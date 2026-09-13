"""Strict JSON adapter between the web application and the exact proof backend."""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction
from itertools import combinations
from math import isfinite
from typing import NoReturn, TextIO

import sympy as sp

from .certificate import DecompositionCertificate, WeightedComponent
from .errors import PolynomialInputError
from .polynomial import HomogeneousPolynomial, Variables
from .primitives import MonomialComponent, SchurComponent, SquareComponent
from .proof import ProofSearchOptions, prove
from .results import ProofResult, ProofStatus
from .search import CombinationSearchLimits, SolverBackend
from .triangle import coefficient_rows, from_coefficient_rows
from .verify import verify_certificate

REQUEST_SCHEMA = "triangle_method.proof_request"
RESPONSE_SCHEMA = "triangle_method.proof_response"
WEB_SCHEMA_VERSION = 1
MINIMUM_DEGREE = 2
MAXIMUM_DEGREE = 12

_REQUEST_FIELDS = {"schema", "schemaVersion", "degree", "coefficientRows"}
_COEFFICIENT_PATTERN = re.compile(r"-?(?:0|[1-9][0-9]{0,63})(?:/[1-9][0-9]{0,63})?\Z")
_SEMANTIC_KINDS = frozenset({"cauchy", "am_gm", "square", "schur", "monomial"})
_VARIABLES = sp.symbols("x y z")
_WEB_PROOF_OPTIONS = ProofSearchOptions(
    combination_limits=CombinationSearchLimits(backend=SolverBackend.AUTO)
)

JsonObject = dict[str, object]
ExactRows = tuple[tuple[sp.Rational, ...], ...]


class WebAdapterInputError(ValueError):
    """Report one stable validation code and readable web-request error message."""

    def __init__(self, code: str, message: str) -> None:
        """Store a nonempty machine code and message for a rejected request."""
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class _ProofRequest:
    """Store one validated display degree and its exact triangular coefficients."""

    degree: int
    coefficient_rows: ExactRows


@dataclass(frozen=True, slots=True)
class _PresentationGroup:
    """Describe one exact semantic group by indexes in the presentation term list."""

    label: str
    semantic_kind: str
    term_indexes: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class _Presentation:
    """Store exactly verified display terms and their disjoint semantic groups."""

    terms: tuple[WeightedComponent, ...]
    groups: tuple[_PresentationGroup, ...]


def _reject_json_constant(value: str) -> NoReturn:
    """Reject nonstandard JSON constants such as NaN and Infinity."""
    raise WebAdapterInputError(
        "request.invalid_json",
        f"unsupported JSON constant: {value}",
    )


def _unique_json_object(pairs: list[tuple[str, object]]) -> JsonObject:
    """Build a JSON object while rejecting duplicate keys at every nesting level."""
    result: JsonObject = {}
    for key, value in pairs:
        if key in result:
            raise WebAdapterInputError(
                "request.invalid_json",
                f"duplicate JSON key: {key}",
            )
        result[key] = value
    return result


def parse_request_document(document: str) -> JsonObject:
    """Decode one strict JSON request document and return its root object."""
    if not isinstance(document, str):
        raise WebAdapterInputError(
            "request.invalid_json",
            "request document must be JSON text",
        )
    try:
        decoded = json.loads(
            document,
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_json_constant,
        )
    except WebAdapterInputError:
        raise
    except (ValueError, RecursionError) as error:
        raise WebAdapterInputError(
            "request.invalid_json",
            "request body must contain one valid JSON document",
        ) from error
    if not isinstance(decoded, dict):
        raise WebAdapterInputError(
            "request.invalid_root",
            "request JSON root must be an object",
        )
    return decoded


def _require_exact_fields(
    value: object,
    expected_fields: set[str],
    *,
    context: str,
) -> JsonObject:
    """Require one object with exactly the named fields and return it unchanged."""
    if not isinstance(value, dict):
        raise WebAdapterInputError(
            "request.invalid_type",
            f"{context} must be an object",
        )
    actual_fields = set(value)
    if actual_fields != expected_fields:
        missing = sorted(expected_fields - actual_fields)
        extra = sorted(actual_fields - expected_fields)
        raise WebAdapterInputError(
            "request.invalid_fields",
            f"{context} has invalid fields: missing={missing}, extra={extra}",
        )
    return value


def _parse_coefficient(value: object, *, row: int, column: int) -> sp.Rational:
    """Parse one canonical integer or fraction string into an exact rational."""
    context = f"coefficientRows[{row}][{column}]"
    if not isinstance(value, str):
        raise WebAdapterInputError(
            "request.invalid_coefficient",
            f"{context} must be an integer or fraction string",
        )
    if _COEFFICIENT_PATTERN.fullmatch(value) is None:
        raise WebAdapterInputError(
            "request.invalid_coefficient",
            f"{context} must use canonical integer or fraction syntax with at most "
            "64 digits per part",
        )
    if value == "-0" or value.startswith("-0/"):
        raise WebAdapterInputError(
            "request.invalid_coefficient",
            f"{context} must write zero canonically as 0",
        )
    try:
        coefficient = Fraction(value)
    except (ValueError, ZeroDivisionError) as error:
        raise WebAdapterInputError(
            "request.invalid_coefficient",
            f"{context} is not a valid exact rational",
        ) from error
    return sp.Rational(coefficient.numerator, coefficient.denominator)


def _contract_integer(value: object) -> int | None:
    """Match JSON Schema integer semantics while continuing to reject booleans."""
    if type(value) is int:
        return value
    if type(value) is float and isfinite(value) and value.is_integer():
        return int(value)
    return None


def _validate_request(payload: object) -> _ProofRequest:
    """Validate the versioned web payload and return exact coefficient rows."""
    request = _require_exact_fields(payload, _REQUEST_FIELDS, context="request")
    if request["schema"] != REQUEST_SCHEMA:
        raise WebAdapterInputError(
            "request.unsupported_schema",
            f"request schema must be {REQUEST_SCHEMA!r}",
        )
    schema_version = _contract_integer(request["schemaVersion"])
    if schema_version is None:
        raise WebAdapterInputError(
            "request.unsupported_version",
            "schemaVersion must be the integer 1",
        )
    if schema_version != WEB_SCHEMA_VERSION:
        raise WebAdapterInputError(
            "request.unsupported_version",
            f"unsupported schemaVersion: {request['schemaVersion']}",
        )

    degree = _contract_integer(request["degree"])
    if degree is None or not MINIMUM_DEGREE <= degree <= MAXIMUM_DEGREE:
        raise WebAdapterInputError(
            "request.invalid_degree",
            f"degree must be an integer from {MINIMUM_DEGREE} through {MAXIMUM_DEGREE}",
        )

    supplied_rows = request["coefficientRows"]
    if not isinstance(supplied_rows, list) or len(supplied_rows) != degree + 1:
        raise WebAdapterInputError(
            "request.invalid_rows",
            f"coefficientRows must contain exactly {degree + 1} rows",
        )

    exact_rows = []
    for row_index, supplied_row in enumerate(supplied_rows):
        if not isinstance(supplied_row, list) or len(supplied_row) != row_index + 1:
            raise WebAdapterInputError(
                "request.invalid_rows",
                f"coefficientRows[{row_index}] must contain exactly "
                f"{row_index + 1} entries",
            )
        exact_rows.append(
            tuple(
                _parse_coefficient(
                    coefficient,
                    row=row_index,
                    column=column_index,
                )
                for column_index, coefficient in enumerate(supplied_row)
            )
        )
    return _ProofRequest(degree=degree, coefficient_rows=tuple(exact_rows))


def _encode_rational(value: sp.Rational) -> dict[str, str]:
    """Encode one exact rational with string integers safe for JavaScript clients."""
    if not isinstance(value, sp.Rational):
        raise TypeError("web response values must be exact SymPy rationals")
    return {
        "numerator": str(int(value.p)),
        "denominator": str(int(value.q)),
    }


def _encode_rows(rows: Sequence[Sequence[sp.Rational]]) -> list[list[dict[str, str]]]:
    """Encode complete exact coefficient rows as JavaScript-safe rational records."""
    return [[_encode_rational(coefficient) for coefficient in row] for row in rows]


def _monomial_expression(
    exponent: tuple[int, int, int],
    variables: Variables,
) -> sp.Expr:
    """Build the ordered-variable monomial represented by one exponent triple."""
    expression = sp.S.One
    for variable, power in zip(variables, exponent, strict=True):
        expression *= variable**power
    return expression


def _component_expression(component: object) -> sp.Expr:
    """Rebuild one supported primitive in its semantic, unexpanded proof form."""
    if type(component) is MonomialComponent:
        return _monomial_expression(component.exponent, component.variables)
    if type(component) is SquareComponent:
        multiplier = _monomial_expression(component.multiplier, component.variables)
        return multiplier * component.factor.to_sympy() ** 2
    if type(component) is SchurComponent:
        first, second, third = (
            _monomial_expression(argument, component.variables)
            for argument in component.arguments
        )
        degree_offset = component.schur_degree - 2
        schur = (
            first**degree_offset * (first - second) * (first - third)
            + second**degree_offset * (second - third) * (second - first)
            + third**degree_offset * (third - first) * (third - second)
        )
        return _monomial_expression(component.multiplier, component.variables) * schur
    raise TypeError("proof certificate contains an unsupported component")


def _verify_component_expression(component: object, expression: sp.Expr) -> None:
    """Check that a displayed semantic expression expands to its exact primitive."""
    if type(component) not in (MonomialComponent, SquareComponent, SchurComponent):
        raise TypeError("proof certificate contains an unsupported component")
    expected = component.expand()
    displayed = HomogeneousPolynomial.from_expr(
        sp.expand(expression),
        variables=component.variables,
    )
    if displayed != expected:
        raise RuntimeError(
            "web presentation expression does not match its verified component"
        )


def _component_kind(component: object) -> str:
    """Return the stable web kind for one supported primitive component."""
    if type(component) is MonomialComponent:
        return "monomial"
    if type(component) is SquareComponent:
        return "square"
    if type(component) is SchurComponent:
        return "schur"
    raise TypeError("proof certificate contains an unsupported component")


def _weighted_contribution(
    term: WeightedComponent,
) -> HomogeneousPolynomial:
    """Expand one weighted primitive into an exact polynomial contribution."""
    expansion = term.component.expand()
    return HomogeneousPolynomial.from_terms(
        {
            exponent: term.weight * coefficient
            for exponent, coefficient in expansion.coefficients.items()
        },
        variables=expansion.variables,
    )


def _difference_edge(component: object) -> tuple[tuple[int, int, int], ...] | None:
    """Return the two monomial exponents when a square factor is exactly their difference."""
    if type(component) is not SquareComponent:
        return None
    terms = tuple(component.factor.coefficients.items())
    if len(terms) != 2 or {coefficient for _, coefficient in terms} != {
        sp.S.One,
        sp.S.NegativeOne,
    }:
        return None
    return tuple(sorted((terms[0][0], terms[1][0])))


def _difference_square_triangles(
    terms: Sequence[WeightedComponent],
) -> tuple[tuple[int, int, int], ...]:
    """Find disjoint three-edge difference-square triangles with common multipliers."""
    selected: list[tuple[int, int, int]] = []
    assigned: set[int] = set()
    for indexes in combinations(range(len(terms)), 3):
        if any(index in assigned for index in indexes):
            continue
        chosen = tuple(terms[index] for index in indexes)
        if any(type(term.component) is not SquareComponent for term in chosen):
            continue
        if any(term.weight <= 0 for term in chosen):
            continue
        if len({term.component.multiplier for term in chosen}) != 1:
            continue
        edges = tuple(_difference_edge(term.component) for term in chosen)
        if any(edge is None for edge in edges):
            continue
        exact_edges = {edge for edge in edges if edge is not None}
        vertices = {vertex for edge in exact_edges for vertex in edge}
        expected_edges = {tuple(sorted(edge)) for edge in combinations(vertices, 2)}
        if len(vertices) == 3 and exact_edges == expected_edges:
            selected.append(indexes)
            assigned.update(indexes)
    return tuple(selected)


def _is_am_gm_square(component: object) -> bool:
    """Recognize a binomial square with exact opposite-sign monomial terms."""
    if type(component) is not SquareComponent:
        return False
    coefficients = tuple(component.factor.coefficients.values())
    return len(coefficients) == 2 and coefficients[0] * coefficients[1] < 0


def _single_component_group(component: object, term_index: int) -> _PresentationGroup:
    """Classify one ungrouped primitive without assigning unsupported provenance."""
    if _is_am_gm_square(component):
        label, semantic_kind = "AM-GM", "am_gm"
    elif type(component) is SquareComponent:
        label, semantic_kind = "Square", "square"
    elif type(component) is SchurComponent:
        label, semantic_kind = "Schur", "schur"
    elif type(component) is MonomialComponent:
        label, semantic_kind = "Nonnegative monomial", "monomial"
    else:
        raise TypeError("proof certificate contains an unsupported component")
    return _PresentationGroup(
        label=label,
        semantic_kind=semantic_kind,
        term_indexes=(term_index,),
    )


def _build_presentation(terms: Sequence[WeightedComponent]) -> _Presentation:
    """Split exact Cauchy portions from weighted edge triangles and retain leftovers."""
    source_terms = tuple(terms)
    triangles = _difference_square_triangles(source_terms)
    triangle_indexes = {index for triangle in triangles for index in triangle}
    presentation_terms: list[WeightedComponent] = []
    presentation_groups: list[_PresentationGroup] = []

    for triangle in triangles:
        common_weight = min(source_terms[index].weight for index in triangle)
        if common_weight <= 0:
            continue
        cauchy_indexes = []
        for source_index in triangle:
            cauchy_indexes.append(len(presentation_terms))
            presentation_terms.append(
                WeightedComponent(
                    weight=common_weight,
                    component=source_terms[source_index].component,
                )
            )
        presentation_groups.append(
            _PresentationGroup(
                label="Cauchy",
                semantic_kind="cauchy",
                term_indexes=tuple(cauchy_indexes),
            )
        )

        for source_index in triangle:
            remainder_weight = source_terms[source_index].weight - common_weight
            if remainder_weight == 0:
                continue
            presentation_index = len(presentation_terms)
            presentation_terms.append(
                WeightedComponent(
                    weight=remainder_weight,
                    component=source_terms[source_index].component,
                )
            )
            presentation_groups.append(
                _single_component_group(
                    source_terms[source_index].component,
                    presentation_index,
                )
            )

    for source_index, term in enumerate(source_terms):
        if source_index in triangle_indexes:
            continue
        presentation_index = len(presentation_terms)
        presentation_terms.append(term)
        presentation_groups.append(
            _single_component_group(term.component, presentation_index)
        )

    return _Presentation(
        terms=tuple(presentation_terms),
        groups=tuple(presentation_groups),
    )


def _encode_presentation_groups(
    groups: Sequence[_PresentationGroup],
) -> list[dict[str, object]]:
    """Encode semantic groups with stable IDs referencing presentation components."""
    return [
        {
            "id": f"group-{group_index}",
            "label": group.label,
            "semanticKind": group.semantic_kind,
            "termIds": [
                f"component-{term_index + 1}" for term_index in group.term_indexes
            ],
        }
        for group_index, group in enumerate(groups, start=1)
    ]


def _verify_presentation(
    target: HomogeneousPolynomial,
    presentation: _Presentation,
) -> None:
    """Require the split display terms to pass the independent exact verifier."""
    grouped_indexes = tuple(
        term_index for group in presentation.groups for term_index in group.term_indexes
    )
    expected_indexes = tuple(range(len(presentation.terms)))
    invalid_group = any(
        not group.label
        or group.semantic_kind not in _SEMANTIC_KINDS
        or not group.term_indexes
        for group in presentation.groups
    )
    invalid_index = any(type(term_index) is not int for term_index in grouped_indexes)
    if (
        invalid_group
        or invalid_index
        or len(set(grouped_indexes)) != len(grouped_indexes)
        or tuple(sorted(grouped_indexes)) != expected_indexes
    ):
        raise RuntimeError("web presentation groups must cover every term exactly once")

    certificate = DecompositionCertificate(
        target=target,
        terms=presentation.terms,
    )
    report = verify_certificate(certificate)
    if (
        report.valid is not True
        or report.issues != ()
        or report.reconstructed != target
        or report.residual is None
        or not report.residual.is_zero
    ):
        raise RuntimeError(
            "split web presentation failed exact certificate verification"
        )


def _proof_payload(
    result: ProofResult,
    *,
    display_degree: int,
) -> JsonObject:
    """Convert a verified certificate into exact display terms, steps, and groups."""
    certificate = result.certificate
    verification = result.verification
    if certificate is None or verification is None or verification.valid is not True:
        raise RuntimeError("a PROVED result must contain an exact verified certificate")
    if verification.residual is None or not verification.residual.is_zero:
        raise RuntimeError("a PROVED result must contain an exact zero residual")

    presentation = _build_presentation(certificate.terms)
    _verify_presentation(result.target, presentation)

    target_rows = coefficient_rows(result.target, display_degree=display_degree)
    accumulated = [
        [sp.S.Zero for _ in range(row_index + 1)]
        for row_index in range(display_degree + 1)
    ]
    term_payloads: list[JsonObject] = []
    step_payloads: list[JsonObject] = []
    weighted_latex: list[str] = []

    for term_index, term in enumerate(presentation.terms, start=1):
        component_id = f"component-{term_index}"
        expression = _component_expression(term.component)
        _verify_component_expression(term.component, expression)
        weighted_expression = term.weight * expression
        contribution = _weighted_contribution(term)
        contribution_rows = coefficient_rows(
            contribution,
            display_degree=display_degree,
        )
        for row_index, row in enumerate(contribution_rows):
            for column_index, coefficient in enumerate(row):
                accumulated[row_index][column_index] += coefficient
        remainder = tuple(
            tuple(
                target_rows[row_index][column_index]
                - accumulated[row_index][column_index]
                for column_index in range(row_index + 1)
            )
            for row_index in range(display_degree + 1)
        )
        expression_latex = sp.latex(expression)
        weighted_expression_latex = sp.latex(weighted_expression)
        weighted_latex.append(weighted_expression_latex)
        term_payloads.append(
            {
                "id": component_id,
                "kind": _component_kind(term.component),
                "weight": _encode_rational(term.weight),
                "expressionLatex": expression_latex,
                "weightedExpressionLatex": weighted_expression_latex,
                "contributionRows": _encode_rows(contribution_rows),
            }
        )
        step_payloads.append(
            {
                "componentId": component_id,
                "accumulatedRows": _encode_rows(accumulated),
                "remainderRows": _encode_rows(remainder),
            }
        )

    if any(
        target_rows[row_index][column_index] != accumulated[row_index][column_index]
        for row_index in range(display_degree + 1)
        for column_index in range(row_index + 1)
    ):
        raise RuntimeError("web proof steps do not reconstruct the verified target")

    target_expression_latex = sp.latex(result.target.to_sympy())
    decomposition_latex = " + ".join(weighted_latex) if weighted_latex else "0"
    return {
        "verified": True,
        "residualZero": True,
        "identityLatex": (f"{target_expression_latex} = {decomposition_latex} \\ge 0"),
        "terms": term_payloads,
        "steps": step_payloads,
        "groups": _encode_presentation_groups(presentation.groups),
    }


def _counterexample_payload(result: ProofResult) -> JsonObject:
    """Convert an exact negative witness into JavaScript-safe display data."""
    counterexample = result.counterexample
    if counterexample is None:
        raise RuntimeError("a DISPROVED result must contain a counterexample")
    coordinates_latex = ", ".join(
        sp.latex(coordinate) for coordinate in counterexample.coordinates
    )
    value_latex = sp.latex(counterexample.value)
    return {
        "coordinates": [
            _encode_rational(coordinate) for coordinate in counterexample.coordinates
        ],
        "value": _encode_rational(counterexample.value),
        "evaluationLatex": (f"F\\left({coordinates_latex}\\right) = {value_latex} < 0"),
    }


def handle_request(payload: object) -> JsonObject:
    """Validate one decoded request, run the exact prover, and return display JSON."""
    request = _validate_request(payload)
    try:
        target = from_coefficient_rows(
            request.coefficient_rows,
            variables=_VARIABLES,
        )
        result = prove(target, options=_WEB_PROOF_OPTIONS)
    except PolynomialInputError as error:
        raise WebAdapterInputError(
            "request.invalid_polynomial",
            str(error),
        ) from error

    target_rows = coefficient_rows(target, display_degree=request.degree)
    proof = None
    counterexample = None
    if result.status is ProofStatus.PROVED:
        proof = _proof_payload(result, display_degree=request.degree)
    elif result.status is ProofStatus.DISPROVED:
        counterexample = _counterexample_payload(result)

    return {
        "schema": RESPONSE_SCHEMA,
        "schemaVersion": WEB_SCHEMA_VERSION,
        "outcome": result.status.value,
        "method": result.method,
        "target": {
            "degree": request.degree,
            "coefficientRows": _encode_rows(target_rows),
            "latex": f"{sp.latex(target.to_sympy())} \\ge 0",
        },
        "proof": proof,
        "counterexample": counterexample,
        "diagnostics": [
            {"code": diagnostic.code, "message": diagnostic.message}
            for diagnostic in result.diagnostics
        ],
    }


def process_request_document(document: str) -> str:
    """Process one JSON request document and return deterministic response JSON."""
    payload = parse_request_document(document)
    response = handle_request(payload)
    return json.dumps(response, sort_keys=True, separators=(",", ":"))


def _write_error(error_stream: TextIO, *, code: str, message: str) -> None:
    """Write one compact structured adapter error to the supplied error stream."""
    document = {"error": {"code": code, "message": message}}
    error_stream.write(json.dumps(document, sort_keys=True, separators=(",", ":")))
    error_stream.write("\n")


def main(
    input_stream: TextIO | None = None,
    output_stream: TextIO | None = None,
    error_stream: TextIO | None = None,
) -> int:
    """Read one stdin request, write one stdout response, and return a process code."""
    input_stream = sys.stdin if input_stream is None else input_stream
    output_stream = sys.stdout if output_stream is None else output_stream
    error_stream = sys.stderr if error_stream is None else error_stream
    try:
        response_document = process_request_document(input_stream.read())
    except WebAdapterInputError as error:
        _write_error(error_stream, code=error.code, message=str(error))
        return 2
    except Exception:
        _write_error(
            error_stream,
            code="adapter.internal_error",
            message="the proof adapter could not complete the request",
        )
        return 1

    output_stream.write(response_document)
    output_stream.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

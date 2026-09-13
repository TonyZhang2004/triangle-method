"""Strict versioned JSON for exact targets and primitive-based certificates."""

from __future__ import annotations

import json
from typing import NoReturn

import sympy as sp

from .certificate import (
    PRIMITIVE_VERSION,
    SCHEMA_VERSION,
    DecompositionCertificate,
    SupportedComponent,
    WeightedComponent,
)
from .errors import CertificateInputError
from .polynomial import Exponent, HomogeneousPolynomial, Variables
from .primitives import MonomialComponent, SchurComponent, SquareComponent

CERTIFICATE_SCHEMA = "triangle_method.decomposition_certificate"


def _require_object(
    value: object, expected_keys: set[str], *, context: str
) -> dict[str, object]:
    """Require a JSON object with precisely the schema's expected fields."""
    if not isinstance(value, dict):
        raise CertificateInputError(f"{context} must be an object")
    actual_keys = set(value)
    if actual_keys != expected_keys:
        missing = sorted(expected_keys - actual_keys)
        extra = sorted(actual_keys - expected_keys)
        raise CertificateInputError(
            f"{context} has invalid fields: missing={missing}, extra={extra}"
        )
    return value


def _require_list(value: object, *, context: str) -> list[object]:
    """Require a JSON array without accepting strings or other iterable values."""
    if not isinstance(value, list):
        raise CertificateInputError(f"{context} must be an array")
    return value


def _require_integer(value: object, *, context: str, minimum: int | None = None) -> int:
    """Read an exact JSON integer and enforce its lower bound, excluding booleans."""
    if type(value) is not int:
        raise CertificateInputError(
            f"{context} must be an integer, not a boolean or float"
        )
    if minimum is not None and value < minimum:
        raise CertificateInputError(f"{context} must be at least {minimum}")
    return value


def _encode_rational(value: sp.Rational) -> dict[str, int]:
    """Represent an exact rational by integer numerator and positive denominator."""
    return {"numerator": int(value.p), "denominator": int(value.q)}


def _decode_rational(value: object, *, context: str) -> sp.Rational:
    """Validate a numerator/denominator object and reconstruct its exact rational."""
    record = _require_object(value, {"numerator", "denominator"}, context=context)
    numerator = _require_integer(record["numerator"], context=f"{context}.numerator")
    denominator = _require_integer(
        record["denominator"], context=f"{context}.denominator", minimum=1
    )
    return sp.Rational(numerator, denominator)


def _decode_exponent(value: object, *, context: str) -> Exponent:
    """Validate three nonnegative exponent integers in the root variable order."""
    coordinates = _require_list(value, context=context)
    if len(coordinates) != 3:
        raise CertificateInputError(f"{context} must contain exactly three exponents")
    validated = tuple(
        _require_integer(coordinate, context=f"{context}[{index}]", minimum=0)
        for index, coordinate in enumerate(coordinates)
    )
    return validated[0], validated[1], validated[2]


def _encode_variables(variables: Variables) -> list[dict[str, object]]:
    """Describe ordered ordinary Symbols while preserving their full assumptions."""
    descriptors = []
    for symbol in variables:
        if type(symbol) is not sp.Symbol:
            raise CertificateInputError(
                "JSON supports ordinary SymPy Symbol objects only; "
                f"{type(symbol).__name__} remains supported only in memory"
            )
        descriptors.append({"name": symbol.name, "assumptions": symbol.assumptions0})
    return descriptors


def _decode_variables(value: object) -> Variables:
    """Rebuild three ordered Symbols from names and complete boolean assumptions."""
    descriptors = _require_list(value, context="variables")
    if len(descriptors) != 3:
        raise CertificateInputError("variables must contain exactly three descriptors")

    variables = []
    for index, descriptor in enumerate(descriptors):
        context = f"variables[{index}]"
        record = _require_object(descriptor, {"name", "assumptions"}, context=context)
        if not isinstance(record["name"], str):
            raise CertificateInputError(f"{context}.name must be a string")
        assumptions = record["assumptions"]
        if not isinstance(assumptions, dict) or any(
            not isinstance(key, str) or type(fact) is not bool
            for key, fact in assumptions.items()
        ):
            raise CertificateInputError(
                f"{context}.assumptions must map strings to booleans"
            )
        symbol = sp.Symbol(record["name"], **assumptions)
        if symbol.assumptions0 != assumptions:
            raise CertificateInputError(
                f"{context}.assumptions must contain the complete consistent assumptions"
            )
        variables.append(symbol)

    return variables[0], variables[1], variables[2]


def _encode_polynomial(polynomial: HomogeneousPolynomial) -> dict[str, object]:
    """Serialize sparse exact terms by exponent slots without an expression parser."""
    return {
        "terms": [
            {"exponent": list(exponent), "coefficient": _encode_rational(coefficient)}
            for exponent, coefficient in sorted(
                polynomial.coefficients.items(), reverse=True
            )
        ]
    }


def _decode_polynomial(
    value: object, variables: Variables, *, context: str
) -> HomogeneousPolynomial:
    """Validate sparse records, reject duplicate exponents, and build the exact model."""
    record = _require_object(value, {"terms"}, context=context)
    terms = _require_list(record["terms"], context=f"{context}.terms")
    coefficients = {}
    for index, term in enumerate(terms):
        term_context = f"{context}.terms[{index}]"
        term_record = _require_object(
            term, {"exponent", "coefficient"}, context=term_context
        )
        exponent = _decode_exponent(
            term_record["exponent"], context=f"{term_context}.exponent"
        )
        if exponent in coefficients:
            raise CertificateInputError(
                f"{context} contains duplicate exponent {exponent}"
            )
        coefficients[exponent] = _decode_rational(
            term_record["coefficient"], context=f"{term_context}.coefficient"
        )
    return HomogeneousPolynomial.from_terms(coefficients, variables=variables)


def _encode_component(component: SupportedComponent) -> dict[str, object]:
    """Serialize a supported primitive's defining parameters without cached expansion."""
    if type(component) is MonomialComponent:
        return {"kind": "monomial", "exponent": list(component.exponent)}
    if type(component) is SquareComponent:
        return {
            "kind": "square",
            "factor": _encode_polynomial(component.factor),
            "multiplier": list(component.multiplier),
        }
    if type(component) is SchurComponent:
        return {
            "kind": "schur",
            "schur_degree": component.schur_degree,
            "arguments": [list(exponent) for exponent in component.arguments],
            "multiplier": list(component.multiplier),
        }
    raise CertificateInputError("unsupported component type")


def _decode_component(
    value: object, variables: Variables, *, context: str
) -> SupportedComponent:
    """Validate a primitive tag and reconstruct its defining public component object."""
    if not isinstance(value, dict):
        raise CertificateInputError(f"{context} must be an object")
    kind = value.get("kind")
    if kind == "monomial":
        record = _require_object(value, {"kind", "exponent"}, context=context)
        return MonomialComponent(
            exponent=_decode_exponent(
                record["exponent"], context=f"{context}.exponent"
            ),
            variables=variables,
        )
    if kind == "square":
        record = _require_object(
            value, {"kind", "factor", "multiplier"}, context=context
        )
        return SquareComponent(
            factor=_decode_polynomial(
                record["factor"], variables, context=f"{context}.factor"
            ),
            multiplier=_decode_exponent(
                record["multiplier"], context=f"{context}.multiplier"
            ),
        )
    if kind == "schur":
        record = _require_object(
            value, {"kind", "schur_degree", "arguments", "multiplier"}, context=context
        )
        arguments = _require_list(record["arguments"], context=f"{context}.arguments")
        if len(arguments) != 3:
            raise CertificateInputError(
                f"{context}.arguments must contain three monomials"
            )
        return SchurComponent(
            schur_degree=_require_integer(
                record["schur_degree"], context=f"{context}.schur_degree", minimum=3
            ),
            arguments=tuple(
                _decode_exponent(argument, context=f"{context}.arguments[{index}]")
                for index, argument in enumerate(arguments)
            ),
            variables=variables,
            multiplier=_decode_exponent(
                record["multiplier"], context=f"{context}.multiplier"
            ),
        )
    raise CertificateInputError(
        f"{context} has an unsupported or missing primitive kind"
    )


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """Reject repeated JSON object keys instead of silently accepting their last value."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise CertificateInputError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> NoReturn:
    """Reject nonstandard JSON constants such as NaN and Infinity."""
    raise CertificateInputError(f"unsupported JSON constant: {value}")


def _decode_certificate(value: object) -> DecompositionCertificate:
    """Validate schema versions and reconstruct a target with its weighted primitives."""
    record = _require_object(
        value,
        {
            "schema",
            "schema_version",
            "primitive_version",
            "variables",
            "target",
            "terms",
        },
        context="certificate",
    )
    if record["schema"] != CERTIFICATE_SCHEMA:
        raise CertificateInputError("unsupported certificate schema")
    for field, supported in (
        ("schema_version", SCHEMA_VERSION),
        ("primitive_version", PRIMITIVE_VERSION),
    ):
        if _require_integer(record[field], context=field) != supported:
            raise CertificateInputError(f"unsupported {field}")

    variables = _decode_variables(record["variables"])
    target = _decode_polynomial(record["target"], variables, context="target")
    terms = []
    for index, term in enumerate(_require_list(record["terms"], context="terms")):
        context = f"terms[{index}]"
        term_record = _require_object(term, {"weight", "component"}, context=context)
        terms.append(
            WeightedComponent(
                weight=_decode_rational(
                    term_record["weight"], context=f"{context}.weight"
                ),
                component=_decode_component(
                    term_record["component"], variables, context=f"{context}.component"
                ),
            )
        )
    return DecompositionCertificate(target=target, terms=terms)


def certificate_to_json(
    certificate: DecompositionCertificate, *, indent: int | None = 2
) -> str:
    """Return deterministic JSON containing exact data and versioned primitive parameters."""
    if type(certificate) is not DecompositionCertificate:
        raise CertificateInputError("certificate must be a DecompositionCertificate")
    if indent is not None:
        _require_integer(indent, context="indent", minimum=0)
    document = {
        "schema": CERTIFICATE_SCHEMA,
        "schema_version": certificate.schema_version,
        "primitive_version": certificate.primitive_version,
        "variables": _encode_variables(certificate.target.variables),
        "target": _encode_polynomial(certificate.target),
        "terms": [
            {
                "weight": _encode_rational(term.weight),
                "component": _encode_component(term.component),
            }
            for term in certificate.terms
        ],
    }
    try:
        return json.dumps(document, indent=indent, sort_keys=True, allow_nan=False)
    except (TypeError, ValueError, OverflowError) as error:
        raise CertificateInputError(
            f"certificate cannot be encoded as JSON: {error}"
        ) from error


def certificate_from_json(document: str) -> DecompositionCertificate:
    """Load strict JSON through validated constructors without claiming a verified proof."""
    if not isinstance(document, str):
        raise CertificateInputError("JSON document must be a string")
    try:
        value = json.loads(
            document,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_json_constant,
        )
        return _decode_certificate(value)
    except CertificateInputError:
        raise
    except (TypeError, ValueError, KeyError, OverflowError, RecursionError) as error:
        raise CertificateInputError(f"invalid certificate JSON: {error}") from error

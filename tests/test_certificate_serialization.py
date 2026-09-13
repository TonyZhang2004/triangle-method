"""Strict deterministic JSON tests for exact decomposition certificates."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
import sympy as sp

from triangle_method import (
    CertificateInputError,
    DecompositionCertificate,
    HomogeneousPolynomial,
    MonomialComponent,
    SchurComponent,
    SquareComponent,
    WeightedComponent,
    verify_certificate,
)

Variables = tuple[sp.Symbol, sp.Symbol, sp.Symbol]
UNIT_ARGUMENTS = ((1, 0, 0), (0, 1, 0), (0, 0, 1))


def _all_primitive_certificate(variables: Variables) -> DecompositionCertificate:
    """Build one exact certificate containing monomial, square, and Schur terms."""

    x, y, z = variables
    schur_expression = (
        x * (x - y) * (x - z) + y * (y - z) * (y - x) + z * (z - x) * (z - y)
    )
    target = HomogeneousPolynomial.from_expr(
        sp.Rational(2, 3) * x**3
        + sp.Rational(1, 2) * z * (x - y) ** 2
        + sp.Rational(5, 7) * schur_expression,
        variables=variables,
    )
    factor = HomogeneousPolynomial.from_expr(x - y, variables=variables)
    terms = (
        WeightedComponent(
            weight=sp.Rational(2, 3),
            component=MonomialComponent(exponent=(3, 0, 0), variables=variables),
        ),
        WeightedComponent(
            weight=sp.Rational(1, 2),
            component=SquareComponent(factor=factor, multiplier=(0, 0, 1)),
        ),
        WeightedComponent(
            weight=sp.Rational(5, 7),
            component=SchurComponent(
                schur_degree=3,
                arguments=UNIT_ARGUMENTS,
                variables=variables,
            ),
        ),
    )
    return DecompositionCertificate(target=target, terms=terms)


def _valid_payload() -> dict[str, object]:
    """Return a mutable decoded document for isolated malformed-schema tests."""

    x, y, z = sp.symbols("x y z")
    return json.loads(_all_primitive_certificate((x, y, z)).to_json())


def _dump(payload: object) -> str:
    """Encode a mutated JSON payload deterministically for a parser rejection test."""

    return json.dumps(payload, sort_keys=True)


def _contains_json_float(value: object) -> bool:
    """Return whether any decoded JSON value is a floating-point number."""

    if isinstance(value, float):
        return True
    if isinstance(value, dict):
        return any(_contains_json_float(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_json_float(item) for item in value)
    return False


def test_json_round_trip_preserves_all_primitive_parameters_and_exact_weights() -> None:
    """Round-trip every built-in primitive without expanding away its proof structure."""

    x, y, z = sp.symbols("x y z")
    certificate = _all_primitive_certificate((x, y, z))

    document = certificate.to_json()
    payload = json.loads(document)
    restored = DecompositionCertificate.from_json(document)

    assert payload["schema"] == "triangle_method.decomposition_certificate"
    assert payload["schema_version"] == certificate.schema_version
    assert payload["primitive_version"] == certificate.primitive_version
    assert [term["weight"] for term in payload["terms"]] == [
        {"numerator": 2, "denominator": 3},
        {"numerator": 1, "denominator": 2},
        {"numerator": 5, "denominator": 7},
    ]
    assert [term["component"]["kind"] for term in payload["terms"]] == [
        "monomial",
        "square",
        "schur",
    ]
    assert not _contains_json_float(payload)
    assert restored == certificate
    assert restored.to_json() == document
    assert verify_certificate(restored).valid


def test_json_round_trip_preserves_reversed_symbol_order_and_assumptions() -> None:
    """Rebuild each ordered symbol with its complete distinguishing assumptions."""

    x = sp.Symbol("x", positive=True)
    y = sp.Symbol("y", nonnegative=True)
    z = sp.Symbol("z", real=True)
    variables = (z, y, x)
    factor_expression = z - sp.Rational(2, 3) * y + x
    target = HomogeneousPolynomial.from_expr(
        sp.Rational(5, 7) * factor_expression**2 + sp.Rational(11, 13) * z * y,
        variables=variables,
    )
    certificate = DecompositionCertificate(
        target=target,
        terms=(
            WeightedComponent(
                weight=sp.Rational(5, 7),
                component=SquareComponent(
                    factor=HomogeneousPolynomial.from_expr(
                        factor_expression,
                        variables=variables,
                    )
                ),
            ),
            WeightedComponent(
                weight=sp.Rational(11, 13),
                component=MonomialComponent(exponent=(1, 1, 0), variables=variables),
            ),
        ),
    )

    payload = json.loads(certificate.to_json())
    restored = DecompositionCertificate.from_json(certificate.to_json())

    assert [entry["name"] for entry in payload["variables"]] == ["z", "y", "x"]
    assert restored.target.variables == variables
    assert tuple(symbol.assumptions0 for symbol in restored.target.variables) == tuple(
        symbol.assumptions0 for symbol in variables
    )
    assert restored == certificate
    assert verify_certificate(restored).valid


def test_json_output_is_deterministic_in_pretty_and_compact_forms() -> None:
    """Keep key ordering and whitespace stable for a chosen indentation mode."""

    x, y, z = sp.symbols("x y z")
    certificate = _all_primitive_certificate((x, y, z))

    assert certificate.to_json() == certificate.to_json(indent=2)
    assert certificate.to_json(indent=None) == certificate.to_json(indent=None)
    assert "\n" in certificate.to_json(indent=2)
    assert "\n" not in certificate.to_json(indent=None)


@pytest.mark.parametrize("indent", [-1, True, 2.5])
def test_json_rejects_invalid_indentation_values(indent: object) -> None:
    """Reject booleans, negative values, and floats as serialization indentation."""

    x, y, z = sp.symbols("x y z")
    certificate = _all_primitive_certificate((x, y, z))

    with pytest.raises(CertificateInputError):
        certificate.to_json(indent=indent)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "document",
    [
        "",
        "{",
        "[]",
        "null",
        '{"value": NaN}',
        '{"schema": "first", "schema": "second"}',
    ],
)
def test_json_rejects_malformed_roots_constants_and_duplicate_keys(
    document: str,
) -> None:
    """Fail closed on malformed JSON instead of accepting parser extensions."""

    with pytest.raises(CertificateInputError):
        DecompositionCertificate.from_json(document)


@pytest.mark.parametrize("document", [b"{}", None, object()])
def test_json_parser_requires_text(document: object) -> None:
    """Require a text document rather than coercing unrelated input types."""

    with pytest.raises(CertificateInputError):
        DecompositionCertificate.from_json(document)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema", "unknown.certificate"),
        ("schema_version", 999),
        ("primitive_version", 999),
    ],
)
def test_json_rejects_unknown_schema_or_versions(field: str, value: object) -> None:
    """Reject documents whose schema or primitive semantics are not supported."""

    payload = _valid_payload()
    payload[field] = value

    with pytest.raises(CertificateInputError):
        DecompositionCertificate.from_json(_dump(payload))


def test_json_rejects_unknown_fields_and_primitive_kinds() -> None:
    """Keep the versioned schema closed to misspelled fields and unproved primitives."""

    extra_field = _valid_payload()
    extra_field["unexpected"] = True
    unknown_primitive = _valid_payload()
    unknown_primitive["terms"][0]["component"]["kind"] = "asserted_nonnegative"

    for payload in (extra_field, unknown_primitive):
        with pytest.raises(CertificateInputError):
            DecompositionCertificate.from_json(_dump(payload))


def test_json_rejects_duplicate_target_exponents() -> None:
    """Prevent repeated sparse terms from being silently overwritten or combined."""

    payload = _valid_payload()
    target_terms = payload["target"]["terms"]
    target_terms.append(dict(target_terms[0]))

    with pytest.raises(CertificateInputError, match="duplicate exponent"):
        DecompositionCertificate.from_json(_dump(payload))


@pytest.mark.parametrize(
    ("numerator", "denominator"),
    [
        (1.0, 2),
        (True, 2),
        (1, 0),
        (1, -2),
        (1, 2.0),
    ],
)
def test_json_rejects_inexact_or_invalid_rational_records(
    numerator: object,
    denominator: object,
) -> None:
    """Require integer numerators and strictly positive integer denominators."""

    payload = _valid_payload()
    payload["terms"][0]["weight"] = {
        "numerator": numerator,
        "denominator": denominator,
    }

    with pytest.raises(CertificateInputError):
        DecompositionCertificate.from_json(_dump(payload))


def test_json_rejects_duplicate_or_inconsistent_variable_descriptors() -> None:
    """Reject variable records that cannot rebuild three distinct exact symbols."""

    duplicate = _valid_payload()
    duplicate["variables"][1] = dict(duplicate["variables"][0])
    inconsistent = _valid_payload()
    inconsistent["variables"][0]["assumptions"] = {
        "positive": True,
        "negative": True,
    }

    for payload in (duplicate, inconsistent):
        with pytest.raises(CertificateInputError):
            DecompositionCertificate.from_json(_dump(payload))


def test_loading_a_certificate_does_not_replace_exact_verification() -> None:
    """Deserialize a structurally valid altered target while leaving it unproved."""

    payload = _valid_payload()
    payload["target"]["terms"][0]["coefficient"] = {
        "numerator": 999,
        "denominator": 1,
    }

    restored = DecompositionCertificate.from_json(_dump(payload))

    assert not verify_certificate(restored).valid


def test_verification_imports_no_numerical_solver_in_an_isolated_interpreter(
    tmp_path: Path,
) -> None:
    """Keep manual verification independent from SciPy and future search backends."""

    script = textwrap.dedent(
        """
        import sys
        import sympy as sp
        from triangle_method import (
            DecompositionCertificate,
            HomogeneousPolynomial,
            MonomialComponent,
            WeightedComponent,
            verify_certificate,
        )

        x, y, z = sp.symbols("x y z")
        variables = (x, y, z)
        target = HomogeneousPolynomial.from_expr(x**2, variables=variables)
        term = WeightedComponent(
            weight=1,
            component=MonomialComponent(exponent=(2, 0, 0), variables=variables),
        )
        certificate = DecompositionCertificate(target=target, terms=(term,))
        assert verify_certificate(certificate).valid
        assert not any(
            name == "scipy" or name.startswith("scipy.") for name in sys.modules
        )
        """
    )
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"

    completed = subprocess.run(
        [sys.executable, "-I", "-c", script],
        cwd=tmp_path,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr

"""Independent exact-verification tests for decomposition certificates."""

from __future__ import annotations

from fractions import Fraction
from typing import Any, TypeAlias

import pytest
import sympy as sp

from triangle_method import (
    CertificateInputError,
    DecompositionCertificate,
    HomogeneousPolynomial,
    MonomialComponent,
    SchurComponent,
    SquareComponent,
    VerificationIssue,
    VerificationReport,
    WeightedComponent,
    verify_certificate,
)

Variables: TypeAlias = tuple[sp.Symbol, sp.Symbol, sp.Symbol]
Primitive: TypeAlias = MonomialComponent | SquareComponent | SchurComponent
UNIT_ARGUMENTS = ((1, 0, 0), (0, 1, 0), (0, 0, 1))


def _polynomial(
    expression: sp.Expr | int, variables: Variables
) -> HomogeneousPolynomial:
    """Build an exact target or square factor in the requested variable order."""

    return HomogeneousPolynomial.from_expr(expression, variables=variables)


def _square(
    expression: sp.Expr,
    variables: Variables,
    *,
    multiplier: tuple[int, int, int] = (0, 0, 0),
) -> SquareComponent:
    """Create a square primitive from an independently stated homogeneous factor."""

    return SquareComponent(
        factor=_polynomial(expression, variables),
        multiplier=multiplier,
    )


def _schur(
    schur_degree: int,
    variables: Variables,
    *,
    multiplier: tuple[int, int, int] = (0, 0, 0),
) -> SchurComponent:
    """Create a classic-variable Schur primitive with an optional monomial shift."""

    return SchurComponent(
        schur_degree=schur_degree,
        arguments=UNIT_ARGUMENTS,
        variables=variables,
        multiplier=multiplier,
    )


def _weighted(
    component: Primitive,
    weight: int | Fraction | sp.Rational = 1,
) -> WeightedComponent:
    """Attach an exact nonnegative weight to one theorem-backed primitive."""

    return WeightedComponent(weight=weight, component=component)


def _approved_terms(
    case_name: str, variables: Variables
) -> tuple[WeightedComponent, ...]:
    """Return the independently known decomposition for one approved fixture."""

    x, y, z = variables
    half = sp.Rational(1, 2)

    if case_name == "quadratic_squares":
        return tuple(
            _weighted(_square(factor, variables), half)
            for factor in (x - y, y - z, z - x)
        )
    if case_name == "cubic_schur":
        return (_weighted(_schur(3, variables)),)
    if case_name == "quintic_schur":
        return (_weighted(_schur(5, variables)),)
    if case_name == "cubic_weighted_squares":
        return (
            _weighted(_square(y - z, variables, multiplier=(1, 0, 0))),
            _weighted(_square(z - x, variables, multiplier=(0, 1, 0))),
            _weighted(_square(x - y, variables, multiplier=(0, 0, 1))),
        )
    if case_name == "quartic_squares":
        return tuple(
            _weighted(_square(factor, variables), half)
            for factor in (x**2 - y**2, y**2 - z**2, z**2 - x**2)
        )
    if case_name == "quartic_schur_lift":
        return tuple(
            _weighted(_schur(3, variables, multiplier=multiplier))
            for multiplier in ((1, 0, 0), (0, 1, 0), (0, 0, 1))
        )
    if case_name == "quintic_schur_plus_squares":
        return (
            _weighted(_schur(5, variables)),
            *(
                _weighted(
                    _square(factor, variables, multiplier=(1, 1, 1)),
                    half,
                )
                for factor in (x - y, y - z, z - x)
            ),
        )
    raise AssertionError(f"missing independent certificate for {case_name}")


def _issue_codes(report: VerificationReport) -> set[str]:
    """Return stable diagnostic codes from one verification report."""

    return {issue.code for issue in report.issues}


def test_certificate_types_are_available_from_the_package_root() -> None:
    """Keep certificate records, diagnostics, and verifier on the supported API."""

    assert DecompositionCertificate.__module__.startswith("triangle_method")
    assert WeightedComponent.__module__.startswith("triangle_method")
    assert VerificationIssue.__module__.startswith("triangle_method")
    assert VerificationReport.__module__.startswith("triangle_method")
    assert callable(verify_certificate)
    assert issubclass(CertificateInputError, ValueError)


def test_manual_certificates_verify_all_seven_approved_identities(
    ternary_symbols: Variables,
    approved_polynomial_cases: tuple[Any, ...],
) -> None:
    """Verify each approved target from its independently stated Schur/square identity."""

    for case in approved_polynomial_cases:
        target = _polynomial(case.expression, ternary_symbols)
        certificate = DecompositionCertificate(
            target=target,
            terms=_approved_terms(case.name, ternary_symbols),
        )

        report = verify_certificate(certificate)

        assert isinstance(report, VerificationReport), case.name
        assert report.valid, (case.name, report.errors)
        assert report.issues == (), case.name
        assert report.errors == (), case.name
        assert report.reconstructed == target, case.name
        assert report.residual is not None and report.residual.is_zero, case.name


def test_certificate_supports_an_explicit_nonnegative_monomial_leftover(
    ternary_symbols: Variables,
) -> None:
    """Represent a positive unmatched coefficient as a weighted monomial primitive."""

    x, y, z = ternary_symbols
    target = _polynomial(2 * (x - y) ** 2 + 3 * z**2, ternary_symbols)
    certificate = DecompositionCertificate(
        target=target,
        terms=(
            _weighted(_square(x - y, ternary_symbols), 2),
            _weighted(
                MonomialComponent(exponent=(0, 0, 2), variables=ternary_symbols),
                3,
            ),
        ),
    )

    report = verify_certificate(certificate)

    assert report.valid
    assert report.reconstructed == target
    assert report.residual is not None and report.residual.is_zero


def test_general_square_certificate_verifies_without_pattern_restrictions(
    ternary_symbols: Variables,
) -> None:
    """Accept a homogeneous factor with three terms and a negative coefficient."""

    x, y, z = ternary_symbols
    target = _polynomial((x + y - z) ** 2, ternary_symbols)
    certificate = DecompositionCertificate(
        target=target,
        terms=(_weighted(_square(x + y - z, ternary_symbols)),),
    )

    assert verify_certificate(certificate).valid


def test_zero_target_has_a_valid_empty_certificate(
    ternary_symbols: Variables,
) -> None:
    """Treat the empty nonnegative sum as an exact certificate for zero."""

    target = _polynomial(0, ternary_symbols)
    certificate = DecompositionCertificate(target=target, terms=())

    report = verify_certificate(certificate)

    assert certificate.terms == ()
    assert report.valid
    assert report.reconstructed == target
    assert report.residual == target


def test_empty_certificate_does_not_prove_a_nonzero_target(
    ternary_symbols: Variables,
) -> None:
    """Report an exact identity failure when no terms reconstruct a nonzero target."""

    x, _, _ = ternary_symbols
    target = _polynomial(x**2, ternary_symbols)

    report = verify_certificate(DecompositionCertificate(target=target, terms=()))

    assert not report.valid
    assert _issue_codes(report) == {"identity_mismatch"}
    assert all(isinstance(issue, VerificationIssue) for issue in report.issues)
    assert report.reconstructed == _polynomial(0, ternary_symbols)
    assert report.residual == target


@pytest.mark.parametrize("weight", [-1, sp.Rational(-1, 3)])
def test_weighted_component_rejects_negative_weights(
    weight: sp.Rational,
    ternary_symbols: Variables,
) -> None:
    """Reject a negative multiplier before it can enter a nonnegative combination."""

    component = MonomialComponent(exponent=(1, 0, 0), variables=ternary_symbols)

    with pytest.raises(CertificateInputError):
        WeightedComponent(weight=weight, component=component)


@pytest.mark.parametrize("weight", [True, 0.25, sp.Float("0.25")])
def test_weighted_component_rejects_boolean_or_inexact_weights(
    weight: object,
    ternary_symbols: Variables,
) -> None:
    """Keep certificate weights exact and distinct from Python truth values."""

    component = MonomialComponent(exponent=(1, 0, 0), variables=ternary_symbols)

    with pytest.raises(CertificateInputError):
        WeightedComponent(weight=weight, component=component)  # type: ignore[arg-type]


def test_weighted_component_converts_fraction_without_approximation(
    ternary_symbols: Variables,
) -> None:
    """Canonicalize a fractions.Fraction weight to the package's exact rational type."""

    component = MonomialComponent(exponent=(1, 0, 0), variables=ternary_symbols)
    weighted = WeightedComponent(weight=Fraction(2, 7), component=component)

    assert weighted.weight == sp.Rational(2, 7)
    assert isinstance(weighted.weight, sp.Rational)


def test_certificate_rejects_a_component_with_another_variable_order(
    ternary_symbols: Variables,
) -> None:
    """Prevent syntactically similar primitives from changing the target basis order."""

    x, _, _ = ternary_symbols
    target = _polynomial(x**2, ternary_symbols)
    reversed_variables = tuple(reversed(ternary_symbols))
    mismatched = MonomialComponent(exponent=(2, 0, 0), variables=reversed_variables)

    with pytest.raises(CertificateInputError):
        DecompositionCertificate(target=target, terms=(_weighted(mismatched),))


def test_verifier_reports_component_degree_mismatch(
    ternary_symbols: Variables,
) -> None:
    """Reject a homogeneous component whose formal degree differs from its target."""

    x, _, _ = ternary_symbols
    target = _polynomial(x**2, ternary_symbols)
    cubic = MonomialComponent(exponent=(3, 0, 0), variables=ternary_symbols)
    certificate = DecompositionCertificate(target=target, terms=(_weighted(cubic),))

    report = verify_certificate(certificate)

    assert not report.valid
    assert _issue_codes(report) == {"degree_mismatch"}
    assert report.issues[0].term_index == 0
    assert report.errors == (report.issues[0].message,)
    assert report.reconstructed is None
    assert report.residual is None


def test_verifier_reports_an_exact_residual_for_an_altered_target(
    ternary_symbols: Variables,
) -> None:
    """Detect a changed target even when every supplied primitive remains valid."""

    x, y, z = ternary_symbols
    square_target = _polynomial((x - y) ** 2, ternary_symbols)
    altered_target = _polynomial((x - y) ** 2 + z**2, ternary_symbols)
    certificate = DecompositionCertificate(
        target=altered_target,
        terms=(_weighted(_square(x - y, ternary_symbols)),),
    )

    report = verify_certificate(certificate)

    assert not report.valid
    assert _issue_codes(report) == {"identity_mismatch"}
    assert report.reconstructed == square_target
    assert report.residual == _polynomial(z**2, ternary_symbols)


@pytest.mark.parametrize("terms", [None, "terms", (object(),)])
def test_certificate_rejects_malformed_term_collections(
    terms: object,
    ternary_symbols: Variables,
) -> None:
    """Require an immutable sequence containing only weighted primitives."""

    target = _polynomial(0, ternary_symbols)

    with pytest.raises(CertificateInputError):
        DecompositionCertificate(target=target, terms=terms)  # type: ignore[arg-type]


def test_certificate_and_weighted_terms_are_immutable(
    ternary_symbols: Variables,
) -> None:
    """Keep exact theorem parameters and target identity fixed after construction."""

    target = _polynomial(0, ternary_symbols)
    component = MonomialComponent(exponent=(0, 0, 0), variables=ternary_symbols)
    weighted = _weighted(component, 0)
    certificate = DecompositionCertificate(target=target, terms=(weighted,))

    with pytest.raises((AttributeError, TypeError)):
        weighted.weight = sp.Integer(1)  # type: ignore[misc]
    with pytest.raises((AttributeError, TypeError)):
        certificate.terms = ()  # type: ignore[misc]


def test_verifier_rejects_a_noncertificate_input() -> None:
    """Raise a clear input error instead of treating arbitrary data as a proof."""

    with pytest.raises(CertificateInputError):
        verify_certificate(object())  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("field", "value", "issue_code"),
    [
        ("schema_version", 2, "unsupported_schema_version"),
        ("schema_version", True, "unsupported_schema_version"),
        ("primitive_version", 2, "unsupported_primitive_version"),
        ("primitive_version", True, "unsupported_primitive_version"),
    ],
)
def test_verifier_rejects_unsupported_in_memory_versions(
    field: str,
    value: object,
    issue_code: str,
    ternary_symbols: Variables,
) -> None:
    """Refuse altered metadata before interpreting in-memory certificate semantics."""

    x, _, _ = ternary_symbols
    target = _polynomial(x, ternary_symbols)
    component = MonomialComponent(exponent=(1, 0, 0), variables=ternary_symbols)
    certificate = DecompositionCertificate(
        target=target,
        terms=(_weighted(component),),
    )
    object.__setattr__(certificate, field, value)

    report = verify_certificate(certificate)

    assert not report.valid
    assert _issue_codes(report) == {issue_code}
    assert report.reconstructed is None
    assert report.residual is None

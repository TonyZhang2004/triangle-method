"""Tests for deterministic direct proof recognition and its verification gate."""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from collections.abc import Callable
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Any

import pytest
import sympy as sp
from sympy.polys.polyerrors import PolynomialError

from triangle_method import (
    CertificateInputError,
    Counterexample,
    DecompositionCertificate,
    HomogeneousPolynomial,
    MonomialComponent,
    Normalization,
    PolynomialInputError,
    ProofDiagnostic,
    ProofResult,
    ProofSearchOptions,
    ProofStatus,
    SchurComponent,
    SquareComponent,
    VerificationIssue,
    VerificationReport,
    WeightedComponent,
    prove,
    triangle_exponents,
    verify_certificate,
    verify_counterexample,
)

Variables = tuple[sp.Symbol, sp.Symbol, sp.Symbol]


def _direct_only_options() -> ProofSearchOptions:
    """Disable later backend phases when a test isolates direct recognition."""

    return ProofSearchOptions(
        enable_combination_search=False,
        enable_counterexample_search=False,
    )


def _polynomial(expression: object, variables: Variables) -> HomogeneousPolynomial:
    """Build one exact homogeneous target in the supplied variable order."""

    return HomogeneousPolynomial.from_expr(expression, variables=variables)


def _classic_schur(degree: int, variables: Variables) -> sp.Expr:
    """Return the classic degree-d Schur expression independently of package primitives."""

    first, second, third = variables
    return sp.expand(
        first ** (degree - 2) * (first - second) * (first - third)
        + second ** (degree - 2) * (second - third) * (second - first)
        + third ** (degree - 2) * (third - first) * (third - second)
    )


def _substituted_schur(degree: int, arguments: tuple[sp.Expr, ...]) -> sp.Expr:
    """Return Schur after an explicit nontrivial monomial substitution."""

    first, second, third = arguments
    return sp.expand(
        first ** (degree - 2) * (first - second) * (first - third)
        + second ** (degree - 2) * (second - third) * (second - first)
        + third ** (degree - 2) * (third - first) * (third - second)
    )


def _diagnostic_codes(result: ProofResult) -> tuple[str, ...]:
    """Return stable diagnostic codes in their reported attempt order."""

    return tuple(diagnostic.code for diagnostic in result.diagnostics)


def _assert_proved(
    result: ProofResult,
    target: HomogeneousPolynomial,
    *,
    method: str,
) -> DecompositionCertificate:
    """Check the complete public and independently verified state of a proved result."""

    assert result.target == target
    assert result.status is ProofStatus.PROVED
    assert result.method == method
    assert result.certificate is not None
    assert result.certificate.target == target
    assert result.verification is not None
    assert result.verification.valid
    assert result.verification.issues == ()
    assert result.verification.reconstructed == target
    assert result.verification.residual is not None
    assert result.verification.residual.is_zero
    assert result.counterexample is None

    independently_checked = verify_certificate(result.certificate)
    assert independently_checked.valid
    assert independently_checked.reconstructed == target
    assert independently_checked.residual is not None
    assert independently_checked.residual.is_zero

    method_prefix = {
        "zero": "zero",
        "monomial": "monomial",
        "classic_schur": "schur",
        "exact_square": "square",
        "nonnegative_coefficients": "coefficients",
        "candidate_combination": "combination",
    }[method]
    codes = _diagnostic_codes(result)
    assert f"{method_prefix}.matched" in codes
    assert codes[-1] == "verification.passed"
    assert codes.index(f"{method_prefix}.matched") < codes.index("verification.passed")
    assert not any(code.endswith(".proved") for code in codes)
    assert all(diagnostic.message for diagnostic in result.diagnostics)

    for term in result.certificate.terms:
        assert isinstance(term.weight, sp.Rational)
        assert term.weight >= 0
        assert not term.component.expand().to_sympy().atoms(sp.Float)
    return result.certificate


def _assert_unknown(result: ProofResult, target: HomogeneousPolynomial) -> None:
    """Check that an inconclusive attempt contains diagnostics and no proof evidence."""

    assert result.target == target
    assert result.status is ProofStatus.UNKNOWN
    assert result.method is None
    assert result.certificate is None
    assert result.verification is None
    assert result.counterexample is None
    assert result.diagnostics
    assert _diagnostic_codes(result)[-1] == "direct.no_match"
    assert all(diagnostic.message for diagnostic in result.diagnostics)


def test_proof_api_is_exported_with_stable_status_values() -> None:
    """Expose the automatic proof records and fixed string-valued status enum."""

    assert issubclass(ProofStatus, str)
    assert ProofStatus.PROVED.value == "PROVED"
    assert ProofStatus.UNKNOWN.value == "UNKNOWN"
    assert ProofStatus.DISPROVED.value == "DISPROVED"
    assert tuple(status.value for status in ProofStatus) == (
        "PROVED",
        "UNKNOWN",
        "DISPROVED",
    )
    assert ProofDiagnostic.__module__.startswith("triangle_method")
    assert ProofResult.__module__.startswith("triangle_method")
    assert callable(prove)


def test_public_result_records_are_frozen_and_copy_diagnostics(
    ternary_symbols: Variables,
) -> None:
    """Prevent caller mutation of diagnostics or completed automatic proof results."""

    x, _, _ = ternary_symbols
    target = _polynomial(-x, ternary_symbols)
    diagnostic = ProofDiagnostic(code="test.unknown", message="No test proof found.")
    caller_owned = [diagnostic]
    result = ProofResult(
        target=target,
        status=ProofStatus.UNKNOWN,
        diagnostics=caller_owned,  # type: ignore[arg-type]
    )

    caller_owned.append(
        ProofDiagnostic(code="test.changed", message="Caller-owned mutation.")
    )

    assert result.diagnostics == (diagnostic,)
    assert isinstance(result.diagnostics, tuple)
    with pytest.raises(FrozenInstanceError):
        result.status = ProofStatus.PROVED  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        diagnostic.code = "test.changed"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("code", "message"),
    [
        ("", "message"),
        ("   ", "message"),
        (" code", "message"),
        ("code ", "message"),
        ("code", ""),
        ("code", " message"),
        (1, "message"),
        ("code", object()),
    ],
)
def test_diagnostics_reject_malformed_machine_or_human_text(
    code: object,
    message: object,
) -> None:
    """Require stable nonblank strings without silently normalizing diagnostic text."""

    with pytest.raises(ValueError):
        ProofDiagnostic(code=code, message=message)  # type: ignore[arg-type]


def test_result_rejects_inconsistent_or_incomplete_states(
    ternary_symbols: Variables,
) -> None:
    """Reject result objects whose status lacks its required evidence."""

    x, _, _ = ternary_symbols
    target = _polynomial(x, ternary_symbols)
    diagnostic = ProofDiagnostic(code="test.unknown", message="No proof found.")

    with pytest.raises(ValueError):
        ProofResult(target=target, status=ProofStatus.PROVED)
    with pytest.raises(ValueError):
        ProofResult(target=target, status=ProofStatus.UNKNOWN)
    with pytest.raises(ValueError):
        ProofResult(
            target=target,
            status=ProofStatus.UNKNOWN,
            method="monomial",
            diagnostics=(diagnostic,),
        )
    with pytest.raises(ValueError):
        ProofResult(
            target=target,
            status=ProofStatus.DISPROVED,
            diagnostics=(diagnostic,),
        )
    with pytest.raises(PolynomialInputError):
        ProofResult(
            target=object(),  # type: ignore[arg-type]
            status=ProofStatus.UNKNOWN,
            diagnostics=(diagnostic,),
        )


def test_disproved_results_require_independently_checked_exact_evidence(
    ternary_symbols: Variables,
) -> None:
    """Accept only a matching exact negative witness for a DISPROVED result."""

    x, _, _ = ternary_symbols
    target = _polynomial(-x, ternary_symbols)
    other_target = _polynomial(-(x**2), ternary_symbols)
    diagnostic = ProofDiagnostic(
        code="counterexample.found",
        message="An exact rational counterexample was found.",
    )
    witness = Counterexample(
        target=target,
        coordinates=(sp.S.One, sp.S.Zero, sp.S.Zero),
        value=sp.S.NegativeOne,
    )

    result = ProofResult(
        target=target,
        status=ProofStatus.DISPROVED,
        method="rational_counterexample",
        counterexample=witness,
        diagnostics=(diagnostic,),
    )

    assert result.counterexample is not None
    assert result.counterexample is not witness
    assert verify_counterexample(result.target, result.counterexample)
    assert result.counterexample.value == -1
    assert result.certificate is None
    assert result.verification is None

    foreign_witness = Counterexample(
        target=other_target,
        coordinates=(sp.S.One, sp.S.Zero, sp.S.Zero),
        value=sp.S.NegativeOne,
    )
    for fields in (
        {"method": None, "counterexample": witness},
        {"method": "wrong", "counterexample": witness},
        {"method": "rational_counterexample", "counterexample": None},
        {
            "method": "rational_counterexample",
            "counterexample": foreign_witness,
        },
    ):
        with pytest.raises(ValueError):
            ProofResult(
                target=target,
                status=ProofStatus.DISPROVED,
                diagnostics=(diagnostic,),
                **fields,
            )

    empty_certificate = DecompositionCertificate(target=target, terms=())
    with pytest.raises(ValueError, match="proof evidence"):
        ProofResult(
            target=target,
            status=ProofStatus.DISPROVED,
            method="rational_counterexample",
            certificate=empty_certificate,
            counterexample=witness,
            diagnostics=(diagnostic,),
        )


def test_results_reject_counterexamples_for_other_statuses_and_forged_evidence(
    ternary_symbols: Variables,
) -> None:
    """Keep witness evidence status-specific and resilient to bypassed constructors."""

    x, _, _ = ternary_symbols
    negative_target = _polynomial(-x, ternary_symbols)
    positive_target = _polynomial(x, ternary_symbols)
    diagnostic = ProofDiagnostic(code="test.result", message="Test evidence.")
    witness = Counterexample(
        target=negative_target,
        coordinates=(sp.S.One, sp.S.Zero, sp.S.Zero),
        value=sp.S.NegativeOne,
    )

    with pytest.raises(ValueError, match="counterexample"):
        ProofResult(
            target=negative_target,
            status=ProofStatus.UNKNOWN,
            counterexample=witness,
            diagnostics=(diagnostic,),
        )

    component = MonomialComponent(exponent=(1, 0, 0), variables=ternary_symbols)
    certificate = DecompositionCertificate(
        target=positive_target,
        terms=(WeightedComponent(weight=1, component=component),),
    )
    with pytest.raises(ValueError, match="counterexample"):
        ProofResult(
            target=positive_target,
            status=ProofStatus.PROVED,
            method="monomial",
            certificate=certificate,
            verification=verify_certificate(certificate),
            counterexample=witness,
        )

    forged = object.__new__(Counterexample)
    object.__setattr__(forged, "target", negative_target)
    object.__setattr__(forged, "coordinates", (sp.S.One, sp.S.Zero, sp.S.Zero))
    object.__setattr__(forged, "value", sp.Integer(-2))
    missing_fields = object.__new__(Counterexample)
    for forged_witness in (forged, missing_fields):
        with pytest.raises(ValueError, match="exact counterexample"):
            ProofResult(
                target=negative_target,
                status=ProofStatus.DISPROVED,
                method="rational_counterexample",
                counterexample=forged_witness,
                diagnostics=(diagnostic,),
            )


def test_proved_result_rechecks_its_certificate_and_method(
    ternary_symbols: Variables,
) -> None:
    """Prevent a valid-looking report or unsupported label from forging a proof."""

    x, _, _ = ternary_symbols
    target = _polynomial(x**2, ternary_symbols)
    component = MonomialComponent(exponent=(2, 0, 0), variables=ternary_symbols)
    valid_certificate = DecompositionCertificate(
        target=target,
        terms=(WeightedComponent(weight=1, component=component),),
    )
    valid_report = verify_certificate(valid_certificate)
    invalid_certificate = DecompositionCertificate(target=target, terms=())

    with pytest.raises(ValueError):
        ProofResult(
            target=target,
            status=ProofStatus.PROVED,
            method="monomial",
            certificate=invalid_certificate,
            verification=valid_report,
        )
    with pytest.raises(ValueError, match="unsupported proof method"):
        ProofResult(
            target=target,
            status=ProofStatus.PROVED,
            method="forged",
            certificate=valid_certificate,
            verification=valid_report,
        )


def test_proved_result_rejects_a_mutable_issue_alias(
    ternary_symbols: Variables,
) -> None:
    """Reject a report whose caller-owned issue list could mutate a frozen result."""

    x, _, _ = ternary_symbols
    target = _polynomial(x, ternary_symbols)
    component = MonomialComponent(exponent=(1, 0, 0), variables=ternary_symbols)
    certificate = DecompositionCertificate(
        target=target,
        terms=(WeightedComponent(weight=1, component=component),),
    )
    mutable_issues: list[VerificationIssue] = []
    malformed_report = VerificationReport(
        valid=True,
        issues=mutable_issues,  # type: ignore[arg-type]
        reconstructed=target,
        residual=_polynomial(0, ternary_symbols),
    )

    with pytest.raises(ValueError, match="valid verification report"):
        ProofResult(
            target=target,
            status=ProofStatus.PROVED,
            method="monomial",
            certificate=certificate,
            verification=malformed_report,
        )


@pytest.mark.parametrize("invalid", [None, object(), 1, True, "x", {}, ()])
def test_prove_rejects_inputs_outside_the_exact_polynomial_model(
    invalid: object,
) -> None:
    """Keep parsing failures distinct from mathematically inconclusive proof attempts."""

    with pytest.raises(PolynomialInputError):
        prove(invalid)  # type: ignore[arg-type]


def test_prove_rejects_a_raw_sympy_expression() -> None:
    """Require callers to supply explicit ordered variables through the shared model."""

    x = sp.Symbol("x")

    with pytest.raises(PolynomialInputError):
        prove(x**2)  # type: ignore[arg-type]


def test_prove_canonicalizes_a_valid_polynomial_subclass(
    ternary_symbols: Variables,
) -> None:
    """Copy an accepted model subclass so exact verification uses the base value type."""

    class DerivedPolynomial(HomogeneousPolynomial):
        """Exercise a caller-defined subtype of the immutable polynomial model."""

    x, y, _ = ternary_symbols
    supplied = DerivedPolynomial.from_expr(
        (x - y) ** 2,
        variables=ternary_symbols,
    )
    expected = _polynomial(supplied.to_sympy(), ternary_symbols)

    result = prove(supplied)

    _assert_proved(result, expected, method="exact_square")
    assert type(result.target) is HomogeneousPolynomial
    assert result.target.variables == supplied.variables
    assert result.target.coefficients == supplied.coefficients


def test_zero_uses_a_verified_empty_certificate(ternary_symbols: Variables) -> None:
    """Recognize the empty nonnegative sum before every nonzero proof family."""

    target = _polynomial(0, ternary_symbols)

    result = prove(target)

    certificate = _assert_proved(result, target, method="zero")
    assert certificate.terms == ()
    assert _diagnostic_codes(result) == ("zero.matched", "verification.passed")


@pytest.mark.parametrize(
    ("expression_factory", "expected_exponent", "expected_weight"),
    [
        (lambda x, y, z: sp.Rational(7, 9), (0, 0, 0), sp.Rational(7, 9)),
        (
            lambda x, y, z: sp.Rational(5, 7) * y**3 * z**2,
            (0, 3, 2),
            sp.Rational(5, 7),
        ),
        (lambda x, y, z: 11 * x**2, (2, 0, 0), sp.Integer(11)),
    ],
)
def test_positive_constants_and_single_monomials_use_one_monomial_component(
    expression_factory: Callable[[sp.Symbol, sp.Symbol, sp.Symbol], sp.Expr],
    expected_exponent: tuple[int, int, int],
    expected_weight: sp.Rational,
    ternary_symbols: Variables,
) -> None:
    """Prefer the direct one-term proof and preserve its exact rational coefficient."""

    target = _polynomial(expression_factory(*ternary_symbols), ternary_symbols)

    result = prove(target)

    certificate = _assert_proved(result, target, method="monomial")
    assert len(certificate.terms) == 1
    term = certificate.terms[0]
    assert term.weight == expected_weight
    assert type(term.component) is MonomialComponent
    assert term.component.exponent == expected_exponent
    assert term.component.variables == ternary_symbols
    assert _diagnostic_codes(result)[-2:] == (
        "monomial.matched",
        "verification.passed",
    )


def test_nonnegative_coefficients_produce_sorted_exact_monomials(
    ternary_symbols: Variables,
) -> None:
    """Decompose sparse and dense positive coefficient maps in canonical exponent order."""

    x, y, z = ternary_symbols
    variables = (z, x, y)
    sparse_terms = {
        (4, 0, 0): sp.Rational(2, 3),
        (1, 2, 1): sp.Rational(5, 7),
        (0, 0, 4): sp.Integer(9),
    }
    dense_terms = {
        exponent: sp.Rational(index + 1, index + 2)
        for index, exponent in enumerate(
            exponent
            for exponent_row in triangle_exponents(3)
            for exponent in exponent_row
        )
    }

    for terms in (sparse_terms, dense_terms):
        target = HomogeneousPolynomial.from_terms(terms, variables=variables)

        result = prove(target, options=_direct_only_options())

        certificate = _assert_proved(
            result,
            target,
            method="nonnegative_coefficients",
        )
        expected_exponents = tuple(sorted(terms, reverse=True))
        assert (
            tuple(term.component.exponent for term in certificate.terms)
            == expected_exponents
        )
        assert tuple(term.weight for term in certificate.terms) == tuple(
            target.coefficient(exponent) for exponent in expected_exponents
        )
        assert all(
            type(term.component) is MonomialComponent
            and term.component.variables == variables
            for term in certificate.terms
        )
        assert _diagnostic_codes(result)[-2:] == (
            "coefficients.matched",
            "verification.passed",
        )


@pytest.mark.parametrize(
    "factor_factory",
    [
        lambda x, y, z: x - 2 * y,
        lambda x, y, z: x + y - z,
        lambda x, y, z: sp.Rational(1, 2) * x - sp.Rational(2, 3) * y + z,
        lambda x, y, z: x**2 + x * y - y**2 + z**2,
        lambda x, y, z: x**2 + y**2 + z**2,
    ],
)
def test_exact_squares_with_linear_rational_and_nonlinear_factors_are_proved(
    factor_factory: Callable[[sp.Symbol, sp.Symbol, sp.Symbol], sp.Expr],
    ternary_symbols: Variables,
) -> None:
    """Recover one rational homogeneous square without restricting its factor pattern."""

    factor = factor_factory(*ternary_symbols)
    target = _polynomial(factor**2, ternary_symbols)

    result = prove(target, options=_direct_only_options())

    certificate = _assert_proved(result, target, method="exact_square")
    assert len(certificate.terms) == 1
    term = certificate.terms[0]
    assert type(term.component) is SquareComponent
    assert term.component.multiplier == (0, 0, 0)
    assert term.component.degree == target.degree
    assert not term.component.factor.to_sympy().atoms(sp.Float)
    assert _diagnostic_codes(result)[-2:] == (
        "square.matched",
        "verification.passed",
    )


def test_square_normalization_restores_rational_scalar_and_odd_monomial_shift(
    ternary_symbols: Variables,
) -> None:
    """Lift a reduced square back to the exact original coefficient content and degree."""

    x, y, z = ternary_symbols
    scalar = sp.Rational(10, 7)
    target = _polynomial(scalar * x * y**2 * (-x + 2 * z) ** 2, ternary_symbols)

    result = prove(target, options=_direct_only_options())

    certificate = _assert_proved(result, target, method="exact_square")
    assert len(certificate.terms) == 1
    term = certificate.terms[0]
    assert term.weight == scalar
    assert type(term.component) is SquareComponent
    assert term.component.multiplier == (1, 2, 0)
    assert term.component.degree == 5
    assert sp.expand(term.component.factor.to_sympy() - (x - 2 * z)) == 0
    first_coefficient = next(iter(term.component.factor.coefficients.values()))
    assert first_coefficient > 0
    assert certificate.target.coefficients == target.coefficients
    assert not certificate.target.to_sympy().atoms(sp.Float)


def test_normalized_component_lifting_adds_an_existing_multiplier(
    ternary_symbols: Variables,
) -> None:
    """Preserve a candidate's shift when restoring the target's common monomial."""

    from triangle_method.recognition import _lift_normalized_component

    x, y, _ = ternary_symbols
    factor = _polynomial(x - y, ternary_symbols)
    normalization = Normalization(
        scalar=sp.Rational(3, 7),
        monomial=(0, 2, 1),
        reduced=factor,
    )
    component = SquareComponent(
        factor=factor,
        multiplier=(1, 0, 0),
    )

    weighted = _lift_normalized_component(normalization, component)

    assert weighted.weight == sp.Rational(3, 7)
    assert type(weighted.component) is SquareComponent
    assert weighted.component.multiplier == (1, 2, 1)
    assert component.multiplier == (1, 0, 0)


def test_exact_rational_unit_square_root_uses_integer_arithmetic() -> None:
    """Distinguish square, nonsquare, and negative rational units without approximation."""

    from triangle_method.recognition import _exact_rational_square_root

    assert _exact_rational_square_root(sp.Rational(4, 9)) == sp.Rational(2, 3)
    assert _exact_rational_square_root(sp.Integer(49)) == sp.Integer(7)
    assert _exact_rational_square_root(sp.Rational(2, 3)) is None
    assert _exact_rational_square_root(sp.Rational(-4, 9)) is None


@pytest.mark.parametrize(
    "expression_factory",
    [
        lambda x, y, z: -((x - y) ** 2),
        lambda x, y, z: (x - y) ** 2 + y**2,
        lambda x, y, z: x**2 - x * y + y**2,
    ],
)
def test_negative_and_near_square_inputs_do_not_match_direct_square_recognition(
    expression_factory: Callable[[sp.Symbol, sp.Symbol, sp.Symbol], sp.Expr],
    ternary_symbols: Variables,
) -> None:
    """Treat a direct square mismatch as inconclusive when later phases are disabled."""

    target = _polynomial(expression_factory(*ternary_symbols), ternary_symbols)

    result = prove(target, options=_direct_only_options())

    _assert_unknown(result, target)
    assert "square.not_exact" in _diagnostic_codes(result)
    assert result.status is not ProofStatus.DISPROVED


def test_square_preflight_limit_is_distinct_from_an_exact_mismatch(
    ternary_symbols: Variables,
) -> None:
    """Skip an otherwise exact high-degree square at the documented structural limit."""

    x, y, _ = ternary_symbols
    target = _polynomial((x**7 - y**7) ** 2, ternary_symbols)

    result = prove(target, options=_direct_only_options())

    _assert_unknown(result, target)
    codes = _diagnostic_codes(result)
    assert "square.limit_exceeded" in codes
    assert "square.matched" not in codes
    assert result.status is not ProofStatus.DISPROVED


@pytest.mark.parametrize(
    "factorization_error",
    [
        PolynomialError("forced exact factorization failure"),
        PolynomialError(),
        NotImplementedError("  unavailable  "),
    ],
)
def test_square_factorization_failure_is_reported_as_inconclusive(
    factorization_error: Exception,
    monkeypatch: pytest.MonkeyPatch,
    ternary_symbols: Variables,
) -> None:
    """Convert a supported exact factorization failure into a stable UNKNOWN diagnostic."""

    import triangle_method.recognition as recognition

    x, y, _ = ternary_symbols
    target = _polynomial((x - y) ** 2, ternary_symbols)

    def fail_factorization(polynomial: HomogeneousPolynomial) -> object:
        """Force the narrow SymPy failure handled by square recognition."""

        raise factorization_error

    monkeypatch.setattr(recognition, "_square_free_decomposition", fail_factorization)

    result = prove(target, options=_direct_only_options())

    _assert_unknown(result, target)
    codes = _diagnostic_codes(result)
    assert "square.factorization_failed" in codes
    assert "square.limit_exceeded" not in codes
    assert "square.matched" not in codes


def test_empty_verifier_exception_detail_still_returns_unknown(
    monkeypatch: pytest.MonkeyPatch,
    ternary_symbols: Variables,
) -> None:
    """Turn an empty expected verifier exception into a well-formed diagnostic."""

    import triangle_method.proof as proof_module

    x, _, _ = ternary_symbols
    target = _polynomial(x**2, ternary_symbols)

    def reject_without_detail(certificate: DecompositionCertificate) -> object:
        """Raise an expected certificate error without human-readable text."""

        raise CertificateInputError

    monkeypatch.setattr(proof_module, "verify_certificate", reject_without_detail)

    result = prove(target)

    assert result.status is ProofStatus.UNKNOWN
    assert result.method is None
    assert result.certificate is None
    assert result.verification is None
    assert _diagnostic_codes(result)[-1] == "verification.failed"
    assert result.diagnostics[-1].message.endswith("no additional detail")


@pytest.mark.parametrize("degree", [3, 4, 5])
def test_classic_schur_degrees_three_four_and_five_are_proved(
    degree: int,
    ternary_symbols: Variables,
) -> None:
    """Match exactly one unit-argument Schur component at the reduced target degree."""

    target = _polynomial(_classic_schur(degree, ternary_symbols), ternary_symbols)

    result = prove(target)

    certificate = _assert_proved(result, target, method="classic_schur")
    assert len(certificate.terms) == 1
    term = certificate.terms[0]
    assert term.weight == 1
    assert type(term.component) is SchurComponent
    assert term.component.schur_degree == degree
    assert term.component.arguments == ((1, 0, 0), (0, 1, 0), (0, 0, 1))
    assert term.component.multiplier == (0, 0, 0)
    assert _diagnostic_codes(result)[-2:] == (
        "schur.matched",
        "verification.passed",
    )


def test_schur_normalization_preserves_scalar_shift_and_declared_variable_order(
    ternary_symbols: Variables,
) -> None:
    """Lift classic Schur in a nonalphabetic basis back to its exact original target."""

    x, y, z = ternary_symbols
    variables = (z, x, y)
    first, second, _ = variables
    scalar = sp.Rational(7, 11)
    expression = scalar * first * second**2 * _classic_schur(4, variables)
    target = _polynomial(expression, variables)

    result = prove(target)

    certificate = _assert_proved(result, target, method="classic_schur")
    term = certificate.terms[0]
    assert term.weight == scalar
    assert type(term.component) is SchurComponent
    assert term.component.variables == variables
    assert term.component.schur_degree == 4
    assert term.component.multiplier == (1, 2, 0)
    assert term.component.degree == target.degree
    assert certificate.target.variables == variables
    assert certificate.target.coefficients == target.coefficients


def test_near_schur_and_substitution_do_not_match_direct_schur_recognition(
    ternary_symbols: Variables,
) -> None:
    """Keep altered and substituted forms outside direct unit-argument matching."""

    x, y, z = ternary_symbols
    targets = (
        _polynomial(_classic_schur(5, ternary_symbols) + x**5, ternary_symbols),
        _polynomial(
            _substituted_schur(3, (x * y, y * z, z * x)),
            ternary_symbols,
        ),
    )

    for target in targets:
        result = prove(target, options=_direct_only_options())

        _assert_unknown(result, target)
        assert "schur.not_classic" in _diagnostic_codes(result)
        assert result.status is not ProofStatus.DISPROVED


def test_seven_approved_examples_are_proved_by_direct_or_combination_methods(
    ternary_symbols: Variables,
    approved_polynomial_cases: tuple[Any, ...],
) -> None:
    """Prove the complete corpus while retaining direct Schur precedence."""

    expected = {
        "quadratic_squares": (ProofStatus.PROVED, "candidate_combination"),
        "cubic_schur": (ProofStatus.PROVED, "classic_schur"),
        "quintic_schur": (ProofStatus.PROVED, "classic_schur"),
        "cubic_weighted_squares": (ProofStatus.PROVED, "candidate_combination"),
        "quartic_squares": (ProofStatus.PROVED, "candidate_combination"),
        "quartic_schur_lift": (ProofStatus.PROVED, "candidate_combination"),
        "quintic_schur_plus_squares": (
            ProofStatus.PROVED,
            "candidate_combination",
        ),
    }

    for case in approved_polynomial_cases:
        target = _polynomial(case.expression, ternary_symbols)

        result = prove(target)

        expected_status, expected_method = expected[case.name]
        assert result.status is expected_status, case.name
        assert result.method == expected_method, case.name
        assert result.status is not ProofStatus.DISPROVED, case.name
        _assert_proved(result, target, method=expected_method)


@pytest.mark.parametrize(
    ("method", "expression_factory"),
    [
        ("zero", lambda x, y, z: 0),
        ("monomial", lambda x, y, z: 2 * x**3),
        ("classic_schur", lambda x, y, z: _classic_schur(3, (x, y, z))),
        ("exact_square", lambda x, y, z: (x - y) ** 2),
        ("nonnegative_coefficients", lambda x, y, z: x**2 + y**2),
    ],
)
def test_every_success_family_fails_closed_when_the_verifier_rejects_it(
    method: str,
    expression_factory: Callable[[sp.Symbol, sp.Symbol, sp.Symbol], sp.Expr],
    monkeypatch: pytest.MonkeyPatch,
    ternary_symbols: Variables,
) -> None:
    """Route every proposed family through one gate that cannot emit an unverified proof."""

    import triangle_method.proof as proof_module

    target = _polynomial(expression_factory(*ternary_symbols), ternary_symbols)
    calls: list[DecompositionCertificate] = []

    def reject_certificate(
        certificate: DecompositionCertificate,
    ) -> VerificationReport:
        """Record the proposed certificate and force an invalid verification report."""

        calls.append(certificate)
        return VerificationReport(
            valid=False,
            issues=(
                VerificationIssue(
                    code="test.forced_rejection",
                    message="The test verifier rejected this candidate.",
                ),
            ),
            reconstructed=None,
            residual=None,
        )

    monkeypatch.setattr(proof_module, "verify_certificate", reject_certificate)

    result = prove(target)

    assert len(calls) == 1, method
    assert calls[0].target == target
    assert result.status is ProofStatus.UNKNOWN
    assert result.method is None
    assert result.certificate is None
    assert result.verification is None
    assert _diagnostic_codes(result)[-1] == "verification.failed"
    assert "verification.passed" not in _diagnostic_codes(result)
    assert "direct.no_match" not in _diagnostic_codes(result)


def test_prove_rejects_a_report_that_claims_success_while_listing_issues(
    monkeypatch: pytest.MonkeyPatch,
    ternary_symbols: Variables,
) -> None:
    """Fail closed when a malformed verifier report contradicts its valid flag."""

    import triangle_method.proof as proof_module

    x, _, _ = ternary_symbols
    target = _polynomial(x**2, ternary_symbols)
    zero = _polynomial(0, ternary_symbols)

    def return_contradictory_report(
        certificate: DecompositionCertificate,
    ) -> VerificationReport:
        """Return exact-looking data together with an issue that invalidates it."""

        return VerificationReport(
            valid=True,
            issues=(
                VerificationIssue(
                    code="test.contradictory_report",
                    message="A valid report cannot contain an issue.",
                ),
            ),
            reconstructed=certificate.target,
            residual=zero,
        )

    monkeypatch.setattr(
        proof_module,
        "verify_certificate",
        return_contradictory_report,
    )

    result = prove(target)

    assert result.status is ProofStatus.UNKNOWN
    assert result.certificate is None
    assert result.verification is None
    assert _diagnostic_codes(result)[-1] == "verification.failed"
    assert "test.contradictory_report" in result.diagnostics[-1].message


def test_repeated_proofs_are_deterministic_and_do_not_mutate_the_target(
    ternary_symbols: Variables,
) -> None:
    """Return equal results and byte-identical certificate JSON from unchanged input."""

    x, y, z = ternary_symbols
    target = _polynomial(
        sp.Rational(3, 5) * x * (x + y - z) ** 2,
        ternary_symbols,
    )
    original_coefficients = dict(target.coefficients)
    original_expression = target.to_sympy()

    first = prove(target)
    second = prove(target)

    _assert_proved(first, target, method="exact_square")
    _assert_proved(second, target, method="exact_square")
    assert first == second
    assert first.diagnostics == second.diagnostics
    assert first.certificate is not None
    assert second.certificate is not None
    assert first.certificate.to_json() == second.certificate.to_json()
    assert dict(target.coefficients) == original_coefficients
    assert target.to_sympy() == original_expression


def test_negative_constants_and_monomials_return_exact_counterexamples(
    ternary_symbols: Variables,
) -> None:
    """Complete DISPROVED results with exact negative simplex evidence."""

    x, _, _ = ternary_symbols
    for expression in (-1, -(x**5)):
        target = _polynomial(expression, ternary_symbols)

        result = prove(target)

        assert result.status is ProofStatus.DISPROVED
        assert result.method == "rational_counterexample"
        assert result.certificate is None
        assert result.verification is None
        assert result.counterexample is not None
        assert verify_counterexample(target, result.counterexample)
        assert result.counterexample.value < 0
        assert _diagnostic_codes(result)[-1] == "counterexample.found"


def test_proving_imports_no_numerical_solver_in_an_isolated_interpreter(
    tmp_path: Path,
) -> None:
    """Keep direct and default exact combination proving independent from SciPy."""

    script = textwrap.dedent(
        """
        import sys
        import sympy as sp
        from triangle_method import (
            HomogeneousPolynomial,
            ProofStatus,
            prove,
            verify_certificate,
        )

        x, y, z = sp.symbols("x y z")
        variables = (x, y, z)
        targets = (
            HomogeneousPolynomial.from_expr((x-y)**2, variables=variables),
            HomogeneousPolynomial.from_expr(
                x*(x**3+y**3+z**3+3*x*y*z-x**2*y-x**2*z
                   -x*y**2-x*z**2-y**2*z-y*z**2),
                variables=variables,
            ),
            HomogeneousPolynomial.from_expr(
                x**2+y**2+z**2-x*y-x*z-y*z,
                variables=variables,
            ),
        )
        for target in targets:
            result = prove(target)
            assert result.status is ProofStatus.PROVED
            assert result.certificate is not None
            assert verify_certificate(result.certificate).valid
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

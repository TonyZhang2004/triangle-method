"""End-to-end tests for the proof, combination, and counterexample backend."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest
import sympy as sp

from triangle_method import (
    CandidateGenerationLimits,
    CombinationSearchLimits,
    CombinationSearchResult,
    CombinationSearchStatus,
    CounterexampleSearchLimits,
    HomogeneousPolynomial,
    ProofDiagnostic,
    ProofSearchOptions,
    ProofStatus,
    SolverBackend,
    VerificationIssue,
    VerificationReport,
    prove,
    verify_certificate,
    verify_counterexample,
)

Variables = tuple[sp.Symbol, sp.Symbol, sp.Symbol]


def _target(expression: object, variables: Variables) -> HomogeneousPolynomial:
    """Construct one exact homogeneous target in the declared variable order."""
    return HomogeneousPolynomial.from_expr(expression, variables=variables)


def _codes(result: object) -> tuple[str, ...]:
    """Return stable diagnostic codes from a public proof result."""
    return tuple(diagnostic.code for diagnostic in result.diagnostics)


def _bounded_options(
    *,
    max_candidates: int = 10_000,
    generation_seconds: float = 5,
    solver_seconds: float = 5,
    max_pivots: int = 10_000,
    max_points: int = 100,
) -> ProofSearchOptions:
    """Build exact-only options with small deterministic test budgets."""
    return ProofSearchOptions(
        candidate_limits=CandidateGenerationLimits(
            max_candidates=max_candidates,
            max_seconds=generation_seconds,
        ),
        combination_limits=CombinationSearchLimits(
            max_seconds=solver_seconds,
            max_pivots=max_pivots,
            backend=SolverBackend.EXACT,
        ),
        counterexample_limits=CounterexampleSearchLimits(
            max_denominator=3,
            max_points=max_points,
        ),
    )


def test_proof_search_options_are_typed_frozen_and_keyword_only() -> None:
    """Expose one immutable configuration object for every automatic backend phase."""
    options = ProofSearchOptions()

    assert type(options.candidate_limits) is CandidateGenerationLimits
    assert type(options.combination_limits) is CombinationSearchLimits
    assert type(options.counterexample_limits) is CounterexampleSearchLimits
    assert options.enable_combination_search
    assert options.enable_counterexample_search
    with pytest.raises(FrozenInstanceError):
        options.enable_combination_search = False  # type: ignore[misc]
    with pytest.raises(TypeError):
        ProofSearchOptions(False)  # type: ignore[misc]

    for malformed in (
        {"candidate_limits": object()},
        {"combination_limits": object()},
        {"counterexample_limits": object()},
        {"enable_combination_search": 1},
        {"enable_counterexample_search": 0},
    ):
        with pytest.raises(ValueError):
            ProofSearchOptions(**malformed)  # type: ignore[arg-type]


def test_default_prover_returns_a_verified_candidate_combination(
    ternary_symbols: Variables,
) -> None:
    """Solve the motivating quadratic through the complete public backend path."""
    x, y, z = ternary_symbols
    target = _target(
        x**2 + y**2 + z**2 - x * y - x * z - y * z,
        ternary_symbols,
    )

    result = prove(target)

    assert result.status is ProofStatus.PROVED
    assert result.method == "candidate_combination"
    assert result.certificate is not None
    assert result.verification is not None and result.verification.valid
    assert result.counterexample is None
    assert len(result.certificate.terms) == 3
    assert all(term.weight == sp.Rational(1, 2) for term in result.certificate.terms)
    assert verify_certificate(result.certificate).valid
    assert "direct.no_match" in _codes(result)
    assert "combination.matched" in _codes(result)
    assert _codes(result)[-1] == "verification.passed"


def test_default_prover_returns_an_exact_rational_counterexample(
    ternary_symbols: Variables,
) -> None:
    """Refute a false quadratic only after an exact simplex reevaluation."""
    x, y, z = ternary_symbols
    target = _target(x**2 + y**2 + z**2 - 4 * x * y, ternary_symbols)

    result = prove(target)

    assert result.status is ProofStatus.DISPROVED
    assert result.method == "rational_counterexample"
    assert result.certificate is None
    assert result.verification is None
    assert result.counterexample is not None
    assert result.counterexample.coordinates == (
        sp.Rational(1, 2),
        sp.Rational(1, 2),
        sp.S.Zero,
    )
    assert result.counterexample.value == sp.Rational(-1, 2)
    assert verify_counterexample(target, result.counterexample)
    assert "combination.exact.infeasible_in_library" in _codes(result)
    assert _codes(result)[-1] == "counterexample.found"


def test_finite_search_exhaustion_returns_unknown_without_evidence(
    ternary_symbols: Variables,
) -> None:
    """Keep an exhausted finite cone and rational grid mathematically inconclusive."""
    x, y, _ = ternary_symbols
    target = _target(x**2 - x * y + y**2, ternary_symbols)

    result = prove(target, options=_bounded_options(max_candidates=0))

    assert result.status is ProofStatus.UNKNOWN
    assert result.method is None
    assert result.certificate is None
    assert result.verification is None
    assert result.counterexample is None
    assert "candidates.incomplete.candidate_limit" in _codes(result)
    assert "combination.exact.infeasible_in_library" in _codes(result)
    assert _codes(result)[-1] == "counterexample.exhausted"


def test_incomplete_candidate_prefix_can_still_produce_a_verified_proof(
    ternary_symbols: Variables,
) -> None:
    """Accept a proof found before generation reaches its configured column cap."""
    x, y, _ = ternary_symbols
    target = _target(
        2 * x**2 - x * y + sp.Rational(1, 4) * y**2,
        ternary_symbols,
    )

    result = prove(target, options=_bounded_options(max_candidates=7))

    assert result.status is ProofStatus.PROVED
    assert result.method == "candidate_combination"
    assert result.certificate is not None
    assert verify_certificate(result.certificate).valid
    assert "candidates.incomplete.candidate_limit" in _codes(result)
    assert "combination.matched" in _codes(result)


@pytest.mark.parametrize(
    ("options", "expected_code"),
    [
        (
            _bounded_options(generation_seconds=0),
            "candidates.incomplete.time_limit",
        ),
        (
            _bounded_options(max_pivots=0),
            "combination.exact.pivot_limit",
        ),
        (
            _bounded_options(solver_seconds=0),
            "combination.exact.time_limit",
        ),
    ],
)
def test_backend_limits_cannot_become_disproofs(
    options: ProofSearchOptions,
    expected_code: str,
    ternary_symbols: Variables,
) -> None:
    """Report generation and exact-solver stops as UNKNOWN after a finite point scan."""
    x, y, z = ternary_symbols
    target = _target(
        x**2 + y**2 + z**2 - x * y - x * z - y * z,
        ternary_symbols,
    )

    result = prove(target, options=options)

    assert result.status is ProofStatus.UNKNOWN
    assert result.counterexample is None
    assert expected_code in _codes(result)
    assert _codes(result)[-1] == "counterexample.exhausted"


def test_point_limit_cannot_turn_a_negative_target_into_disproved(
    ternary_symbols: Variables,
) -> None:
    """Require an evaluated witness even when finite-cone infeasibility is exact."""
    x, _, _ = ternary_symbols
    target = _target(-x, ternary_symbols)

    result = prove(target, options=_bounded_options(max_points=0))

    assert result.status is ProofStatus.UNKNOWN
    assert result.counterexample is None
    assert "combination.exact.infeasible_in_library" in _codes(result)
    assert _codes(result)[-1] == "counterexample.point_limit"


def test_combination_proposals_still_fail_closed_at_the_verifier(
    monkeypatch: pytest.MonkeyPatch,
    ternary_symbols: Variables,
) -> None:
    """Prevent an exact solver proposal from bypassing certificate verification."""
    import triangle_method.proof as proof_module

    x, y, z = ternary_symbols
    target = _target(
        x**2 + y**2 + z**2 - x * y - x * z - y * z,
        ternary_symbols,
    )

    def reject_certificate(certificate: object) -> VerificationReport:
        """Force rejection after the combination solver proposes exact terms."""
        return VerificationReport(
            valid=False,
            issues=(
                VerificationIssue(
                    code="test.rejected_combination",
                    message="The test rejected this combination.",
                ),
            ),
            reconstructed=None,
            residual=None,
        )

    monkeypatch.setattr(proof_module, "verify_certificate", reject_certificate)

    result = prove(target, options=_bounded_options())

    assert result.status is ProofStatus.UNKNOWN
    assert result.certificate is None
    assert result.verification is None
    assert result.counterexample is None
    assert _codes(result)[-1] == "verification.failed"
    assert "counterexample.found" not in _codes(result)


def test_solver_owned_residual_cannot_manufacture_a_proof(
    monkeypatch: pytest.MonkeyPatch,
    ternary_symbols: Variables,
) -> None:
    """Reconstruct proposed terms even when a solver record falsely claims zero."""
    import triangle_method.proof as proof_module

    x, y, z = ternary_symbols
    target = _target(
        x**2 + y**2 + z**2 - x * y - x * z - y * z,
        ternary_symbols,
    )

    def return_wrong_weights(library, limits=None):
        """Claim feasibility with same-length weights that reconstruct zero."""
        return CombinationSearchResult(
            status=CombinationSearchStatus.FEASIBLE,
            weights=tuple(sp.S.Zero for _ in library.candidates),
            backend=SolverBackend.EXACT,
            diagnostics=(
                ProofDiagnostic(
                    code="combination.matched",
                    message="The mocked solver claims an exact match.",
                ),
            ),
            pivots=0,
            attempted_supports=1,
            exact_residual=tuple(sp.S.Zero for _ in range(6)),
        )

    monkeypatch.setattr(
        proof_module,
        "solve_candidate_combination",
        return_wrong_weights,
    )

    result = prove(target, options=_bounded_options())

    assert result.status is ProofStatus.UNKNOWN
    assert result.certificate is None
    assert result.verification is None
    assert result.counterexample is None
    assert _codes(result)[-1] == "verification.failed"


def test_auto_backend_falls_back_exactly_when_scipy_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    ternary_symbols: Variables,
) -> None:
    """Keep AUTO combination search functional without the optional solver."""
    import triangle_method.search as search_module

    x, y, z = ternary_symbols
    target = _target(
        x**2 + y**2 + z**2 - x * y - x * z - y * z,
        ternary_symbols,
    )
    monkeypatch.setattr(search_module, "_load_scipy_linprog", lambda: None)

    result = prove(
        target,
        options=ProofSearchOptions(
            combination_limits=CombinationSearchLimits(
                backend=SolverBackend.AUTO,
            )
        ),
    )

    assert result.status is ProofStatus.PROVED
    assert result.method == "candidate_combination"
    assert result.certificate is not None
    assert verify_certificate(result.certificate).valid
    assert "combination.numeric.unavailable" in _codes(result)


def test_prove_validates_its_keyword_only_options(
    ternary_symbols: Variables,
) -> None:
    """Reject malformed orchestration configuration before any backend phase runs."""
    x, _, _ = ternary_symbols
    target = _target(x, ternary_symbols)

    with pytest.raises(TypeError):
        prove(target, ProofSearchOptions())  # type: ignore[misc]
    with pytest.raises(ValueError, match="ProofSearchOptions"):
        prove(target, options=object())  # type: ignore[arg-type]

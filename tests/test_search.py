"""Exact feasibility and optional-support tests for candidate combination search."""

from __future__ import annotations

import random
from dataclasses import FrozenInstanceError
from types import SimpleNamespace
from typing import TypeAlias

import pytest
import sympy as sp

import triangle_method.search as search_module
from triangle_method import (
    CandidateGenerationLimits,
    CandidateLibrary,
    DecompositionCertificate,
    HomogeneousPolynomial,
    ProofDiagnostic,
    generate_candidates,
    triangle_exponents,
    verify_certificate,
)
from triangle_method.search import (
    CombinationSearchLimits,
    CombinationSearchResult,
    CombinationSearchStatus,
    SolverBackend,
    solve_candidate_combination,
)

Variables: TypeAlias = tuple[sp.Symbol, sp.Symbol, sp.Symbol]


def _target(expression: object, variables: Variables) -> HomogeneousPolynomial:
    """Build one exact homogeneous target in the requested variable order."""
    return HomogeneousPolynomial.from_expr(expression, variables=variables)


def _library(
    expression: object,
    variables: Variables,
    *,
    max_candidates: int = 10_000,
):
    """Generate a candidate library with a generous deterministic time budget."""
    target = _target(expression, variables)
    return generate_candidates(
        target,
        limits=CandidateGenerationLimits(
            max_candidates=max_candidates,
            max_seconds=30,
        ),
    )


def _exact_limits(**changes: object) -> CombinationSearchLimits:
    """Return exact-only limits with room for the default quintic library."""
    values = {
        "max_seconds": 10,
        "max_pivots": 10_000,
        "max_recovery_candidates": 256,
        "numerical_tolerance": 1e-9,
        "backend": SolverBackend.EXACT,
    }
    values.update(changes)
    return CombinationSearchLimits(**values)  # type: ignore[arg-type]


def _codes(result: CombinationSearchResult) -> tuple[str, ...]:
    """Return stable diagnostic codes from one combination search result."""
    return tuple(diagnostic.code for diagnostic in result.diagnostics)


def _verified_certificate(result: CombinationSearchResult, library) -> None:
    """Map exact column weights through candidate scales and verify the identity."""
    assert result.status is CombinationSearchStatus.FEASIBLE
    assert len(result.weights) == len(library.candidates)
    certificate = DecompositionCertificate(
        target=library.target,
        terms=tuple(
            candidate.weighted_component(weight)
            for candidate, weight in zip(
                library.candidates,
                result.weights,
                strict=True,
            )
            if weight
        ),
    )
    report = verify_certificate(certificate)
    assert report.valid, report.errors
    assert report.residual is not None and report.residual.is_zero


def test_search_api_has_stable_string_enums_and_frozen_limits() -> None:
    """Expose deterministic backend, status, and immutable limit vocabulary."""
    assert tuple(backend.value for backend in SolverBackend) == (
        "auto",
        "exact",
        "scipy_highs",
    )
    assert tuple(status.value for status in CombinationSearchStatus) == (
        "FEASIBLE",
        "INFEASIBLE_IN_LIBRARY",
        "LIMIT_REACHED",
        "ERROR",
    )
    limits = CombinationSearchLimits()
    assert limits.backend is SolverBackend.EXACT
    assert limits.max_pivots == 10_000
    with pytest.raises(FrozenInstanceError):
        limits.max_pivots = 1  # type: ignore[misc]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("max_seconds", -1),
        ("max_seconds", float("inf")),
        ("max_seconds", True),
        ("max_pivots", -1),
        ("max_pivots", 1.5),
        ("max_recovery_candidates", True),
        ("numerical_tolerance", 0),
        ("numerical_tolerance", float("nan")),
        ("backend", "exact"),
    ],
)
def test_search_limits_reject_malformed_values(field: str, value: object) -> None:
    """Reject ambiguous booleans, non-finite bounds, and raw backend strings."""
    with pytest.raises(ValueError):
        CombinationSearchLimits(**{field: value})


def test_search_results_copy_sequences_and_enforce_status_evidence() -> None:
    """Freeze public outcomes and reject weights or residuals for the wrong status."""
    diagnostic = ProofDiagnostic(code="test.search", message="Test search outcome.")
    caller_weights = [sp.S.Zero]
    caller_diagnostics = [diagnostic]
    caller_residual = [sp.S.Zero]
    result = CombinationSearchResult(
        status=CombinationSearchStatus.FEASIBLE,
        weights=caller_weights,  # type: ignore[arg-type]
        backend=SolverBackend.EXACT,
        diagnostics=caller_diagnostics,  # type: ignore[arg-type]
        pivots=0,
        attempted_supports=0,
        exact_residual=caller_residual,  # type: ignore[arg-type]
    )
    caller_weights.append(sp.S.One)
    caller_diagnostics.append(diagnostic)
    caller_residual.append(sp.S.One)

    assert result.weights == (sp.S.Zero,)
    assert result.diagnostics == (diagnostic,)
    assert result.exact_residual == (sp.S.Zero,)
    with pytest.raises(FrozenInstanceError):
        result.pivots = 1  # type: ignore[misc]

    common = {
        "diagnostics": (diagnostic,),
        "pivots": 0,
        "attempted_supports": 0,
    }
    invalid_states = (
        {
            "status": CombinationSearchStatus.FEASIBLE,
            "weights": (sp.S.NegativeOne,),
            "backend": SolverBackend.EXACT,
            "exact_residual": (sp.S.Zero,),
        },
        {
            "status": CombinationSearchStatus.FEASIBLE,
            "weights": (0.0,),
            "backend": SolverBackend.EXACT,
            "exact_residual": (sp.S.Zero,),
        },
        {
            "status": CombinationSearchStatus.FEASIBLE,
            "weights": (sp.S.Zero,),
            "backend": SolverBackend.AUTO,
            "exact_residual": (sp.S.Zero,),
        },
        {
            "status": CombinationSearchStatus.FEASIBLE,
            "weights": (sp.S.Zero,),
            "backend": SolverBackend.EXACT,
            "exact_residual": (),
        },
        {
            "status": CombinationSearchStatus.FEASIBLE,
            "weights": (sp.S.Zero,),
            "backend": SolverBackend.EXACT,
            "exact_residual": (sp.S.One,),
        },
        {
            "status": CombinationSearchStatus.INFEASIBLE_IN_LIBRARY,
            "weights": (sp.S.Zero,),
            "backend": SolverBackend.EXACT,
            "exact_residual": None,
        },
        {
            "status": CombinationSearchStatus.ERROR,
            "weights": (),
            "backend": SolverBackend.EXACT,
            "exact_residual": (sp.S.Zero,),
        },
    )
    for state in invalid_states:
        with pytest.raises(ValueError):
            CombinationSearchResult(**common, **state)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="diagnostics"):
        CombinationSearchResult(
            status=CombinationSearchStatus.ERROR,
            weights=(),
            backend=SolverBackend.EXACT,
            diagnostics=(),
            pivots=0,
            attempted_supports=0,
            exact_residual=None,
        )


@pytest.mark.parametrize(
    "expression_factory",
    [
        lambda x, y, z: x**2 + y**2 + z**2 - x * y - x * z - y * z,
        lambda x, y, z: (
            x**2 * y
            + x * y**2
            + y**2 * z
            + y * z**2
            + z**2 * x
            + z * x**2
            - 6 * x * y * z
        ),
        lambda x, y, z: x**4 + y**4 + z**4 - x**2 * y**2 - y**2 * z**2 - z**2 * x**2,
        lambda x, y, z: (
            x**4
            + y**4
            + z**4
            + x**2 * y * z
            + x * y**2 * z
            + x * y * z**2
            - 2 * x**2 * y**2
            - 2 * y**2 * z**2
            - 2 * z**2 * x**2
        ),
        lambda x, y, z: (
            x**5
            + y**5
            + z**5
            - x**4 * y
            - x**4 * z
            - x * y**4
            - y**4 * z
            - x * z**4
            - y * z**4
            + 2 * x**3 * y * z
            + 2 * x * y**3 * z
            + 2 * x * y * z**3
            - x**2 * y**2 * z
            - x**2 * y * z**2
            - x * y**2 * z**2
        ),
    ],
)
def test_exact_search_proves_the_five_combination_corpus_cases(
    expression_factory,
    ternary_symbols: Variables,
) -> None:
    """Recover exact verified combinations through the default quintic library."""
    library = _library(expression_factory(*ternary_symbols), ternary_symbols)

    result = solve_candidate_combination(library, _exact_limits())

    assert result.status is CombinationSearchStatus.FEASIBLE
    assert result.backend is SolverBackend.EXACT
    assert result.pivots <= 10_000
    assert result.attempted_supports == 1
    assert result.exact_residual is not None
    assert not any(result.exact_residual)
    assert _codes(result) == ("combination.matched",)
    _verified_certificate(result, library)


def test_seeded_generated_positive_combinations_recover_exactly(
    ternary_symbols: Variables,
) -> None:
    """Recover representative rational combinations drawn from generated libraries."""
    rng = random.Random(20_260_913)
    x, _, _ = ternary_symbols

    for degree in (2, 3, 4):
        base_library = _library(x**degree, ternary_symbols)
        exponents = tuple(
            exponent for row in triangle_exponents(degree) for exponent in row
        )
        for _ in range(8):
            support_size = rng.randint(1, min(6, len(base_library.candidates)))
            support = rng.sample(range(len(base_library.candidates)), support_size)
            input_weights = {
                candidate_index: sp.Rational(rng.randint(1, 7), rng.randint(1, 7))
                for candidate_index in support
            }
            coefficients = {}
            for row_index, exponent in enumerate(exponents):
                coefficient = sum(
                    (
                        input_weights[candidate_index]
                        * base_library.candidates[candidate_index].column[row_index]
                        for candidate_index in support
                    ),
                    sp.S.Zero,
                )
                if coefficient:
                    coefficients[exponent] = coefficient
            target = HomogeneousPolynomial.from_terms(
                coefficients,
                variables=ternary_symbols,
            )
            library = CandidateLibrary(
                target=target,
                candidates=base_library.candidates,
                limits=base_library.limits,
                metadata=base_library.metadata,
            )

            result = solve_candidate_combination(library, _exact_limits())

            assert result.status is CombinationSearchStatus.FEASIBLE
            _verified_certificate(result, library)


def test_exact_search_is_deterministic_and_preserves_rational_scale(
    ternary_symbols: Variables,
) -> None:
    """Return identical exact weights while restoring tiny rational target content."""
    x, y, z = ternary_symbols
    scale = sp.Rational(1, 10**30)
    expression = scale * (x**2 + y**2 + z**2 - x * y - x * z - y * z)
    library = _library(expression, ternary_symbols)

    first = solve_candidate_combination(library, _exact_limits())
    second = solve_candidate_combination(library, _exact_limits())

    assert first == second
    assert first.weights == second.weights
    assert all(isinstance(weight, sp.Rational) for weight in first.weights)
    assert any(weight.q >= 10**30 for weight in first.weights if weight)
    _verified_certificate(first, library)


def test_column_weights_recover_a_candidate_with_nonunit_expansion_scale(
    ternary_symbols: Variables,
) -> None:
    """Keep canonical column scaling distinct from final primitive weights."""
    x, y, _ = ternary_symbols
    expression = 2 * x**2 - x * y + sp.Rational(1, 4) * y**2
    library = _library(expression, ternary_symbols, max_candidates=7)

    result = solve_candidate_combination(library, _exact_limits())

    assert result.weights == (
        sp.S.One,
        sp.S.Zero,
        sp.S.Zero,
        sp.S.Zero,
        sp.S.Zero,
        sp.S.Zero,
        sp.Rational(1, 4),
    )
    scaled_candidate = library.candidates[6]
    assert scaled_candidate.column == (4, -4, 0, 1, 0, 0)
    assert scaled_candidate.expansion_scale == sp.Rational(1, 4)
    assert scaled_candidate.weighted_component(result.weights[6]).weight == 1
    _verified_certificate(result, library)


def test_feasibility_wins_when_the_last_allowed_pivot_reaches_zero(
    ternary_symbols: Variables,
) -> None:
    """Return a completed exact solution without spending a degenerate extra pivot."""
    _, y, z = ternary_symbols
    library = _library(y * z, ternary_symbols)

    result = solve_candidate_combination(
        library,
        _exact_limits(max_pivots=5),
    )

    assert result.status is CombinationSearchStatus.FEASIBLE
    assert result.pivots == 5
    assert result.weights[4] == 1
    _verified_certificate(result, library)


def test_rank_deficient_numerical_support_is_solved_exactly(
    monkeypatch: pytest.MonkeyPatch,
    ternary_symbols: Variables,
) -> None:
    """Accept a dependent proposed support without choosing free values numerically."""
    x, y, z = ternary_symbols
    library = _library(x**2 + y**2 + z**2 - x * y - x * z - y * z, ternary_symbols)
    candidate_count = len(library.candidates)
    matrix = sp.Matrix.hstack(
        *(sp.Matrix(candidate.column) for candidate in library.candidates)
    )
    assert matrix.rank() < candidate_count

    def fake_linprog(*args, **kwargs):
        return SimpleNamespace(
            status=0,
            success=True,
            x=[1.0] * candidate_count,
        )

    monkeypatch.setattr(search_module, "_load_scipy_linprog", lambda: fake_linprog)
    result = solve_candidate_combination(
        library,
        CombinationSearchLimits(
            backend=SolverBackend.SCIPY_HIGHS,
            max_recovery_candidates=candidate_count,
        ),
    )

    assert result.status is CombinationSearchStatus.FEASIBLE
    assert result.backend is SolverBackend.SCIPY_HIGHS
    assert result.attempted_supports == 1
    assert _codes(result) == (
        "combination.numeric.proposed_support",
        "combination.matched",
    )
    _verified_certificate(result, library)


def test_near_zero_column_is_reintroduced_after_strong_support_fails(
    monkeypatch: pytest.MonkeyPatch,
    ternary_symbols: Variables,
) -> None:
    """Retry exact recovery with a tiny proposed weight before full fallback."""
    x, y, z = ternary_symbols
    library = _library(x**2 + y**2 + z**2 - x * y - x * z - y * z, ternary_symbols)
    baseline = solve_candidate_combination(library, _exact_limits())
    selected = [index for index, weight in enumerate(baseline.weights) if weight]
    assert len(selected) == 3
    proposed_values = [0.0] * len(library.candidates)
    proposed_values[selected[0]] = 1.0
    proposed_values[selected[1]] = 1.0
    proposed_values[selected[2]] = 1e-12

    def fake_linprog(*args, **kwargs):
        return SimpleNamespace(status=0, success=True, x=proposed_values)

    monkeypatch.setattr(search_module, "_load_scipy_linprog", lambda: fake_linprog)
    result = solve_candidate_combination(
        library,
        CombinationSearchLimits(
            backend=SolverBackend.SCIPY_HIGHS,
            max_recovery_candidates=3,
        ),
    )

    assert result.status is CombinationSearchStatus.FEASIBLE
    assert result.backend is SolverBackend.SCIPY_HIGHS
    assert result.attempted_supports == 2
    assert _codes(result) == (
        "combination.numeric.proposed_support",
        "combination.recovery.support_failed",
        "combination.matched",
    )
    _verified_certificate(result, library)


@pytest.mark.parametrize(
    ("fake_result", "diagnostic_code"),
    [
        (
            SimpleNamespace(status=2, success=False, x=None),
            "combination.numeric.infeasible",
        ),
        (
            SimpleNamespace(status=1, success=False, x=None),
            "combination.numeric.time_limit",
        ),
        (
            SimpleNamespace(status=0, success=True, x=[float("nan")]),
            "combination.numeric.error",
        ),
    ],
)
def test_numerical_failures_cannot_override_exact_fallback(
    monkeypatch: pytest.MonkeyPatch,
    ternary_symbols: Variables,
    fake_result: object,
    diagnostic_code: str,
) -> None:
    """Treat numerical status and malformed values only as search diagnostics."""
    x, y, z = ternary_symbols
    library = _library(x**2 + y**2 + z**2 - x * y - x * z - y * z, ternary_symbols)

    def fake_linprog(*args, **kwargs):
        if diagnostic_code == "combination.numeric.error":
            fake_result.x = [float("nan")] * len(library.candidates)
        return fake_result

    monkeypatch.setattr(search_module, "_load_scipy_linprog", lambda: fake_linprog)
    result = solve_candidate_combination(
        library,
        CombinationSearchLimits(backend=SolverBackend.SCIPY_HIGHS),
    )

    assert result.status is CombinationSearchStatus.FEASIBLE
    assert result.backend is SolverBackend.EXACT
    assert diagnostic_code in _codes(result)
    assert _codes(result)[-1] == "combination.matched"
    _verified_certificate(result, library)


def test_auto_backend_reports_unavailable_scipy_and_uses_exact_search(
    monkeypatch: pytest.MonkeyPatch,
    ternary_symbols: Variables,
) -> None:
    """Keep the default backend useful when the optional dependency is absent."""
    x, y, z = ternary_symbols
    library = _library(x**2 + y**2 + z**2 - x * y - x * z - y * z, ternary_symbols)
    monkeypatch.setattr(search_module, "_load_scipy_linprog", lambda: None)

    result = solve_candidate_combination(
        library,
        CombinationSearchLimits(backend=SolverBackend.AUTO),
    )

    assert result.status is CombinationSearchStatus.FEASIBLE
    assert result.backend is SolverBackend.EXACT
    assert _codes(result) == (
        "combination.numeric.unavailable",
        "combination.matched",
    )
    _verified_certificate(result, library)


def test_zero_time_budget_does_not_import_the_optional_backend(
    monkeypatch: pytest.MonkeyPatch,
    ternary_symbols: Variables,
) -> None:
    """Honor an exhausted budget before attempting a lazy SciPy import."""
    x, y, z = ternary_symbols
    library = _library(x**2 + y**2 + z**2 - x * y - x * z - y * z, ternary_symbols)

    def fail_if_loaded():
        raise AssertionError("an exhausted solver budget must not load SciPy")

    monkeypatch.setattr(search_module, "_load_scipy_linprog", fail_if_loaded)

    result = solve_candidate_combination(
        library,
        CombinationSearchLimits(
            max_seconds=0,
            backend=SolverBackend.AUTO,
        ),
    )

    assert result.status is CombinationSearchStatus.LIMIT_REACHED
    assert _codes(result) == (
        "combination.numeric.time_limit",
        "combination.exact.time_limit",
    )


def test_exact_search_handles_zero_empty_and_infeasible_libraries(
    ternary_symbols: Variables,
) -> None:
    """Distinguish the empty zero combination from finite-cone infeasibility."""
    x, _, _ = ternary_symbols
    zero_library = _library(0, ternary_symbols, max_candidates=0)
    empty_nonzero_library = _library(x, ternary_symbols, max_candidates=0)
    negative_library = _library(-x, ternary_symbols)

    zero = solve_candidate_combination(zero_library, _exact_limits())
    empty_nonzero = solve_candidate_combination(
        empty_nonzero_library,
        _exact_limits(),
    )
    negative = solve_candidate_combination(negative_library, _exact_limits())

    assert zero.status is CombinationSearchStatus.FEASIBLE
    assert zero.weights == ()
    assert zero.exact_residual == (sp.S.Zero,)
    assert empty_nonzero.status is CombinationSearchStatus.INFEASIBLE_IN_LIBRARY
    assert negative.status is CombinationSearchStatus.INFEASIBLE_IN_LIBRARY
    assert "combination.exact.infeasible_in_library" in _codes(empty_nonzero)
    assert "combination.exact.infeasible_in_library" in _codes(negative)


def test_exact_pivot_and_time_limits_return_distinct_inconclusive_results(
    ternary_symbols: Variables,
) -> None:
    """Report operational stops without attaching any candidate weights."""
    x, y, z = ternary_symbols
    library = _library(x**2 + y**2 + z**2 - x * y - x * z - y * z, ternary_symbols)

    pivot_limited = solve_candidate_combination(
        library,
        _exact_limits(max_pivots=0),
    )
    time_limited = solve_candidate_combination(
        library,
        _exact_limits(max_seconds=0),
    )

    assert pivot_limited.status is CombinationSearchStatus.LIMIT_REACHED
    assert pivot_limited.weights == ()
    assert pivot_limited.exact_residual is None
    assert _codes(pivot_limited)[-1] == "combination.exact.pivot_limit"
    assert time_limited.status is CombinationSearchStatus.LIMIT_REACHED
    assert time_limited.weights == ()
    assert time_limited.exact_residual is None
    assert _codes(time_limited)[-1] == "combination.exact.time_limit"


def test_exact_backend_never_attempts_to_import_scipy(
    monkeypatch: pytest.MonkeyPatch,
    ternary_symbols: Variables,
) -> None:
    """Keep exact-only search independent of the optional numerical package."""
    x, y, z = ternary_symbols
    library = _library(x**2 + y**2 + z**2 - x * y - x * z - y * z, ternary_symbols)

    def fail_if_loaded():
        raise AssertionError("exact search must not load SciPy")

    monkeypatch.setattr(search_module, "_load_scipy_linprog", fail_if_loaded)

    result = solve_candidate_combination(library, _exact_limits())

    assert result.status is CombinationSearchStatus.FEASIBLE

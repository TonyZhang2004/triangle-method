"""Tests for bounded exact rational counterexample search."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from fractions import Fraction

import pytest
import sympy as sp

from triangle_method import HomogeneousPolynomial, PolynomialInputError
from triangle_method.counterexamples import (
    Counterexample,
    CounterexampleSearchError,
    CounterexampleSearchLimits,
    CounterexampleSearchResult,
    CounterexampleSearchStopReason,
    evaluate_on_simplex,
    search_counterexample,
    verify_counterexample,
)

Variables = tuple[sp.Symbol, sp.Symbol, sp.Symbol]


def _polynomial(expression: object, variables: Variables) -> HomogeneousPolynomial:
    """Construct one exact target in the requested variable order."""
    return HomogeneousPolynomial.from_expr(expression, variables=variables)


def test_exact_simplex_evaluation_accepts_supported_rational_inputs(
    ternary_symbols: Variables,
) -> None:
    """Preserve rational coordinates and evaluation without floating conversion."""
    x, y, z = ternary_symbols
    target = _polynomial(sp.Rational(1, 3) * x**2 - 2 * x * y + z**2, ternary_symbols)

    value = evaluate_on_simplex(
        target,
        (Fraction(1, 2), sp.Rational(1, 3), Fraction(1, 6)),
    )

    assert value == sp.Rational(-2, 9)
    assert isinstance(value, sp.Rational)
    assert not value.atoms(sp.Float)


def test_known_false_inequality_produces_an_exact_boundary_witness(
    ternary_symbols: Variables,
) -> None:
    """Find the first negative midpoint for the documented false quadratic."""
    x, y, z = ternary_symbols
    target = _polynomial(x**2 + y**2 + z**2 - 4 * x * y, ternary_symbols)

    result = search_counterexample(
        target,
        CounterexampleSearchLimits(max_denominator=2, max_points=20),
    )

    assert result.complete
    assert result.stop_reason is None
    assert result.found
    assert result.checked_points == 4
    assert result.denominator_reached == 2
    assert result.counterexample == Counterexample(
        target=target,
        coordinates=(sp.Rational(1, 2), sp.Rational(1, 2), sp.S.Zero),
        value=sp.Rational(-1, 2),
    )
    assert result.counterexample is not None
    assert verify_counterexample(target, result.counterexample)


def test_search_checks_simplex_vertices_and_edges(
    ternary_symbols: Variables,
) -> None:
    """Include boundary points instead of restricting discovery to the open simplex."""
    x, y, _ = ternary_symbols
    vertex_negative = _polynomial(-(x**2), ternary_symbols)
    edge_negative = _polynomial(-x * y, ternary_symbols)

    vertex_result = search_counterexample(vertex_negative)
    edge_result = search_counterexample(edge_negative)

    assert vertex_result.counterexample == Counterexample(
        target=vertex_negative,
        coordinates=(sp.S.One, sp.S.Zero, sp.S.Zero),
        value=sp.S.NegativeOne,
    )
    assert edge_result.counterexample == Counterexample(
        target=edge_negative,
        coordinates=(sp.Rational(1, 2), sp.Rational(1, 2), sp.S.Zero),
        value=sp.Rational(-1, 4),
    )


def test_exhausted_search_is_only_a_finite_unsuccessful_outcome(
    ternary_symbols: Variables,
) -> None:
    """Report an exhausted configured grid without manufacturing proof evidence."""
    x, y, z = ternary_symbols
    target = _polynomial(x**2 + y**2 + z**2, ternary_symbols)
    limits = CounterexampleSearchLimits(max_denominator=3, max_points=100)

    result = search_counterexample(target, limits)

    assert result.complete
    assert result.stop_reason is None
    assert not result.found
    assert result.counterexample is None
    assert result.checked_points == 13
    assert result.denominator_reached == 3


def test_point_budget_stops_before_an_unchecked_negative_point(
    ternary_symbols: Variables,
) -> None:
    """Apply the point cap deterministically in canonical triangle order."""
    x, y, _ = ternary_symbols
    target = _polynomial(-x * y, ternary_symbols)

    stopped = search_counterexample(
        target,
        CounterexampleSearchLimits(max_denominator=5, max_points=3),
    )
    found = search_counterexample(
        target,
        CounterexampleSearchLimits(max_denominator=5, max_points=4),
    )

    assert not stopped.complete
    assert stopped.stop_reason is CounterexampleSearchStopReason.POINT_LIMIT
    assert stopped.checked_points == 3
    assert stopped.denominator_reached == 1
    assert stopped.counterexample is None
    assert found.complete
    assert found.counterexample is not None
    assert found.checked_points == 4


@pytest.mark.parametrize(
    ("constant", "counterexample_found", "expected_value"),
    [
        (-3, True, sp.Integer(-3)),
        (0, False, None),
        (5, False, None),
    ],
)
def test_constants_receive_one_coordinate_independent_check(
    ternary_symbols: Variables,
    constant: int,
    counterexample_found: bool,
    expected_value: sp.Rational | None,
) -> None:
    """Decide constant targets without redundantly traversing every rational point."""
    target = _polynomial(constant, ternary_symbols)

    result = search_counterexample(
        target,
        CounterexampleSearchLimits(max_denominator=9, max_points=1),
    )

    assert result.complete
    assert result.found is counterexample_found
    assert result.checked_points == 1
    assert result.denominator_reached == 1
    if expected_value is None:
        assert result.counterexample is None
    else:
        assert result.counterexample is not None
        assert result.counterexample.value == expected_value
        assert verify_counterexample(target, result.counterexample)


def test_zero_point_budget_returns_a_limit_without_evaluation(
    ternary_symbols: Variables,
) -> None:
    """Allow callers to disable search explicitly while retaining a valid outcome."""
    x, _, _ = ternary_symbols
    limits = CounterexampleSearchLimits(max_denominator=4, max_points=0)

    polynomial_result = search_counterexample(
        _polynomial(-x, ternary_symbols),
        limits,
    )
    constant_result = search_counterexample(
        _polynomial(-1, ternary_symbols),
        limits,
    )

    assert not polynomial_result.complete
    assert not constant_result.complete
    assert polynomial_result.stop_reason is CounterexampleSearchStopReason.POINT_LIMIT
    assert constant_result.stop_reason is CounterexampleSearchStopReason.POINT_LIMIT
    assert polynomial_result.checked_points == constant_result.checked_points == 0
    assert (
        polynomial_result.denominator_reached
        == constant_result.denominator_reached
        == 0
    )


def test_counterexample_verifier_rejects_wrong_value_or_target(
    ternary_symbols: Variables,
) -> None:
    """Recompute witness evidence instead of trusting a plausible negative claim."""
    x, y, z = ternary_symbols
    target = _polynomial(x**2 + y**2 + z**2 - 4 * x * y, ternary_symbols)
    other = _polynomial(x**2 + y**2 + z**2, ternary_symbols)
    point = (sp.Rational(1, 2), sp.Rational(1, 2), sp.S.Zero)
    valid = Counterexample(
        target=target,
        coordinates=point,
        value=sp.Rational(-1, 2),
    )

    assert verify_counterexample(target, valid)
    assert not verify_counterexample(other, valid)

    forged = object.__new__(Counterexample)
    object.__setattr__(forged, "target", target)
    object.__setattr__(forged, "coordinates", point)
    object.__setattr__(forged, "value", sp.Rational(-1, 3))
    assert not verify_counterexample(target, forged)

    with pytest.raises(CounterexampleSearchError, match="exact evaluation"):
        Counterexample(
            target=target,
            coordinates=point,
            value=sp.Rational(-1, 3),
        )


def test_counterexample_search_canonicalizes_polynomial_subclasses(
    ternary_symbols: Variables,
) -> None:
    """Verify witnesses against the canonical value represented by a model subclass."""

    class DerivedPolynomial(HomogeneousPolynomial):
        """Exercise canonicalization at the counterexample verification boundary."""

    x, _, _ = ternary_symbols
    supplied = DerivedPolynomial.from_expr(-x, variables=ternary_symbols)

    result = search_counterexample(supplied)

    assert result.counterexample is not None
    assert type(result.counterexample.target) is HomogeneousPolynomial
    assert verify_counterexample(supplied, result.counterexample)


def test_search_result_rebuilds_and_rejects_forged_witnesses(
    ternary_symbols: Variables,
) -> None:
    """Do not trust an exact-type witness whose constructor invariants were bypassed."""

    x, _, _ = ternary_symbols
    target = _polynomial(-x, ternary_symbols)
    limits = CounterexampleSearchLimits(max_denominator=1, max_points=3)
    forged = object.__new__(Counterexample)
    object.__setattr__(forged, "target", target)
    object.__setattr__(forged, "coordinates", (sp.S.One, sp.S.Zero, sp.S.Zero))
    object.__setattr__(forged, "value", sp.Integer(-2))
    missing_fields = object.__new__(Counterexample)

    assert not verify_counterexample(target, forged)
    assert not verify_counterexample(target, missing_fields)
    with pytest.raises(CounterexampleSearchError, match="malformed"):
        CounterexampleSearchResult(
            limits=limits,
            checked_points=1,
            denominator_reached=1,
            counterexample=forged,
        )
    with pytest.raises(CounterexampleSearchError, match="malformed"):
        CounterexampleSearchResult(
            limits=limits,
            checked_points=1,
            denominator_reached=1,
            counterexample=missing_fields,
        )


def test_search_result_checks_witness_denominator_metadata(
    ternary_symbols: Variables,
) -> None:
    """Require a found point to lie at the exact denominator reported by the search."""

    x, y, _ = ternary_symbols
    target = _polynomial(-x * y, ternary_symbols)
    witness = Counterexample(
        target=target,
        coordinates=(sp.Rational(1, 2), sp.Rational(1, 2), sp.S.Zero),
        value=sp.Rational(-1, 4),
    )

    with pytest.raises(CounterexampleSearchError, match="denominator"):
        CounterexampleSearchResult(
            limits=CounterexampleSearchLimits(max_denominator=12, max_points=10),
            checked_points=1,
            denominator_reached=1,
            counterexample=witness,
        )


@pytest.mark.parametrize(
    "coordinates",
    [
        (1, 0),
        (1, 0, 0, 0),
        (True, 0, 0),
        (1.0, 0, 0),
        (sp.sqrt(2), 0, 1 - sp.sqrt(2)),
        (2, -1, 0),
        (1, 1, 0),
        "1,0,0",
    ],
)
def test_simplex_points_reject_malformed_or_inexact_coordinates(
    ternary_symbols: Variables,
    coordinates: object,
) -> None:
    """Reject points outside the exact nonnegative rational simplex."""
    target = _polynomial(1, ternary_symbols)

    with pytest.raises(CounterexampleSearchError):
        evaluate_on_simplex(target, coordinates)  # type: ignore[arg-type]


@pytest.mark.parametrize("value", [0, 1, sp.Rational(1, 2), 0.0, sp.sqrt(2)])
def test_counterexamples_require_an_exact_strictly_negative_value(
    ternary_symbols: Variables,
    value: object,
) -> None:
    """Prevent nonnegative, floating, or irrational witness evaluations."""
    with pytest.raises(CounterexampleSearchError):
        Counterexample(
            target=_polynomial(-1, ternary_symbols),
            coordinates=(sp.S.One, sp.S.Zero, sp.S.Zero),
            value=value,  # type: ignore[arg-type]
        )


@pytest.mark.parametrize(
    "limits",
    [
        {"max_denominator": 0},
        {"max_denominator": True},
        {"max_denominator": 1.0},
        {"max_points": -1},
        {"max_points": False},
        {"max_points": 2.0},
    ],
)
def test_search_limits_reject_invalid_budgets(limits: dict[str, object]) -> None:
    """Require bounded searches to use explicit non-boolean integer budgets."""
    with pytest.raises(CounterexampleSearchError):
        CounterexampleSearchLimits(**limits)  # type: ignore[arg-type]


def test_search_records_are_frozen_and_reject_inconsistent_states(
    ternary_symbols: Variables,
) -> None:
    """Keep public search evidence immutable and consistent with its status."""
    limits = CounterexampleSearchLimits(max_denominator=2, max_points=3)
    target = _polynomial(-1, ternary_symbols)
    counterexample = Counterexample(
        target=target,
        coordinates=(sp.S.One, sp.S.Zero, sp.S.Zero),
        value=sp.S.NegativeOne,
    )
    result = CounterexampleSearchResult(
        limits=limits,
        checked_points=1,
        denominator_reached=1,
        counterexample=counterexample,
    )

    with pytest.raises(FrozenInstanceError):
        result.checked_points = 2  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        counterexample.value = -2  # type: ignore[misc]
    with pytest.raises(CounterexampleSearchError):
        CounterexampleSearchResult(
            limits=limits,
            checked_points=1,
            denominator_reached=1,
            complete=False,
            stop_reason=CounterexampleSearchStopReason.POINT_LIMIT,
            counterexample=counterexample,
        )
    with pytest.raises(CounterexampleSearchError):
        CounterexampleSearchResult(
            limits=limits,
            checked_points=1,
            denominator_reached=1,
            complete=True,
            stop_reason=CounterexampleSearchStopReason.POINT_LIMIT,
        )
    with pytest.raises(CounterexampleSearchError):
        CounterexampleSearchResult(
            limits=limits,
            checked_points=2,
            denominator_reached=1,
            complete=False,
            stop_reason=CounterexampleSearchStopReason.POINT_LIMIT,
        )


def test_public_functions_reject_wrong_target_and_record_types(
    ternary_symbols: Variables,
) -> None:
    """Distinguish invalid caller input from an inconclusive finite search."""
    x, _, _ = ternary_symbols
    target = _polynomial(-x, ternary_symbols)

    with pytest.raises(PolynomialInputError):
        evaluate_on_simplex(object(), (1, 0, 0))  # type: ignore[arg-type]
    with pytest.raises(PolynomialInputError):
        search_counterexample(object())  # type: ignore[arg-type]
    with pytest.raises(PolynomialInputError):
        verify_counterexample(object(), object())  # type: ignore[arg-type]
    with pytest.raises(CounterexampleSearchError):
        search_counterexample(target, limits=object())  # type: ignore[arg-type]
    with pytest.raises(CounterexampleSearchError):
        verify_counterexample(target, object())  # type: ignore[arg-type]

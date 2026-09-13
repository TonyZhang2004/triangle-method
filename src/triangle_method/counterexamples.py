"""Bounded exact counterexample search on the nonnegative ternary simplex."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from enum import Enum
from fractions import Fraction
from math import gcd, lcm
from typing import TypeAlias

import sympy as sp

from .errors import PolynomialInputError
from .polynomial import HomogeneousPolynomial

SimplexPoint: TypeAlias = tuple[sp.Rational, sp.Rational, sp.Rational]


class CounterexampleSearchError(ValueError):
    """Report malformed rational-search limits, points, witnesses, or outcomes."""


class CounterexampleSearchStopReason(str, Enum):
    """Identify the operational budget that interrupted a rational-point search."""

    POINT_LIMIT = "point_limit"


def _validate_integer_limit(
    value: object,
    *,
    name: str,
    minimum: int,
) -> int:
    """Validate a non-boolean integer search limit at the stated minimum."""
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise CounterexampleSearchError(
            f"{name} must be an integer that is at least {minimum}"
        )
    return value


@dataclass(frozen=True, slots=True, kw_only=True)
class CounterexampleSearchLimits:
    """Bound rational simplex denominators and the number of exact evaluations."""

    max_denominator: int = 12
    max_points: int = 10_000

    def __post_init__(self) -> None:
        """Reject malformed limits before a rational-point search begins."""
        _validate_integer_limit(
            self.max_denominator,
            name="max_denominator",
            minimum=1,
        )
        _validate_integer_limit(
            self.max_points,
            name="max_points",
            minimum=0,
        )


def _coerce_exact_coordinate(value: object, *, context: str) -> sp.Rational:
    """Convert one supported exact rational coordinate or evaluation value."""
    if isinstance(value, bool):
        raise CounterexampleSearchError(f"{context} cannot be a boolean")
    if isinstance(value, (float, sp.Float)):
        raise CounterexampleSearchError(
            f"{context} must be exact; use sympy.Rational or fractions.Fraction"
        )
    if isinstance(value, Fraction):
        return sp.Rational(value.numerator, value.denominator)
    if isinstance(value, int):
        return sp.Integer(value)
    if isinstance(value, sp.Rational):
        return value
    raise CounterexampleSearchError(
        f"{context} must be an integer or exact rational number"
    )


def _coerce_simplex_point(coordinates: Sequence[object]) -> SimplexPoint:
    """Validate three exact nonnegative coordinates summing to one."""
    if isinstance(coordinates, (str, bytes)):
        raise CounterexampleSearchError(
            "simplex coordinates must contain three exact rational values"
        )
    try:
        values = tuple(coordinates)
    except TypeError as error:
        raise CounterexampleSearchError(
            "simplex coordinates must contain three exact rational values"
        ) from error
    if len(values) != 3:
        raise CounterexampleSearchError(
            "simplex coordinates must contain exactly three values"
        )

    point = tuple(
        _coerce_exact_coordinate(value, context=f"coordinate {index}")
        for index, value in enumerate(values)
    )
    if any(coordinate < 0 for coordinate in point):
        raise CounterexampleSearchError("simplex coordinates must be nonnegative")
    if sum(point, sp.S.Zero) != 1:
        raise CounterexampleSearchError("simplex coordinates must sum exactly to one")
    return point  # type: ignore[return-value]


@dataclass(frozen=True, slots=True, kw_only=True)
class CounterexampleSearchResult:
    """Store one bounded search outcome and enough work metadata for diagnostics."""

    limits: CounterexampleSearchLimits
    checked_points: int
    denominator_reached: int
    counterexample: Counterexample | None = None
    complete: bool = True
    stop_reason: CounterexampleSearchStopReason | None = None

    def __post_init__(self) -> None:
        """Enforce consistent evidence, counters, and interruption metadata."""
        if type(self.limits) is not CounterexampleSearchLimits:
            raise CounterexampleSearchError(
                "limits must be a CounterexampleSearchLimits object"
            )
        checked_points = _validate_integer_limit(
            self.checked_points,
            name="checked_points",
            minimum=0,
        )
        denominator_reached = _validate_integer_limit(
            self.denominator_reached,
            name="denominator_reached",
            minimum=0,
        )
        if checked_points > self.limits.max_points:
            raise CounterexampleSearchError(
                "checked_points cannot exceed the configured point limit"
            )
        if denominator_reached > self.limits.max_denominator:
            raise CounterexampleSearchError(
                "denominator_reached cannot exceed the configured denominator limit"
            )
        if (checked_points == 0) != (denominator_reached == 0):
            raise CounterexampleSearchError(
                "denominator_reached must be zero exactly when no points were checked"
            )

        if not isinstance(self.complete, bool):
            raise CounterexampleSearchError("complete must be a boolean")
        if self.complete and self.stop_reason is not None:
            raise CounterexampleSearchError(
                "a complete search result cannot contain a stop reason"
            )
        if not self.complete:
            if self.stop_reason is not CounterexampleSearchStopReason.POINT_LIMIT:
                raise CounterexampleSearchError(
                    "an incomplete search must identify the point limit as its stop reason"
                )
            if checked_points != self.limits.max_points:
                raise CounterexampleSearchError(
                    "a point-limit result must consume the configured point budget"
                )
            if self.counterexample is not None:
                raise CounterexampleSearchError(
                    "an interrupted search result cannot contain a counterexample"
                )
        elif self.stop_reason is not None:
            raise CounterexampleSearchError(
                "a complete search result cannot contain a stop reason"
            )

        if self.counterexample is not None:
            if type(self.counterexample) is not Counterexample:
                raise CounterexampleSearchError(
                    "counterexample must be a Counterexample object or None"
                )
            if checked_points == 0:
                raise CounterexampleSearchError(
                    "a result with a counterexample must have checked at least one point"
                )
            try:
                rebuilt_counterexample = Counterexample(
                    target=self.counterexample.target,
                    coordinates=self.counterexample.coordinates,
                    value=self.counterexample.value,
                )
            except (
                AttributeError,
                CounterexampleSearchError,
                PolynomialInputError,
            ) as error:
                raise CounterexampleSearchError(
                    "counterexample search evidence is malformed"
                ) from error
            point_denominator = lcm(
                *(
                    int(coordinate.q)
                    for coordinate in rebuilt_counterexample.coordinates
                )
            )
            if point_denominator != denominator_reached:
                raise CounterexampleSearchError(
                    "counterexample denominator does not match search metadata"
                )
            object.__setattr__(self, "counterexample", rebuilt_counterexample)

    @property
    def found(self) -> bool:
        """Return whether the bounded search produced an exact negative witness."""
        return self.counterexample is not None


def evaluate_on_simplex(
    polynomial: HomogeneousPolynomial,
    coordinates: Sequence[object],
) -> sp.Rational:
    """Evaluate a homogeneous polynomial exactly at a rational simplex point."""
    if not isinstance(polynomial, HomogeneousPolynomial):
        raise PolynomialInputError(
            "evaluate_on_simplex() requires a HomogeneousPolynomial"
        )
    point = _coerce_simplex_point(coordinates)
    value = sp.S.Zero
    for exponent, coefficient in polynomial.coefficients.items():
        monomial_value = sp.S.One
        for coordinate, power in zip(point, exponent, strict=True):
            monomial_value *= coordinate**power
        value += coefficient * monomial_value
    return value


@dataclass(frozen=True, slots=True, kw_only=True)
class Counterexample:
    """Store a target, rational simplex coordinates, and its exact negative value."""

    target: HomogeneousPolynomial
    coordinates: SimplexPoint
    value: sp.Rational

    def __post_init__(self) -> None:
        """Copy the target and require the stored exact evaluation to be negative."""
        if not isinstance(self.target, HomogeneousPolynomial):
            raise PolynomialInputError(
                "counterexample target must be a HomogeneousPolynomial"
            )
        target = HomogeneousPolynomial.from_terms(
            self.target.coefficients,
            variables=self.target.variables,
        )
        coordinates = _coerce_simplex_point(self.coordinates)
        value = _coerce_exact_coordinate(self.value, context="counterexample value")
        if value >= 0:
            raise CounterexampleSearchError(
                "a counterexample value must be strictly negative"
            )
        evaluated = evaluate_on_simplex(target, coordinates)
        if evaluated != value:
            raise CounterexampleSearchError(
                "counterexample value does not equal the target's exact evaluation"
            )
        object.__setattr__(self, "target", target)
        object.__setattr__(self, "coordinates", coordinates)
        object.__setattr__(self, "value", value)


def verify_counterexample(
    target: HomogeneousPolynomial,
    counterexample: Counterexample,
) -> bool:
    """Rebuild and re-evaluate a counterexample against the requested exact target."""
    if not isinstance(target, HomogeneousPolynomial):
        raise PolynomialInputError(
            "verify_counterexample() requires a HomogeneousPolynomial"
        )
    if type(counterexample) is not Counterexample:
        raise CounterexampleSearchError("counterexample must be a Counterexample")
    try:
        canonical_target = HomogeneousPolynomial.from_terms(
            target.coefficients,
            variables=target.variables,
        )
        rebuilt = Counterexample(
            target=canonical_target,
            coordinates=counterexample.coordinates,
            value=counterexample.value,
        )
        return (
            counterexample.target == rebuilt.target
            and counterexample.coordinates == rebuilt.coordinates
            and counterexample.value == rebuilt.value
        )
    except (AttributeError, CounterexampleSearchError, PolynomialInputError):
        return False


def _primitive_simplex_points(denominator: int) -> Iterator[SimplexPoint]:
    """Yield new denominator-d simplex points in canonical triangle order."""
    for row in range(denominator + 1):
        first_numerator = denominator - row
        for third_numerator in range(row + 1):
            second_numerator = row - third_numerator
            if (
                gcd(
                    gcd(first_numerator, second_numerator),
                    third_numerator,
                )
                != 1
            ):
                continue
            yield (
                sp.Rational(first_numerator, denominator),
                sp.Rational(second_numerator, denominator),
                sp.Rational(third_numerator, denominator),
            )


def _search_constant(
    target: HomogeneousPolynomial,
    limits: CounterexampleSearchLimits,
) -> CounterexampleSearchResult:
    """Decide a constant target with one exact evaluation when budget permits."""
    if limits.max_points == 0:
        return CounterexampleSearchResult(
            limits=limits,
            checked_points=0,
            denominator_reached=0,
            complete=False,
            stop_reason=CounterexampleSearchStopReason.POINT_LIMIT,
        )

    coordinates: SimplexPoint = (sp.S.One, sp.S.Zero, sp.S.Zero)
    value = evaluate_on_simplex(target, coordinates)
    if value < 0:
        return CounterexampleSearchResult(
            limits=limits,
            checked_points=1,
            denominator_reached=1,
            counterexample=Counterexample(
                target=target,
                coordinates=coordinates,
                value=value,
            ),
        )
    return CounterexampleSearchResult(
        limits=limits,
        checked_points=1,
        denominator_reached=1,
    )


def search_counterexample(
    target: HomogeneousPolynomial,
    limits: CounterexampleSearchLimits | None = None,
) -> CounterexampleSearchResult:
    """Search reduced rational points up to fixed denominator and evaluation budgets."""
    if not isinstance(target, HomogeneousPolynomial):
        raise PolynomialInputError(
            "search_counterexample() requires a HomogeneousPolynomial"
        )
    if limits is None:
        limits = CounterexampleSearchLimits()
    elif type(limits) is not CounterexampleSearchLimits:
        raise CounterexampleSearchError(
            "limits must be a CounterexampleSearchLimits object or None"
        )

    if target.degree == 0:
        return _search_constant(target, limits)

    checked_points = 0
    denominator_reached = 0
    for denominator in range(1, limits.max_denominator + 1):
        for coordinates in _primitive_simplex_points(denominator):
            if checked_points == limits.max_points:
                return CounterexampleSearchResult(
                    limits=limits,
                    checked_points=checked_points,
                    denominator_reached=denominator_reached,
                    complete=False,
                    stop_reason=CounterexampleSearchStopReason.POINT_LIMIT,
                )

            value = evaluate_on_simplex(target, coordinates)
            checked_points += 1
            denominator_reached = denominator
            if value < 0:
                return CounterexampleSearchResult(
                    limits=limits,
                    checked_points=checked_points,
                    denominator_reached=denominator_reached,
                    counterexample=Counterexample(
                        target=target,
                        coordinates=coordinates,
                        value=value,
                    ),
                )

    return CounterexampleSearchResult(
        limits=limits,
        checked_points=checked_points,
        denominator_reached=denominator_reached,
    )

"""Deterministic finite component generation in the shared triangle basis."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from enum import Enum
from fractions import Fraction
from heapq import heappop, heappush
from itertools import combinations
from math import gcd, isfinite
from time import monotonic as _monotonic
from typing import TypeAlias

import sympy as sp

from .certificate import WeightedComponent
from .errors import CandidateGenerationError, PolynomialInputError, PrimitiveInputError
from .normalization import _rational_content
from .polynomial import (
    ExactCoefficientInput,
    HomogeneousPolynomial,
    Variables,
    _coerce_exact_rational,
)
from .primitives import (
    MonomialComponent,
    PrimitiveComponent,
    SchurComponent,
    SquareComponent,
)
from .triangle import (
    _triangle_exponent_rows,
    _triangle_index,
    coefficient_rows,
)

IntegerColumn: TypeAlias = tuple[sp.Integer, ...]
LiftedPrimitive: TypeAlias = MonomialComponent | SquareComponent | SchurComponent
TimeCheck: TypeAlias = Callable[[], None]

_SCHUR_DEGREES = (3, 5)


class CandidateFamily(str, Enum):
    """Identify the finite primitive family that produced a candidate column."""

    MONOMIAL = "monomial"
    BINOMIAL_SQUARE = "binomial_square"
    SCHUR = "schur"


class GenerationStopReason(str, Enum):
    """Identify the operational budget that interrupted candidate generation."""

    CANDIDATE_LIMIT = "candidate_limit"
    TIME_LIMIT = "time_limit"


_COMPONENT_TYPE_BY_FAMILY = {
    CandidateFamily.MONOMIAL: MonomialComponent,
    CandidateFamily.BINOMIAL_SQUARE: SquareComponent,
    CandidateFamily.SCHUR: SchurComponent,
}


class _ZeroCandidateError(CandidateGenerationError):
    """Mark a theorem-backed component whose exact expansion has no cone ray."""


class _GenerationTimeLimitReached(RuntimeError):
    """Stop a family iterator when its cooperative deadline has elapsed."""


def _validate_integer_limit(
    value: object,
    *,
    name: str,
    minimum: int,
) -> int:
    """Validate one non-boolean integer generation limit at a stated minimum."""
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        comparison = "nonnegative" if minimum == 0 else f"at least {minimum}"
        raise CandidateGenerationError(
            f"{name} must be an integer that is {comparison}"
        )
    return value


@dataclass(frozen=True, slots=True, kw_only=True)
class CandidateGenerationLimits:
    """Bound the finite component scope and operational generation work."""

    max_candidates: int = 10_000
    max_seconds: float = 5.0
    max_ratio_numerator: int = 2
    max_ratio_denominator: int = 2
    max_base_degree: int = 10

    def __post_init__(self) -> None:
        """Validate limits and store the operational time bound as a finite float."""
        _validate_integer_limit(
            self.max_candidates,
            name="max_candidates",
            minimum=0,
        )
        _validate_integer_limit(
            self.max_ratio_numerator,
            name="max_ratio_numerator",
            minimum=1,
        )
        _validate_integer_limit(
            self.max_ratio_denominator,
            name="max_ratio_denominator",
            minimum=1,
        )
        _validate_integer_limit(
            self.max_base_degree,
            name="max_base_degree",
            minimum=0,
        )

        if isinstance(self.max_seconds, bool) or not isinstance(
            self.max_seconds, (int, float)
        ):
            raise CandidateGenerationError(
                "max_seconds must be a nonnegative finite number"
            )
        try:
            seconds = float(self.max_seconds)
        except (OverflowError, TypeError, ValueError) as error:
            raise CandidateGenerationError(
                "max_seconds must be a nonnegative finite number"
            ) from error
        if not isfinite(seconds) or seconds < 0:
            raise CandidateGenerationError(
                "max_seconds must be a nonnegative finite number"
            )
        object.__setattr__(self, "max_seconds", seconds)

    @property
    def square_ratios(self) -> tuple[sp.Rational, ...]:
        """Return all reduced positive ratios within the configured height bounds."""
        return tuple(
            _bounded_square_ratios(
                self.max_ratio_numerator,
                self.max_ratio_denominator,
            )
        )


def _bounded_square_ratios(
    max_numerator: int,
    max_denominator: int,
    check_time: TimeCheck | None = None,
) -> Iterator[sp.Rational]:
    """Yield bounded reduced positive ratios in exact increasing order."""
    # The value p/q increases when p moves right or q moves down. Expanding this
    # monotone grid from its minimum exposes the next exact ratio without first
    # allocating the full numerator-by-denominator rectangle.
    first = (1, max_denominator)
    pending: list[tuple[Fraction, int, int]] = [
        (Fraction(*first), *first),
    ]
    discovered = {first}

    while pending:
        if check_time is not None:
            check_time()
        ratio, numerator, denominator = heappop(pending)
        if gcd(numerator, denominator) == 1:
            yield sp.Rational(ratio.numerator, ratio.denominator)

        neighbors = (
            (numerator + 1, denominator),
            (numerator, denominator - 1),
        )
        for next_numerator, next_denominator in neighbors:
            if (
                next_numerator > max_numerator
                or next_denominator < 1
                or (next_numerator, next_denominator) in discovered
            ):
                continue
            if check_time is not None:
                check_time()
            discovered.add((next_numerator, next_denominator))
            heappush(
                pending,
                (
                    Fraction(next_numerator, next_denominator),
                    next_numerator,
                    next_denominator,
                ),
            )


def _flatten_coefficients(polynomial: HomogeneousPolynomial) -> tuple[sp.Rational, ...]:
    """Flatten exact coefficient rows in the package's canonical triangle order."""
    return tuple(
        coefficient for row in coefficient_rows(polynomial) for coefficient in row
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class ComponentCandidate:
    """Store primitive provenance and its exact primitive-integer matrix column."""

    family: CandidateFamily
    component: PrimitiveComponent
    column: IntegerColumn = field(init=False)
    expansion_scale: sp.Rational = field(init=False)

    def __post_init__(self) -> None:
        """Validate provenance and derive a positive-scale canonical coefficient ray."""
        if not isinstance(self.family, CandidateFamily):
            raise CandidateGenerationError("candidate family must be a CandidateFamily")
        expected_type = _COMPONENT_TYPE_BY_FAMILY[self.family]
        if type(self.component) is not expected_type:
            raise CandidateGenerationError(
                f"{self.family.value} candidates require {expected_type.__name__}"
            )

        try:
            expansion = self.component.expand()
        except (PolynomialInputError, PrimitiveInputError) as error:
            raise CandidateGenerationError(
                f"candidate component could not be expanded: {error}"
            ) from error
        if expansion.is_zero:
            raise _ZeroCandidateError(
                "candidate component must have a nonzero exact expansion"
            )
        if expansion.variables != self.component.variables:
            raise CandidateGenerationError(
                "candidate expansion changed the component variable order"
            )
        if expansion.degree != self.component.degree:
            raise CandidateGenerationError(
                "candidate expansion degree does not match its formal degree"
            )

        raw_column = _flatten_coefficients(expansion)
        expansion_scale = _rational_content(raw_column)
        primitive_column = tuple(
            coefficient / expansion_scale for coefficient in raw_column
        )
        if any(
            not isinstance(coefficient, sp.Integer) for coefficient in primitive_column
        ):
            raise CandidateGenerationError(
                "candidate column normalization did not produce exact integers"
            )

        object.__setattr__(self, "column", primitive_column)
        object.__setattr__(self, "expansion_scale", expansion_scale)

    @property
    def degree(self) -> int:
        """Return the formal homogeneous degree of the candidate component."""
        return self.component.degree

    @property
    def variables(self) -> Variables:
        """Return the candidate component's three explicitly ordered variables."""
        return self.component.variables

    def expand(self) -> HomogeneousPolynomial:
        """Return the candidate's exact polynomial expansion."""
        return self.component.expand()

    def weighted_component(
        self,
        column_weight: ExactCoefficientInput,
    ) -> WeightedComponent:
        """Convert a nonnegative canonical-column weight to the primitive's weight."""
        try:
            exact_weight = _coerce_exact_rational(
                column_weight,
                context="candidate column weight",
            )
        except PolynomialInputError as error:
            raise CandidateGenerationError(str(error)) from error
        if exact_weight < 0:
            raise CandidateGenerationError(
                "candidate column weight must be nonnegative"
            )
        return WeightedComponent(
            weight=exact_weight / self.expansion_scale,
            component=self.component,
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class CandidateGenerationMetadata:
    """Describe finite-scope completion, interruption, and exact candidate counts."""

    complete: bool
    stop_reason: GenerationStopReason | None
    attempted_count: int
    retained_count: int
    duplicate_count: int
    zero_count: int
    completed_families: tuple[CandidateFamily, ...]
    interrupted_family: CandidateFamily | None

    def __post_init__(self) -> None:
        """Copy family metadata and enforce consistent completion and count states."""
        if type(self.complete) is not bool:
            raise CandidateGenerationError("metadata complete must be a boolean")
        if self.stop_reason is not None and not isinstance(
            self.stop_reason, GenerationStopReason
        ):
            raise CandidateGenerationError(
                "metadata stop_reason must be a GenerationStopReason or None"
            )
        if self.interrupted_family is not None and not isinstance(
            self.interrupted_family, CandidateFamily
        ):
            raise CandidateGenerationError(
                "metadata interrupted_family must be a CandidateFamily or None"
            )

        counts = {
            "attempted_count": self.attempted_count,
            "retained_count": self.retained_count,
            "duplicate_count": self.duplicate_count,
            "zero_count": self.zero_count,
        }
        for name, value in counts.items():
            _validate_integer_limit(value, name=f"metadata {name}", minimum=0)
        classified_count = self.retained_count + self.duplicate_count + self.zero_count
        unclassified_count = self.attempted_count - classified_count
        if unclassified_count < 0:
            raise CandidateGenerationError(
                "metadata attempted_count cannot be smaller than its classified counts"
            )
        if unclassified_count > 1:
            raise CandidateGenerationError(
                "metadata can contain at most one interrupted candidate attempt"
            )

        if isinstance(self.completed_families, (str, bytes)):
            raise CandidateGenerationError(
                "metadata completed_families must contain CandidateFamily values"
            )
        try:
            completed_families = tuple(self.completed_families)
        except TypeError as error:
            raise CandidateGenerationError(
                "metadata completed_families must be iterable"
            ) from error
        if any(
            not isinstance(family, CandidateFamily) for family in completed_families
        ):
            raise CandidateGenerationError(
                "metadata completed_families must contain CandidateFamily values"
            )
        if len(set(completed_families)) != len(completed_families):
            raise CandidateGenerationError(
                "metadata completed_families cannot contain duplicates"
            )
        family_order = tuple(CandidateFamily)
        if completed_families != family_order[: len(completed_families)]:
            raise CandidateGenerationError(
                "metadata completed_families must follow canonical family order"
            )
        object.__setattr__(self, "completed_families", completed_families)

        if self.complete:
            if self.stop_reason is not None or self.interrupted_family is not None:
                raise CandidateGenerationError(
                    "complete metadata cannot contain an interruption"
                )
            if completed_families != family_order:
                raise CandidateGenerationError(
                    "complete metadata must include every candidate family"
                )
            if unclassified_count:
                raise CandidateGenerationError(
                    "complete metadata must classify every candidate attempt"
                )
        elif self.stop_reason is None or self.interrupted_family is None:
            raise CandidateGenerationError(
                "incomplete metadata must identify its stop reason and family"
            )
        elif (
            len(completed_families) >= len(family_order)
            or self.interrupted_family is not family_order[len(completed_families)]
        ):
            raise CandidateGenerationError(
                "metadata interrupted_family must follow the completed family prefix"
            )
        if self.interrupted_family in completed_families:
            raise CandidateGenerationError(
                "the interrupted family cannot also be marked complete"
            )
        if (
            self.stop_reason is GenerationStopReason.CANDIDATE_LIMIT
            and unclassified_count != 1
        ):
            raise CandidateGenerationError(
                "candidate-limit metadata must include its unretained candidate attempt"
            )


def _validate_monomial_candidate_order(
    candidates: tuple[ComponentCandidate, ...],
    target_degree: int,
    metadata: CandidateGenerationMetadata,
) -> None:
    """Require the canonical monomial prefix and its full block when completed."""
    monomials = tuple(
        candidate
        for candidate in candidates
        if candidate.family is CandidateFamily.MONOMIAL
    )
    positions = tuple(
        _triangle_index(candidate.component.exponent)  # type: ignore[union-attr]
        for candidate in monomials
    )
    if positions != tuple(range(len(monomials))):
        raise CandidateGenerationError(
            "monomial candidates must form a canonical exponent prefix"
        )

    expected_count = (target_degree + 1) * (target_degree + 2) // 2
    if (
        CandidateFamily.MONOMIAL in metadata.completed_families
        and len(monomials) != expected_count
    ):
        raise CandidateGenerationError(
            "a completed monomial family must contain every target position"
        )


def _square_candidate_key(
    candidate: ComponentCandidate,
    limits: CandidateGenerationLimits,
) -> tuple[int, int, sp.Rational]:
    """Validate one configured binomial square and return its generation-order key."""
    component = candidate.component
    if type(component) is not SquareComponent:
        raise CandidateGenerationError(
            "binomial-square provenance must contain a SquareComponent"
        )
    factor_terms = tuple(component.factor.coefficients.items())
    positive_terms = tuple(
        (exponent, coefficient)
        for exponent, coefficient in factor_terms
        if coefficient == 1
    )
    negative_terms = tuple(
        (exponent, coefficient)
        for exponent, coefficient in factor_terms
        if coefficient < 0
    )
    if len(factor_terms) != 2 or len(positive_terms) != 1 or len(negative_terms) != 1:
        raise CandidateGenerationError(
            "generated square factors must have coefficients 1 and -r"
        )

    positive_exponent = positive_terms[0][0]
    negative_exponent, negative_coefficient = negative_terms[0]
    ratio = -negative_coefficient
    if (
        int(ratio.p) > limits.max_ratio_numerator
        or int(ratio.q) > limits.max_ratio_denominator
    ):
        raise CandidateGenerationError(
            "square candidate ratio exceeds the configured rational bounds"
        )
    if 2 * component.factor.degree > limits.max_base_degree:
        raise CandidateGenerationError(
            "square candidate exceeds the configured base-degree limit"
        )
    if any(
        min(left, right) != 0
        for left, right in zip(
            positive_exponent,
            negative_exponent,
            strict=True,
        )
    ):
        raise CandidateGenerationError(
            "square candidate must extract its maximal common monomial"
        )

    positive_endpoint = tuple(
        shift + 2 * power
        for shift, power in zip(
            component.multiplier,
            positive_exponent,
            strict=True,
        )
    )
    negative_endpoint = tuple(
        shift + 2 * power
        for shift, power in zip(
            component.multiplier,
            negative_exponent,
            strict=True,
        )
    )
    positive_position = _triangle_index(positive_endpoint)
    negative_position = _triangle_index(negative_endpoint)
    if positive_position >= negative_position:
        raise CandidateGenerationError(
            "square candidate endpoints must follow canonical orientation"
        )
    return positive_position, negative_position, ratio


def _schur_candidate_key(
    candidate: ComponentCandidate,
    limits: CandidateGenerationLimits,
) -> tuple[int, int, int]:
    """Validate one configured Schur lift and return its generation-order key."""
    component = candidate.component
    if type(component) is not SchurComponent:
        raise CandidateGenerationError("Schur provenance must contain a SchurComponent")
    if component.schur_degree not in _SCHUR_DEGREES:
        raise CandidateGenerationError("candidate Schur degree must be three or five")

    argument_power = component.arguments[0][0]
    expected_arguments = (
        (argument_power, 0, 0),
        (0, argument_power, 0),
        (0, 0, argument_power),
    )
    if argument_power < 1 or component.arguments != expected_arguments:
        raise CandidateGenerationError(
            "candidate Schur arguments must be matching pure variable powers"
        )
    base_degree = component.schur_degree * argument_power
    if base_degree > limits.max_base_degree:
        raise CandidateGenerationError(
            "Schur candidate exceeds the configured base-degree limit"
        )
    return (
        _SCHUR_DEGREES.index(component.schur_degree),
        argument_power,
        _triangle_index(component.multiplier),
    )


def _validate_configured_candidate_order(
    candidates: tuple[ComponentCandidate, ...],
    target_degree: int,
    limits: CandidateGenerationLimits,
    metadata: CandidateGenerationMetadata,
) -> None:
    """Validate family scope and deterministic order without regenerating the library."""
    _validate_monomial_candidate_order(candidates, target_degree, metadata)
    square_keys = tuple(
        _square_candidate_key(candidate, limits)
        for candidate in candidates
        if candidate.family is CandidateFamily.BINOMIAL_SQUARE
    )
    if square_keys != tuple(sorted(square_keys)):
        raise CandidateGenerationError(
            "square candidates must follow canonical endpoint and ratio order"
        )
    schur_keys = tuple(
        _schur_candidate_key(candidate, limits)
        for candidate in candidates
        if candidate.family is CandidateFamily.SCHUR
    )
    if schur_keys != tuple(sorted(schur_keys)):
        raise CandidateGenerationError(
            "Schur candidates must follow canonical degree, power, and shift order"
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class CandidateLibrary:
    """Store a canonical target, finite exact candidates, limits, and completion data."""

    target: HomogeneousPolynomial
    candidates: tuple[ComponentCandidate, ...]
    limits: CandidateGenerationLimits
    metadata: CandidateGenerationMetadata

    def __post_init__(self) -> None:
        """Copy library data and validate its target-degree basis and metadata counts."""
        if not isinstance(self.target, HomogeneousPolynomial):
            raise PolynomialInputError(
                "candidate library target must be a HomogeneousPolynomial"
            )
        target = HomogeneousPolynomial.from_terms(
            self.target.coefficients,
            variables=self.target.variables,
        )
        object.__setattr__(self, "target", target)

        if type(self.limits) is not CandidateGenerationLimits:
            raise CandidateGenerationError(
                "candidate library limits must be CandidateGenerationLimits"
            )
        if type(self.metadata) is not CandidateGenerationMetadata:
            raise CandidateGenerationError(
                "candidate library metadata must be CandidateGenerationMetadata"
            )
        if isinstance(self.candidates, (str, bytes)):
            raise CandidateGenerationError(
                "candidate library candidates must contain ComponentCandidate objects"
            )
        try:
            candidates = tuple(self.candidates)
        except TypeError as error:
            raise CandidateGenerationError(
                "candidate library candidates must be iterable"
            ) from error
        if any(type(candidate) is not ComponentCandidate for candidate in candidates):
            raise CandidateGenerationError(
                "candidate library candidates must contain ComponentCandidate objects"
            )
        if len(candidates) > self.limits.max_candidates:
            raise CandidateGenerationError(
                "candidate library exceeds its retained-candidate limit"
            )
        if (
            self.metadata.stop_reason is GenerationStopReason.CANDIDATE_LIMIT
            and len(candidates) != self.limits.max_candidates
        ):
            raise CandidateGenerationError(
                "a candidate-limit interruption must fill the retained-candidate budget"
            )
        if self.metadata.retained_count != len(candidates):
            raise CandidateGenerationError(
                "metadata retained_count does not match the candidate sequence"
            )

        expected_length = (target.degree + 1) * (target.degree + 2) // 2
        seen_columns: set[IntegerColumn] = set()
        family_order = tuple(CandidateFamily)
        family_positions = {family: index for index, family in enumerate(family_order)}
        candidate_family_positions = tuple(
            family_positions[candidate.family] for candidate in candidates
        )
        if candidate_family_positions != tuple(sorted(candidate_family_positions)):
            raise CandidateGenerationError(
                "candidate library families must follow canonical generation order"
            )
        considered_families = self.metadata.completed_families
        if self.metadata.interrupted_family is not None:
            considered_families = (
                *considered_families,
                self.metadata.interrupted_family,
            )
        if any(candidate.family not in considered_families for candidate in candidates):
            raise CandidateGenerationError(
                "candidate library contains a family that metadata did not consider"
            )
        for candidate in candidates:
            if candidate.variables != target.variables:
                raise CandidateGenerationError(
                    "candidate variable order does not match the library target"
                )
            if candidate.degree != target.degree:
                raise CandidateGenerationError(
                    "candidate degree does not match the library target"
                )
            if len(candidate.column) != expected_length:
                raise CandidateGenerationError(
                    "candidate column length does not match the target triangle"
                )
            if candidate.column in seen_columns:
                raise CandidateGenerationError(
                    "candidate library cannot contain duplicate canonical columns"
                )
            seen_columns.add(candidate.column)

        _validate_configured_candidate_order(
            candidates,
            target.degree,
            self.limits,
            self.metadata,
        )
        object.__setattr__(self, "candidates", candidates)

    @property
    def complete(self) -> bool:
        """Return whether every candidate in the configured finite scope was considered."""
        return self.metadata.complete


def _monomial_components(
    degree: int,
    variables: Variables,
) -> Iterator[MonomialComponent]:
    """Yield every coefficient-one monomial in canonical target-degree order."""
    for row in _triangle_exponent_rows(degree):
        for exponent in row:
            yield MonomialComponent(exponent=exponent, variables=variables)


def _parity_matches(
    first: tuple[int, int, int],
    second: tuple[int, int, int],
) -> bool:
    """Return whether two exponent endpoints have an integer lattice midpoint."""
    return all(
        (left - right) % 2 == 0 for left, right in zip(first, second, strict=True)
    )


def _binomial_square_components(
    degree: int,
    variables: Variables,
    limits: CandidateGenerationLimits,
    check_time: TimeCheck,
) -> Iterator[SquareComponent]:
    """Yield bounded parity-compatible weighted binomial square placements."""
    exponents: list[tuple[int, int, int]] = []
    for row in _triangle_exponent_rows(degree):
        for exponent in row:
            check_time()
            exponents.append(exponent)

    cached_ratios: list[sp.Rational] = []
    ratio_scope_complete = False
    for first, second in combinations(exponents, 2):
        check_time()
        if not _parity_matches(first, second):
            continue

        multiplier = tuple(
            min(left, right) for left, right in zip(first, second, strict=True)
        )
        base_degree = degree - sum(multiplier)
        if base_degree > limits.max_base_degree:
            continue
        first_factor = tuple(
            (power - shift) // 2 for power, shift in zip(first, multiplier, strict=True)
        )
        second_factor = tuple(
            (power - shift) // 2
            for power, shift in zip(second, multiplier, strict=True)
        )

        ratios: Iterator[sp.Rational]
        if ratio_scope_complete:
            ratios = iter(cached_ratios)
        else:
            ratios = _bounded_square_ratios(
                limits.max_ratio_numerator,
                limits.max_ratio_denominator,
                check_time,
            )

        for ratio in ratios:
            check_time()
            if not ratio_scope_complete:
                cached_ratios.append(ratio)
            factor = HomogeneousPolynomial.from_terms(
                {
                    first_factor: 1,
                    second_factor: -ratio,
                },
                variables=variables,
            )
            yield SquareComponent(factor=factor, multiplier=multiplier)
        ratio_scope_complete = True


def _schur_components(
    degree: int,
    variables: Variables,
    limits: CandidateGenerationLimits,
    check_time: TimeCheck,
) -> Iterator[SchurComponent]:
    """Yield cubic and quintic Schur power dilations with monomial translations."""
    for schur_degree in _SCHUR_DEGREES:
        argument_power = 1
        while schur_degree * argument_power <= degree:
            base_degree = schur_degree * argument_power
            if base_degree > limits.max_base_degree:
                break
            arguments = (
                (argument_power, 0, 0),
                (0, argument_power, 0),
                (0, 0, argument_power),
            )
            multiplier_degree = degree - base_degree
            for row in _triangle_exponent_rows(multiplier_degree):
                for multiplier in row:
                    check_time()
                    yield SchurComponent(
                        schur_degree=schur_degree,
                        arguments=arguments,
                        variables=variables,
                        multiplier=multiplier,
                    )
            argument_power += 1


def _time_limit_reached(started_at: float, max_seconds: float) -> bool:
    """Return whether the cooperative monotonic generation budget is exhausted."""
    return _monotonic() - started_at >= max_seconds


@dataclass(slots=True, kw_only=True)
class _GenerationState:
    """Track one mutable enumeration and freeze it into a public candidate library."""

    target: HomogeneousPolynomial
    limits: CandidateGenerationLimits
    started_at: float
    candidates: list[ComponentCandidate] = field(default_factory=list)
    seen_columns: set[IntegerColumn] = field(default_factory=set)
    completed_families: list[CandidateFamily] = field(default_factory=list)
    attempted_count: int = 0
    duplicate_count: int = 0
    zero_count: int = 0

    def time_limit_reached(self) -> bool:
        """Return whether this enumeration has exhausted its cooperative deadline."""
        return _time_limit_reached(self.started_at, self.limits.max_seconds)

    def require_time_remaining(self) -> None:
        """Raise the private stop signal when family preparation exhausts the deadline."""
        if self.time_limit_reached():
            raise _GenerationTimeLimitReached

    def build_library(
        self,
        *,
        stop_reason: GenerationStopReason | None = None,
        interrupted_family: CandidateFamily | None = None,
    ) -> CandidateLibrary:
        """Copy current candidates and counts into a validated immutable result."""
        metadata = CandidateGenerationMetadata(
            complete=stop_reason is None,
            stop_reason=stop_reason,
            attempted_count=self.attempted_count,
            retained_count=len(self.candidates),
            duplicate_count=self.duplicate_count,
            zero_count=self.zero_count,
            completed_families=tuple(self.completed_families),
            interrupted_family=interrupted_family,
        )
        return CandidateLibrary(
            target=self.target,
            candidates=tuple(self.candidates),
            limits=self.limits,
            metadata=metadata,
        )


def generate_candidates(
    target: HomogeneousPolynomial,
    limits: CandidateGenerationLimits | None = None,
) -> CandidateLibrary:
    """Generate a budgeted deterministic library in the target's exact triangle basis."""
    if not isinstance(target, HomogeneousPolynomial):
        raise PolynomialInputError(
            "generate_candidates() requires a HomogeneousPolynomial"
        )
    target = HomogeneousPolynomial.from_terms(
        target.coefficients,
        variables=target.variables,
    )
    if limits is None:
        limits = CandidateGenerationLimits()
    elif type(limits) is not CandidateGenerationLimits:
        raise CandidateGenerationError(
            "limits must be a CandidateGenerationLimits object or None"
        )

    state = _GenerationState(
        target=target,
        limits=limits,
        started_at=_monotonic(),
    )

    family_iterators: tuple[tuple[CandidateFamily, Iterator[LiftedPrimitive]], ...] = (
        (
            CandidateFamily.MONOMIAL,
            _monomial_components(target.degree, target.variables),
        ),
        (
            CandidateFamily.BINOMIAL_SQUARE,
            _binomial_square_components(
                target.degree,
                target.variables,
                limits,
                state.require_time_remaining,
            ),
        ),
        (
            CandidateFamily.SCHUR,
            _schur_components(
                target.degree,
                target.variables,
                limits,
                state.require_time_remaining,
            ),
        ),
    )
    for family, components in family_iterators:
        if state.time_limit_reached():
            return state.build_library(
                stop_reason=GenerationStopReason.TIME_LIMIT,
                interrupted_family=family,
            )

        component_iterator = iter(components)
        while True:
            try:
                component = next(component_iterator)
            except StopIteration:
                break
            except _GenerationTimeLimitReached:
                return state.build_library(
                    stop_reason=GenerationStopReason.TIME_LIMIT,
                    interrupted_family=family,
                )
            if state.time_limit_reached():
                return state.build_library(
                    stop_reason=GenerationStopReason.TIME_LIMIT,
                    interrupted_family=family,
                )
            if (
                family is CandidateFamily.MONOMIAL
                and len(state.candidates) >= limits.max_candidates
            ):
                state.attempted_count += 1
                return state.build_library(
                    stop_reason=GenerationStopReason.CANDIDATE_LIMIT,
                    interrupted_family=family,
                )
            state.attempted_count += 1
            try:
                candidate = ComponentCandidate(family=family, component=component)
            except _ZeroCandidateError:
                state.zero_count += 1
                if state.time_limit_reached():
                    return state.build_library(
                        stop_reason=GenerationStopReason.TIME_LIMIT,
                        interrupted_family=family,
                    )
                continue

            if state.time_limit_reached():
                return state.build_library(
                    stop_reason=GenerationStopReason.TIME_LIMIT,
                    interrupted_family=family,
                )
            if candidate.column in state.seen_columns:
                state.duplicate_count += 1
                continue
            if len(state.candidates) >= limits.max_candidates:
                return state.build_library(
                    stop_reason=GenerationStopReason.CANDIDATE_LIMIT,
                    interrupted_family=family,
                )

            state.candidates.append(candidate)
            state.seen_columns.add(candidate.column)

        state.completed_families.append(family)

    return state.build_library()

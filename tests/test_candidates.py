"""Public contracts for finite, deterministic candidate generation."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from typing import Any, TypeAlias

import pytest
import sympy as sp

import triangle_method.candidates as candidate_module
from triangle_method import (
    CandidateFamily,
    CandidateGenerationError,
    CandidateGenerationLimits,
    CandidateGenerationMetadata,
    CandidateLibrary,
    ComponentCandidate,
    DecompositionCertificate,
    GenerationStopReason,
    HomogeneousPolynomial,
    MonomialComponent,
    PolynomialInputError,
    SchurComponent,
    SquareComponent,
    coefficient_rows,
    generate_candidates,
    triangle_exponents,
    verify_certificate,
)

Variables: TypeAlias = tuple[sp.Symbol, sp.Symbol, sp.Symbol]


def _target_of_degree(
    degree: int,
    variables: Variables,
) -> HomogeneousPolynomial:
    """Build a sparse target whose coefficients do not guide candidate selection."""
    return HomogeneousPolynomial.from_terms(
        {(degree, 0, 0): 1},
        variables=variables,
    )


def _limits(**overrides: object) -> CandidateGenerationLimits:
    """Return generous operational limits with the documented finite defaults."""
    values: dict[str, object] = {
        "max_candidates": 100_000,
        "max_seconds": 30.0,
        "max_ratio_numerator": 2,
        "max_ratio_denominator": 2,
        "max_base_degree": 10,
    }
    values.update(overrides)
    return CandidateGenerationLimits(**values)  # type: ignore[arg-type]


def _complete_metadata(*, retained_count: int) -> CandidateGenerationMetadata:
    """Build complete metadata suitable for direct CandidateLibrary validation tests."""
    return CandidateGenerationMetadata(
        complete=True,
        stop_reason=None,
        attempted_count=retained_count,
        retained_count=retained_count,
        duplicate_count=0,
        zero_count=0,
        completed_families=tuple(CandidateFamily),
        interrupted_family=None,
    )


def test_candidate_api_has_stable_string_enums_and_root_exports() -> None:
    """Expose the finite-generation records, error, enums, and entry point at package root."""
    assert issubclass(CandidateFamily, str)
    assert tuple(family.value for family in CandidateFamily) == (
        "monomial",
        "binomial_square",
        "schur",
    )
    assert issubclass(GenerationStopReason, str)
    assert tuple(reason.value for reason in GenerationStopReason) == (
        "candidate_limit",
        "time_limit",
    )
    assert issubclass(CandidateGenerationError, ValueError)
    assert CandidateGenerationLimits.__module__.startswith("triangle_method")
    assert CandidateGenerationMetadata.__module__.startswith("triangle_method")
    assert ComponentCandidate.__module__.startswith("triangle_method")
    assert CandidateLibrary.__module__.startswith("triangle_method")
    assert callable(generate_candidates)


def test_default_limits_expose_exact_reduced_square_ratios() -> None:
    """Keep the finite default scope explicit and ratio arithmetic exactly rational."""
    limits = CandidateGenerationLimits()

    assert limits.max_candidates == 10_000
    assert limits.max_seconds == 5.0
    assert type(limits.max_seconds) is float
    assert limits.max_ratio_numerator == 2
    assert limits.max_ratio_denominator == 2
    assert limits.max_base_degree == 10
    assert limits.square_ratios == (
        sp.Rational(1, 2),
        sp.Integer(1),
        sp.Integer(2),
    )
    assert all(isinstance(ratio, sp.Rational) for ratio in limits.square_ratios)

    expanded = CandidateGenerationLimits(
        max_ratio_numerator=3,
        max_ratio_denominator=3,
    )
    assert expanded.square_ratios == (
        sp.Rational(1, 3),
        sp.Rational(1, 2),
        sp.Rational(2, 3),
        sp.Integer(1),
        sp.Rational(3, 2),
        sp.Integer(2),
        sp.Integer(3),
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("max_candidates", -1),
        ("max_candidates", True),
        ("max_candidates", 1.5),
        ("max_ratio_numerator", 0),
        ("max_ratio_numerator", False),
        ("max_ratio_denominator", 0),
        ("max_ratio_denominator", 2.0),
        ("max_base_degree", -1),
        ("max_base_degree", True),
        ("max_seconds", -0.01),
        ("max_seconds", float("inf")),
        ("max_seconds", float("nan")),
        ("max_seconds", 10**1000),
        ("max_seconds", True),
        ("max_seconds", "5"),
    ],
)
def test_generation_limits_reject_invalid_bounds(field: str, value: object) -> None:
    """Reject negative, non-finite, boolean, and wrong-kind generation bounds."""
    with pytest.raises(CandidateGenerationError):
        CandidateGenerationLimits(**{field: value})  # type: ignore[arg-type]


def test_integer_time_limit_is_copied_to_a_finite_float() -> None:
    """Accept an integer elapsed-time budget while storing one stable float value."""
    limits = CandidateGenerationLimits(max_seconds=7)

    assert limits.max_seconds == 7.0
    assert type(limits.max_seconds) is float


@pytest.mark.parametrize("bad_target", [object(), 1, sp.Symbol("x")])
def test_generate_candidates_rejects_unvalidated_targets(bad_target: object) -> None:
    """Require callers to use the package's exact homogeneous polynomial model."""
    with pytest.raises(PolynomialInputError):
        generate_candidates(bad_target)  # type: ignore[arg-type]


@pytest.mark.parametrize("bad_limits", [object(), {}, 1])
def test_generate_candidates_rejects_unvalidated_limit_records(
    bad_limits: object,
    ternary_symbols: Variables,
) -> None:
    """Reject mappings and unrelated objects instead of silently interpreting limits."""
    target = _target_of_degree(2, ternary_symbols)

    with pytest.raises(CandidateGenerationError):
        generate_candidates(target, limits=bad_limits)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("degree", "family_counts"),
    [
        (0, (1, 0, 0)),
        (1, (3, 0, 0)),
        (2, (6, 9, 0)),
        (3, (10, 27, 1)),
    ],
)
def test_small_degree_counts_and_family_order_are_deterministic(
    degree: int,
    family_counts: tuple[int, int, int],
    ternary_symbols: Variables,
) -> None:
    """Lock the canonical family blocks and exact counts for the smallest degrees."""
    library = generate_candidates(
        _target_of_degree(degree, ternary_symbols),
        limits=_limits(),
    )
    expected_families = tuple(
        family
        for family, count in zip(CandidateFamily, family_counts, strict=True)
        for _ in range(count)
    )

    assert tuple(candidate.family for candidate in library.candidates) == (
        expected_families
    )
    assert len(library.candidates) == sum(family_counts)
    assert library.complete
    assert library.metadata == CandidateGenerationMetadata(
        complete=True,
        stop_reason=None,
        attempted_count=sum(family_counts),
        retained_count=sum(family_counts),
        duplicate_count=0,
        zero_count=0,
        completed_families=tuple(CandidateFamily),
        interrupted_family=None,
    )


def test_monomials_form_the_identity_columns_in_triangle_order(
    ternary_symbols: Variables,
) -> None:
    """Place one coefficient-one monomial at every canonical target position."""
    degree = 3
    library = generate_candidates(
        _target_of_degree(degree, ternary_symbols),
        limits=_limits(),
    )
    monomials = tuple(
        candidate
        for candidate in library.candidates
        if candidate.family is CandidateFamily.MONOMIAL
    )
    exponents = tuple(
        exponent for row in triangle_exponents(degree) for exponent in row
    )

    components = tuple(candidate.component for candidate in monomials)
    assert all(type(component) is MonomialComponent for component in components)
    assert tuple(component.exponent for component in components) == exponents  # type: ignore[union-attr]
    for index, candidate in enumerate(monomials):
        expected_column = tuple(
            sp.Integer(position == index) for position in range(len(exponents))
        )
        assert candidate.column == expected_column
        assert candidate.expansion_scale == 1


def test_same_degree_targets_receive_the_same_candidate_sequence(
    ternary_symbols: Variables,
) -> None:
    """Make candidate selection independent of sparse coefficients and target zeros."""
    degree = 3
    sparse = _target_of_degree(degree, ternary_symbols)
    dense = HomogeneousPolynomial.from_terms(
        {
            exponent: index + 1
            for index, exponent in enumerate(
                exponent for row in triangle_exponents(degree) for exponent in row
            )
        },
        variables=ternary_symbols,
    )
    limits = _limits()

    sparse_library = generate_candidates(sparse, limits=limits)
    dense_library = generate_candidates(dense, limits=limits)

    assert sparse != dense
    assert sparse_library.candidates == dense_library.candidates
    assert sparse_library.metadata == dense_library.metadata
    assert sparse_library.limits == dense_library.limits


def test_generation_copies_the_target_into_the_canonical_base_model(
    ternary_symbols: Variables,
) -> None:
    """Detach library identity from a caller-owned polynomial object and subclass."""

    class DerivedPolynomial(HomogeneousPolynomial):
        pass

    target = DerivedPolynomial.from_terms(
        {(2, 0, 0): 2, (0, 2, 0): -1},
        variables=ternary_symbols,
    )
    library = generate_candidates(target, limits=_limits())

    assert type(library.target) is HomogeneousPolynomial
    assert library.target is not target
    assert library.target.variables == target.variables
    assert dict(library.target.coefficients) == dict(target.coefficients)


def test_candidate_cap_stops_on_the_next_unique_column(
    ternary_symbols: Variables,
) -> None:
    """Retain the exact prefix and classify the first over-budget proposal as attempted."""
    library = generate_candidates(
        _target_of_degree(2, ternary_symbols),
        limits=_limits(max_candidates=6),
    )

    assert len(library.candidates) == 6
    assert all(
        candidate.family is CandidateFamily.MONOMIAL for candidate in library.candidates
    )
    assert library.metadata == CandidateGenerationMetadata(
        complete=False,
        stop_reason=GenerationStopReason.CANDIDATE_LIMIT,
        attempted_count=7,
        retained_count=6,
        duplicate_count=0,
        zero_count=0,
        completed_families=(CandidateFamily.MONOMIAL,),
        interrupted_family=CandidateFamily.BINOMIAL_SQUARE,
    )


def test_candidate_cap_equal_to_final_count_reports_completion(
    ternary_symbols: Variables,
) -> None:
    """Avoid a false interruption when the retained budget exactly fits the library."""
    library = generate_candidates(
        _target_of_degree(2, ternary_symbols),
        limits=_limits(max_candidates=15),
    )

    assert len(library.candidates) == 15
    assert library.complete
    assert library.metadata.stop_reason is None
    assert library.metadata.completed_families == tuple(CandidateFamily)


def test_candidate_cap_pulls_only_the_needed_ratio_prefix(
    monkeypatch: pytest.MonkeyPatch,
    ternary_symbols: Variables,
) -> None:
    """Stop a large rational scope without materializing ratios beyond the cap trigger."""
    original = candidate_module._bounded_square_ratios
    pulled: list[sp.Rational] = []

    def guarded_ratios(*args: Any, **kwargs: Any) -> Any:
        """Expose at most the two ratios needed to retain one square and detect the next."""
        for ratio in original(*args, **kwargs):
            pulled.append(ratio)
            if len(pulled) > 2:
                raise AssertionError(
                    "candidate generation consumed an eager ratio suffix"
                )
            yield ratio

    monkeypatch.setattr(candidate_module, "_bounded_square_ratios", guarded_ratios)
    library = generate_candidates(
        _target_of_degree(2, ternary_symbols),
        limits=_limits(
            max_candidates=7,
            max_ratio_numerator=100,
            max_ratio_denominator=100,
        ),
    )

    assert pulled == [sp.Rational(1, 100), sp.Rational(1, 99)]
    assert len(library.candidates) == 7
    assert library.metadata.stop_reason is GenerationStopReason.CANDIDATE_LIMIT


def test_zero_candidate_cap_returns_an_empty_incomplete_prefix(
    ternary_symbols: Variables,
) -> None:
    """Count the first new monomial proposal without retaining it under a zero cap."""
    library = generate_candidates(
        _target_of_degree(2, ternary_symbols),
        limits=_limits(max_candidates=0),
    )

    assert library.candidates == ()
    assert library.metadata.attempted_count == 1
    assert library.metadata.retained_count == 0
    assert library.metadata.stop_reason is GenerationStopReason.CANDIDATE_LIMIT
    assert library.metadata.completed_families == ()
    assert library.metadata.interrupted_family is CandidateFamily.MONOMIAL


def test_cooperative_time_limit_returns_the_exact_attempted_prefix(
    monkeypatch: pytest.MonkeyPatch,
    ternary_symbols: Variables,
) -> None:
    """Report an expansion that crossed the fake-clock deadline without retaining it."""
    ticks = iter((0.0, 0.0, 0.0, 2.0))
    monkeypatch.setattr(candidate_module, "_monotonic", lambda: next(ticks))

    library = generate_candidates(
        _target_of_degree(2, ternary_symbols),
        limits=_limits(max_seconds=1.0),
    )

    assert library.candidates == ()
    assert library.metadata == CandidateGenerationMetadata(
        complete=False,
        stop_reason=GenerationStopReason.TIME_LIMIT,
        attempted_count=1,
        retained_count=0,
        duplicate_count=0,
        zero_count=0,
        completed_families=(),
        interrupted_family=CandidateFamily.MONOMIAL,
    )


def test_base_degree_limit_restricts_scope_without_marking_it_incomplete(
    ternary_symbols: Variables,
) -> None:
    """Treat primitive-degree bounds as the requested scope while keeping monomials."""
    target = _target_of_degree(4, ternary_symbols)
    monomial_only = generate_candidates(
        target,
        limits=_limits(max_base_degree=1),
    )
    bounded = generate_candidates(
        target,
        limits=_limits(max_base_degree=3),
    )

    assert monomial_only.complete
    assert len(monomial_only.candidates) == 15
    assert {candidate.family for candidate in monomial_only.candidates} == {
        CandidateFamily.MONOMIAL
    }

    assert bounded.complete
    assert len(bounded.candidates) == 72
    assert {candidate.family for candidate in bounded.candidates} == set(
        CandidateFamily
    )
    for candidate in bounded.candidates:
        if type(candidate.component) is SquareComponent:
            assert 2 * candidate.component.factor.degree <= 3
        elif type(candidate.component) is SchurComponent:
            argument_degree = sum(candidate.component.arguments[0])
            assert candidate.component.schur_degree * argument_degree <= 3


def test_component_candidate_preserves_positive_scale_and_recovers_weight(
    ternary_symbols: Variables,
) -> None:
    """Relate one primitive expansion to its integer column and exact solver weight."""
    x, y, _ = ternary_symbols
    factor = HomogeneousPolynomial.from_expr(
        2 * x - 2 * y,
        variables=ternary_symbols,
    )
    candidate = ComponentCandidate(
        family=CandidateFamily.BINOMIAL_SQUARE,
        component=SquareComponent(factor=factor),
    )
    flattened_expansion = tuple(
        coefficient
        for row in coefficient_rows(candidate.expand())
        for coefficient in row
    )

    assert candidate.column == (1, -2, 0, 1, 0, 0)
    assert candidate.expansion_scale == 4
    assert flattened_expansion == tuple(
        candidate.expansion_scale * coefficient for coefficient in candidate.column
    )

    weighted = candidate.weighted_component(8)
    assert weighted.weight == 2
    target = HomogeneousPolynomial.from_expr(
        8 * (x - y) ** 2,
        variables=ternary_symbols,
    )
    report = verify_certificate(
        DecompositionCertificate(target=target, terms=(weighted,))
    )
    assert report.valid, report.errors
    assert report.reconstructed == target
    assert report.residual is not None and report.residual.is_zero


@pytest.mark.parametrize("bad_weight", [-1, sp.Rational(-1, 2), 0.5, True])
def test_candidate_weight_conversion_rejects_invalid_weights(
    bad_weight: object,
    ternary_symbols: Variables,
) -> None:
    """Reject negative or inexact column weights before certificate construction."""
    candidate = ComponentCandidate(
        family=CandidateFamily.MONOMIAL,
        component=MonomialComponent(
            exponent=(1, 0, 0),
            variables=ternary_symbols,
        ),
    )

    with pytest.raises(CandidateGenerationError):
        candidate.weighted_component(bad_weight)  # type: ignore[arg-type]


def test_component_candidate_rejects_wrong_provenance_or_zero_ray(
    ternary_symbols: Variables,
) -> None:
    """Require family/type agreement and a nonzero theorem-backed expansion."""
    monomial = MonomialComponent(
        exponent=(1, 0, 0),
        variables=ternary_symbols,
    )
    with pytest.raises(CandidateGenerationError):
        ComponentCandidate(
            family="monomial",  # type: ignore[arg-type]
            component=monomial,
        )
    with pytest.raises(CandidateGenerationError):
        ComponentCandidate(
            family=CandidateFamily.BINOMIAL_SQUARE,
            component=monomial,
        )

    zero_schur = SchurComponent(
        schur_degree=3,
        arguments=((1, 0, 0), (1, 0, 0), (1, 0, 0)),
        variables=ternary_symbols,
    )
    with pytest.raises(CandidateGenerationError):
        ComponentCandidate(
            family=CandidateFamily.SCHUR,
            component=zero_schur,
        )


@pytest.mark.parametrize(
    "changes",
    [
        {"complete": 1},
        {"stop_reason": "time_limit"},
        {"attempted_count": -1},
        {"attempted_count": 0, "retained_count": 1},
        {"completed_families": (CandidateFamily.MONOMIAL,)},
        {
            "complete": False,
            "stop_reason": None,
            "interrupted_family": CandidateFamily.MONOMIAL,
            "completed_families": (),
        },
        {
            "complete": False,
            "stop_reason": GenerationStopReason.TIME_LIMIT,
            "interrupted_family": CandidateFamily.SCHUR,
            "completed_families": (CandidateFamily.MONOMIAL,),
        },
        {
            "completed_families": (
                CandidateFamily.MONOMIAL,
                CandidateFamily.SCHUR,
            )
        },
    ],
)
def test_metadata_rejects_inconsistent_counts_and_family_states(
    changes: dict[str, Any],
) -> None:
    """Reject contradictory completion, interruption, count, and family-prefix states."""
    values: dict[str, Any] = {
        "complete": True,
        "stop_reason": None,
        "attempted_count": 1,
        "retained_count": 1,
        "duplicate_count": 0,
        "zero_count": 0,
        "completed_families": tuple(CandidateFamily),
        "interrupted_family": None,
    }
    values.update(changes)

    with pytest.raises(CandidateGenerationError):
        CandidateGenerationMetadata(**values)


def test_public_records_are_frozen_and_copy_candidate_sequences(
    ternary_symbols: Variables,
) -> None:
    """Prevent caller mutation of limits, metadata, candidates, and library sequences."""
    target = _target_of_degree(0, ternary_symbols)
    generated = generate_candidates(target, limits=_limits())
    caller_owned_candidates = list(generated.candidates)
    library = CandidateLibrary(
        target=target,
        candidates=caller_owned_candidates,  # type: ignore[arg-type]
        limits=generated.limits,
        metadata=generated.metadata,
    )
    caller_owned_families = list(CandidateFamily)
    metadata = CandidateGenerationMetadata(
        complete=True,
        stop_reason=None,
        attempted_count=0,
        retained_count=0,
        duplicate_count=0,
        zero_count=0,
        completed_families=caller_owned_families,  # type: ignore[arg-type]
        interrupted_family=None,
    )

    caller_owned_candidates.clear()
    caller_owned_families.clear()

    assert library.candidates == generated.candidates
    assert isinstance(library.candidates, tuple)
    assert library.target == target
    assert library.target is not target
    assert metadata.completed_families == tuple(CandidateFamily)
    assert isinstance(metadata.completed_families, tuple)
    with pytest.raises(FrozenInstanceError):
        generated.limits.max_candidates = 1  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        generated.metadata.complete = False  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        generated.candidates[0].column = ()  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        library.candidates = ()  # type: ignore[misc]


def test_candidate_library_rejects_invalid_members_and_metadata(
    ternary_symbols: Variables,
) -> None:
    """Enforce target basis, unique columns, record types, and retained-count agreement."""
    target = _target_of_degree(0, ternary_symbols)
    generated = generate_candidates(target, limits=_limits())
    candidate = generated.candidates[0]

    with pytest.raises(PolynomialInputError):
        CandidateLibrary(
            target=object(),  # type: ignore[arg-type]
            candidates=(),
            limits=generated.limits,
            metadata=_complete_metadata(retained_count=0),
        )
    with pytest.raises(CandidateGenerationError):
        CandidateLibrary(
            target=target,
            candidates="candidate",  # type: ignore[arg-type]
            limits=generated.limits,
            metadata=_complete_metadata(retained_count=0),
        )
    with pytest.raises(CandidateGenerationError):
        CandidateLibrary(
            target=target,
            candidates=(candidate,),
            limits=object(),  # type: ignore[arg-type]
            metadata=generated.metadata,
        )
    with pytest.raises(CandidateGenerationError):
        CandidateLibrary(
            target=target,
            candidates=(candidate,),
            limits=generated.limits,
            metadata=_complete_metadata(retained_count=0),
        )

    duplicate_metadata = _complete_metadata(retained_count=2)
    with pytest.raises(CandidateGenerationError):
        CandidateLibrary(
            target=target,
            candidates=(candidate, candidate),
            limits=generated.limits,
            metadata=duplicate_metadata,
        )

    wrong_degree = ComponentCandidate(
        family=CandidateFamily.MONOMIAL,
        component=MonomialComponent(
            exponent=(1, 0, 0),
            variables=ternary_symbols,
        ),
    )
    with pytest.raises(CandidateGenerationError):
        CandidateLibrary(
            target=target,
            candidates=(wrong_degree,),
            limits=generated.limits,
            metadata=_complete_metadata(retained_count=1),
        )

    reordered_variables = (
        ternary_symbols[1],
        ternary_symbols[0],
        ternary_symbols[2],
    )
    wrong_variables = ComponentCandidate(
        family=CandidateFamily.MONOMIAL,
        component=MonomialComponent(
            exponent=(0, 0, 0),
            variables=reordered_variables,
        ),
    )
    with pytest.raises(CandidateGenerationError):
        CandidateLibrary(
            target=target,
            candidates=(wrong_variables,),
            limits=generated.limits,
            metadata=_complete_metadata(retained_count=1),
        )


def test_candidate_library_rejects_an_underfilled_candidate_limit(
    ternary_symbols: Variables,
) -> None:
    """Require candidate-limit results to contain exactly the configured retained cap."""
    target = _target_of_degree(1, ternary_symbols)
    limits = _limits(max_candidates=2)
    candidate = generate_candidates(target, limits=_limits()).candidates[0]
    metadata = CandidateGenerationMetadata(
        complete=False,
        stop_reason=GenerationStopReason.CANDIDATE_LIMIT,
        attempted_count=2,
        retained_count=1,
        duplicate_count=0,
        zero_count=0,
        completed_families=(),
        interrupted_family=CandidateFamily.MONOMIAL,
    )

    with pytest.raises(CandidateGenerationError):
        CandidateLibrary(
            target=target,
            candidates=(candidate,),
            limits=limits,
            metadata=metadata,
        )


@pytest.mark.parametrize("change", ["missing", "reordered"])
def test_candidate_library_requires_the_canonical_complete_monomial_block(
    change: str,
    ternary_symbols: Variables,
) -> None:
    """Reject complete libraries whose mandatory identity-column block is incomplete."""
    target = _target_of_degree(2, ternary_symbols)
    generated = generate_candidates(target, limits=_limits(max_base_degree=0))
    candidates = list(generated.candidates)
    if change == "missing":
        candidates.pop()
    else:
        candidates[0], candidates[1] = candidates[1], candidates[0]
    metadata = _complete_metadata(retained_count=len(candidates))

    with pytest.raises(CandidateGenerationError):
        CandidateLibrary(
            target=target,
            candidates=candidates,  # type: ignore[arg-type]
            limits=_limits(max_base_degree=0),
            metadata=metadata,
        )


@pytest.mark.parametrize("degree", [2, 4])
def test_candidate_library_rejects_reordered_generated_family_blocks(
    degree: int,
    ternary_symbols: Variables,
) -> None:
    """Preserve canonical endpoint and Schur-shift order in stored complete libraries."""
    generated = generate_candidates(
        _target_of_degree(degree, ternary_symbols),
        limits=_limits(),
    )
    family = CandidateFamily.BINOMIAL_SQUARE if degree == 2 else CandidateFamily.SCHUR
    candidates = list(generated.candidates)
    positions = [
        index
        for index, candidate in enumerate(candidates)
        if candidate.family is family
    ]
    assert len(positions) >= 2
    first, second = positions[-2:]
    candidates[first], candidates[second] = candidates[second], candidates[first]

    with pytest.raises(CandidateGenerationError):
        CandidateLibrary(
            target=generated.target,
            candidates=candidates,  # type: ignore[arg-type]
            limits=generated.limits,
            metadata=generated.metadata,
        )


def test_candidate_library_rejects_squares_outside_the_configured_family(
    ternary_symbols: Variables,
) -> None:
    """Reject trinomial, reversed, and out-of-range square provenance records."""
    x, y, z = ternary_symbols
    target = _target_of_degree(2, ternary_symbols)
    limits = _limits()
    monomials = generate_candidates(
        target,
        limits=_limits(max_base_degree=0),
    ).candidates
    invalid_factors = (x + y - z, y - x, x - 3 * y)

    for expression in invalid_factors:
        invalid = ComponentCandidate(
            family=CandidateFamily.BINOMIAL_SQUARE,
            component=SquareComponent(
                factor=HomogeneousPolynomial.from_expr(
                    expression,
                    variables=ternary_symbols,
                )
            ),
        )
        candidates = (*monomials, invalid)
        metadata = CandidateGenerationMetadata(
            complete=False,
            stop_reason=GenerationStopReason.TIME_LIMIT,
            attempted_count=len(candidates),
            retained_count=len(candidates),
            duplicate_count=0,
            zero_count=0,
            completed_families=(CandidateFamily.MONOMIAL,),
            interrupted_family=CandidateFamily.BINOMIAL_SQUARE,
        )

        with pytest.raises(CandidateGenerationError):
            CandidateLibrary(
                target=target,
                candidates=candidates,
                limits=limits,
                metadata=metadata,
            )


def test_candidate_library_rejects_unextracted_or_overdegree_squares(
    ternary_symbols: Variables,
) -> None:
    """Enforce maximal monomial extraction and the configured square base degree."""
    x, y, z = ternary_symbols
    target = _target_of_degree(4, ternary_symbols)
    limits = _limits(max_base_degree=2)
    monomials = generate_candidates(
        target,
        limits=_limits(max_base_degree=0),
    ).candidates
    invalid_components = (
        SquareComponent(
            factor=HomogeneousPolynomial.from_expr(
                x * y - x * z,
                variables=ternary_symbols,
            )
        ),
        SquareComponent(
            factor=HomogeneousPolynomial.from_expr(
                x**2 - y**2,
                variables=ternary_symbols,
            )
        ),
    )

    for component in invalid_components:
        invalid = ComponentCandidate(
            family=CandidateFamily.BINOMIAL_SQUARE,
            component=component,
        )
        candidates = (*monomials, invalid)
        metadata = CandidateGenerationMetadata(
            complete=False,
            stop_reason=GenerationStopReason.TIME_LIMIT,
            attempted_count=len(candidates),
            retained_count=len(candidates),
            duplicate_count=0,
            zero_count=0,
            completed_families=(CandidateFamily.MONOMIAL,),
            interrupted_family=CandidateFamily.BINOMIAL_SQUARE,
        )

        with pytest.raises(CandidateGenerationError):
            CandidateLibrary(
                target=target,
                candidates=candidates,
                limits=limits,
                metadata=metadata,
            )


def test_candidate_library_rejects_schur_forms_outside_the_configured_family(
    ternary_symbols: Variables,
) -> None:
    """Restrict stored Schur provenance to cubic/quintic pure-power substitutions."""
    target = _target_of_degree(4, ternary_symbols)
    monomials = generate_candidates(
        target,
        limits=_limits(max_base_degree=0),
    ).candidates
    invalid_cases = (
        (
            SchurComponent(
                schur_degree=4,
                arguments=((1, 0, 0), (0, 1, 0), (0, 0, 1)),
                variables=ternary_symbols,
            ),
            _limits(),
        ),
        (
            SchurComponent(
                schur_degree=3,
                arguments=((0, 1, 0), (1, 0, 0), (0, 0, 1)),
                variables=ternary_symbols,
                multiplier=(1, 0, 0),
            ),
            _limits(),
        ),
        (
            SchurComponent(
                schur_degree=3,
                arguments=((1, 0, 0), (0, 1, 0), (0, 0, 1)),
                variables=ternary_symbols,
                multiplier=(1, 0, 0),
            ),
            _limits(max_base_degree=2),
        ),
    )

    for component, limits in invalid_cases:
        invalid = ComponentCandidate(
            family=CandidateFamily.SCHUR,
            component=component,
        )
        candidates = (*monomials, invalid)
        metadata = CandidateGenerationMetadata(
            complete=False,
            stop_reason=GenerationStopReason.TIME_LIMIT,
            attempted_count=len(candidates),
            retained_count=len(candidates),
            duplicate_count=0,
            zero_count=0,
            completed_families=(
                CandidateFamily.MONOMIAL,
                CandidateFamily.BINOMIAL_SQUARE,
            ),
            interrupted_family=CandidateFamily.SCHUR,
        )

        with pytest.raises(CandidateGenerationError):
            CandidateLibrary(
                target=target,
                candidates=candidates,
                limits=limits,
                metadata=metadata,
            )

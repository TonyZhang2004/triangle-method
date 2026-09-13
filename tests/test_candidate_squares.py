"""Exact weighted-binomial-square candidate generation tests."""

from __future__ import annotations

from math import gcd
from typing import TypeAlias

import pytest
import sympy as sp

from triangle_method import (
    DecompositionCertificate,
    HomogeneousPolynomial,
    SquareComponent,
    triangle_exponents,
    verify_certificate,
)
from triangle_method.candidates import (
    CandidateFamily,
    CandidateGenerationLimits,
    CandidateLibrary,
    ComponentCandidate,
    generate_candidates,
)

Variables: TypeAlias = tuple[sp.Symbol, sp.Symbol, sp.Symbol]
Exponent: TypeAlias = tuple[int, int, int]


def _target_of_degree(degree: int, variables: Variables) -> HomogeneousPolynomial:
    """Return a sparse nonzero target used only to select a candidate degree."""
    return HomogeneousPolynomial.from_expr(
        variables[0] ** degree,
        variables=variables,
    )


def _library(
    degree: int,
    variables: Variables,
    *,
    limits: CandidateGenerationLimits | None = None,
) -> CandidateLibrary:
    """Generate the configured candidate library for one homogeneous degree."""
    return generate_candidates(_target_of_degree(degree, variables), limits=limits)


def _square_candidates(library: CandidateLibrary) -> tuple[ComponentCandidate, ...]:
    """Select the binomial-square family without changing its generated order."""
    return tuple(
        candidate
        for candidate in library.candidates
        if candidate.family is CandidateFamily.BINOMIAL_SQUARE
    )


def _flatten(polynomial: HomogeneousPolynomial) -> tuple[sp.Rational, ...]:
    """Flatten exact coefficients in the package's canonical triangle order."""
    return tuple(
        polynomial.coefficient(exponent)
        for row in triangle_exponents(polynomial.degree)
        for exponent in row
    )


def _find_encoded_square(
    library: CandidateLibrary,
    *,
    multiplier: Exponent,
    positive_exponent: Exponent,
    negative_exponent: Exponent,
    ratio: sp.Rational | int,
) -> ComponentCandidate:
    """Find one square by its canonical multiplier and ordered binomial factor."""
    expected_factor = {
        positive_exponent: sp.S.One,
        negative_exponent: -sp.Rational(ratio),
    }
    matches = []
    for candidate in _square_candidates(library):
        component = candidate.component
        if (
            type(component) is SquareComponent
            and component.multiplier == multiplier
            and dict(component.factor.coefficients) == expected_factor
        ):
            matches.append(candidate)

    assert len(matches) == 1
    return matches[0]


def _find_expansion(
    library: CandidateLibrary,
    expression: sp.Expr,
) -> ComponentCandidate:
    """Find the unique square candidate with the requested exact expansion."""
    expected = HomogeneousPolynomial.from_expr(
        sp.expand(expression),
        variables=library.target.variables,
    )
    matches = [
        candidate
        for candidate in _square_candidates(library)
        if candidate.expand() == expected
    ]
    assert len(matches) == 1
    return matches[0]


def test_default_ratios_and_degree_two_placements_are_exact(
    ternary_symbols: Variables,
) -> None:
    """Generate all three quadratic endpoint pairs at ratios one-half, one, and two."""
    limits = CandidateGenerationLimits()
    library = _library(2, ternary_symbols, limits=limits)
    squares = _square_candidates(library)

    assert limits.square_ratios == (
        sp.Rational(1, 2),
        sp.Integer(1),
        sp.Integer(2),
    )
    assert library.metadata.complete
    assert len(squares) == 9

    ratio_two = _find_encoded_square(
        library,
        multiplier=(0, 0, 0),
        positive_exponent=(1, 0, 0),
        negative_exponent=(0, 1, 0),
        ratio=2,
    )
    assert ratio_two.column == (1, -4, 0, 4, 0, 0)
    assert ratio_two.expansion_scale == 1
    assert _flatten(ratio_two.expand()) == ratio_two.column

    ratio_half = _find_encoded_square(
        library,
        multiplier=(0, 0, 0),
        positive_exponent=(1, 0, 0),
        negative_exponent=(0, 1, 0),
        ratio=sp.Rational(1, 2),
    )
    assert ratio_half.column == (4, -4, 0, 1, 0, 0)
    assert ratio_half.expansion_scale == sp.Rational(1, 4)


def test_odd_degree_square_uses_the_midpoint_and_monomial_shift(
    ternary_symbols: Variables,
) -> None:
    """Encode x(y-2z)^2 at its two endpoints and integral midpoint."""
    x, y, z = ternary_symbols
    candidate = _find_encoded_square(
        _library(3, ternary_symbols),
        multiplier=(1, 0, 0),
        positive_exponent=(0, 1, 0),
        negative_exponent=(0, 0, 1),
        ratio=2,
    )

    assert sp.expand(candidate.expand().to_sympy() - x * (y - 2 * z) ** 2) == 0
    assert candidate.column == (0, 0, 0, 1, -4, 4, 0, 0, 0, 0)
    assert candidate.expansion_scale == 1


def test_nonadjacent_quartic_and_maximal_multiplier_are_generated(
    ternary_symbols: Variables,
) -> None:
    """Cover distant endpoints and move their full common monomial outside the square."""
    x, y, _ = ternary_symbols
    library = _library(4, ternary_symbols)

    nonadjacent = _find_expansion(library, (x**2 - y**2) ** 2)
    assert type(nonadjacent.component) is SquareComponent
    assert nonadjacent.component.multiplier == (0, 0, 0)
    assert dict(nonadjacent.component.factor.coefficients) == {
        (2, 0, 0): sp.S.One,
        (0, 2, 0): -sp.S.One,
    }

    shifted = _find_expansion(library, x**2 * (x - y) ** 2)
    assert type(shifted.component) is SquareComponent
    assert shifted.component.multiplier == (2, 0, 0)
    assert dict(shifted.component.factor.coefficients) == {
        (1, 0, 0): sp.S.One,
        (0, 1, 0): -sp.S.One,
    }


def test_endpoint_pairs_with_nonintegral_midpoints_are_excluded(
    ternary_symbols: Variables,
) -> None:
    """Reject degree-four endpoints whose coordinate parities do not match."""
    forbidden_endpoints = frozenset(((3, 1, 0), (0, 4, 0)))

    for candidate in _square_candidates(_library(4, ternary_symbols)):
        positive_support = frozenset(
            exponent
            for exponent, coefficient in candidate.expand().coefficients.items()
            if coefficient > 0
        )
        assert positive_support != forbidden_endpoints


def test_ratio_two_thirds_has_primitive_column_and_recoverable_scale(
    ternary_symbols: Variables,
) -> None:
    """Normalize (x-2y/3)^2 to (9,-12,4) and recover certificate weight exactly."""
    limits = CandidateGenerationLimits(
        max_ratio_numerator=3,
        max_ratio_denominator=3,
    )
    library = _library(2, ternary_symbols, limits=limits)
    candidate = _find_encoded_square(
        library,
        multiplier=(0, 0, 0),
        positive_exponent=(1, 0, 0),
        negative_exponent=(0, 1, 0),
        ratio=sp.Rational(2, 3),
    )

    assert candidate.column == (9, -12, 0, 4, 0, 0)
    assert candidate.expansion_scale == sp.Rational(1, 9)
    assert _flatten(candidate.expand()) == tuple(
        candidate.expansion_scale * entry for entry in candidate.column
    )

    column_weight = sp.Rational(5, 9)
    weighted = candidate.weighted_component(column_weight)
    target_terms = {
        exponent: column_weight * entry
        for exponent, entry in zip(
            (exponent for row in triangle_exponents(2) for exponent in row),
            candidate.column,
            strict=True,
        )
    }
    target = HomogeneousPolynomial.from_terms(
        target_terms,
        variables=ternary_symbols,
    )
    certificate = DecompositionCertificate(target=target, terms=(weighted,))

    assert weighted.weight == 5
    assert verify_certificate(certificate).valid


def test_required_square_components_for_the_five_decomposition_fixtures_exist(
    ternary_symbols: Variables,
) -> None:
    """Retain every square used by the five initial multi-component decompositions."""
    x, y, z = ternary_symbols
    requirements = {
        "quadratic_squares": (
            (2, (x - y) ** 2),
            (2, (y - z) ** 2),
            (2, (z - x) ** 2),
        ),
        "cubic_weighted_squares": (
            (3, x * (y - z) ** 2),
            (3, y * (z - x) ** 2),
            (3, z * (x - y) ** 2),
        ),
        "quartic_squares": (
            (4, (x**2 - y**2) ** 2),
            (4, (y**2 - z**2) ** 2),
            (4, (z**2 - x**2) ** 2),
        ),
        "quartic_schur_lift": (),
        "quintic_schur_plus_squares": (
            (5, x * y * z * (x - y) ** 2),
            (5, x * y * z * (y - z) ** 2),
            (5, x * y * z * (z - x) ** 2),
        ),
    }
    libraries = {degree: _library(degree, ternary_symbols) for degree in (2, 3, 4, 5)}

    assert tuple(requirements) == (
        "quadratic_squares",
        "cubic_weighted_squares",
        "quartic_squares",
        "quartic_schur_lift",
        "quintic_schur_plus_squares",
    )
    for required in requirements.values():
        for degree, expression in required:
            _find_expansion(libraries[degree], expression)


@pytest.mark.parametrize("degree", [2, 3, 4, 5])
def test_every_square_has_exact_degree_variables_column_and_certificate(
    degree: int,
    ternary_symbols: Variables,
) -> None:
    """Check every generated square against expansion, scaling, and the verifier."""
    x, y, z = ternary_symbols
    variables = (z, x, y)
    library = _library(degree, variables)

    for candidate in _square_candidates(library):
        component = candidate.component
        expanded = candidate.expand()
        flattened = _flatten(expanded)

        assert type(component) is SquareComponent
        assert component.variables == variables
        assert component.degree == degree
        assert expanded == component.expand()
        assert not expanded.is_zero
        assert expanded.degree == degree
        assert candidate.expansion_scale > 0
        assert all(isinstance(entry, sp.Integer) for entry in candidate.column)
        assert flattened == tuple(
            candidate.expansion_scale * entry for entry in candidate.column
        )
        assert gcd(*(abs(int(entry)) for entry in candidate.column)) == 1
        assert sum(entry != 0 for entry in candidate.column) == 3

        weighted = candidate.weighted_component(candidate.expansion_scale)
        certificate = DecompositionCertificate(target=expanded, terms=(weighted,))
        assert weighted.weight == 1
        assert verify_certificate(certificate).valid


def test_generation_is_deterministic_and_independent_of_target_zeros(
    ternary_symbols: Variables,
) -> None:
    """Return one stable square library for every target with the same degree and basis."""
    x, _, _ = ternary_symbols
    sparse_target = _target_of_degree(4, ternary_symbols)
    dense_target = HomogeneousPolynomial.from_terms(
        {exponent: 1 for row in triangle_exponents(4) for exponent in row},
        variables=ternary_symbols,
    )

    first = generate_candidates(sparse_target)
    repeated = generate_candidates(sparse_target)
    dense = generate_candidates(dense_target)

    assert first.candidates == repeated.candidates
    assert first.metadata == repeated.metadata
    assert _square_candidates(first) == _square_candidates(dense)
    assert _find_expansion(first, (x**2 - ternary_symbols[1] ** 2) ** 2)


def test_positive_scale_aliases_share_a_column_without_sign_flipping(
    ternary_symbols: Variables,
) -> None:
    """Normalize positive square aliases to one signed ray and retain exact scales."""
    x, y, _ = ternary_symbols

    def candidate_for(factor_expression: sp.Expr) -> ComponentCandidate:
        factor = HomogeneousPolynomial.from_expr(
            factor_expression,
            variables=ternary_symbols,
        )
        return ComponentCandidate(
            family=CandidateFamily.BINOMIAL_SQUARE,
            component=SquareComponent(factor=factor),
        )

    base = candidate_for(x - 2 * y)
    positive_alias = candidate_for(2 * x - 4 * y)
    sign_alias = candidate_for(-x + 2 * y)

    assert base.column == positive_alias.column == sign_alias.column
    assert base.column == (1, -4, 0, 4, 0, 0)
    assert base.expansion_scale == 1
    assert positive_alias.expansion_scale == 4
    assert sign_alias.expansion_scale == 1
    assert base.column != tuple(-entry for entry in base.column)

    weighted = positive_alias.weighted_component(4)
    assert weighted.weight == 1
    certificate = DecompositionCertificate(
        target=positive_alias.expand(),
        terms=(weighted,),
    )
    assert verify_certificate(certificate).valid

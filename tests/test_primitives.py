"""Exact expansion and validation tests for theorem-backed primitives."""

from __future__ import annotations

from typing import Any

import pytest
import sympy as sp

from triangle_method import (
    HomogeneousPolynomial,
    MonomialComponent,
    PrimitiveInputError,
    SchurComponent,
    SquareComponent,
)

Exponent = tuple[int, int, int]


def _assert_expands_to(component: Any, expected: sp.Expr) -> None:
    """Compare a primitive's exact polynomial expansion with an independent formula."""

    expanded = component.expand()

    assert isinstance(expanded, HomogeneousPolynomial)
    assert sp.expand(expanded.to_sympy() - expected) == 0
    assert not expanded.to_sympy().atoms(sp.Float)


def _classic_schur(
    schur_degree: int,
    arguments: tuple[sp.Expr, sp.Expr, sp.Expr],
) -> sp.Expr:
    """Build the defining cyclic Schur expression independently for test expectations."""

    first, second, third = arguments
    return sp.expand(
        first ** (schur_degree - 2) * (first - second) * (first - third)
        + second ** (schur_degree - 2) * (second - third) * (second - first)
        + third ** (schur_degree - 2) * (third - first) * (third - second)
    )


def test_primitive_types_are_available_from_the_package_root() -> None:
    """Keep the three supported theorem-backed components on the public API."""

    assert MonomialComponent.__module__.startswith("triangle_method")
    assert SquareComponent.__module__.startswith("triangle_method")
    assert SchurComponent.__module__.startswith("triangle_method")
    assert issubclass(PrimitiveInputError, ValueError)


def test_monomial_component_expands_in_the_declared_variable_order(
    ternary_symbols: tuple[sp.Symbol, sp.Symbol, sp.Symbol],
) -> None:
    """Interpret one exponent triple against its explicit ordered symbols."""

    x, y, z = ternary_symbols
    component = MonomialComponent(exponent=(2, 1, 3), variables=(z, x, y))

    assert component.variables == (z, x, y)
    assert component.exponent == (2, 1, 3)
    assert component.degree == 6
    _assert_expands_to(component, z**2 * x * y**3)


@pytest.mark.parametrize(
    "exponent",
    [
        (1, 2),
        (1, 2, 3, 4),
        [1, 2, 3],
        (1, -1, 0),
        (1.0, 0, 0),
        (True, 0, 0),
    ],
)
def test_monomial_component_rejects_invalid_exponents(
    exponent: object,
    ternary_symbols: tuple[sp.Symbol, sp.Symbol, sp.Symbol],
) -> None:
    """Require one nonnegative integer exponent for each ordered variable."""

    with pytest.raises(PrimitiveInputError):
        MonomialComponent(
            exponent=exponent,  # type: ignore[arg-type]
            variables=ternary_symbols,
        )


@pytest.mark.parametrize(
    "variables",
    [
        (),
        sp.symbols("x y"),
        (sp.Symbol("x"), sp.Symbol("x"), sp.Symbol("z")),
        (sp.Symbol("x"), "y", sp.Symbol("z")),
    ],
)
def test_monomial_component_rejects_invalid_variable_orders(
    variables: object,
) -> None:
    """Reject incomplete, duplicate, or nonsymbol primitive variable orders."""

    with pytest.raises(PrimitiveInputError):
        MonomialComponent(exponent=(1, 0, 0), variables=variables)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("factor_expression", "expected"),
    [
        (lambda x, y, z: x - 2 * y, lambda x, y, z: (x - 2 * y) ** 2),
        (lambda x, y, z: x + y - z, lambda x, y, z: (x + y - z) ** 2),
    ],
)
def test_square_component_supports_weighted_binomial_and_general_linear_squares(
    factor_expression: Any,
    expected: Any,
    ternary_symbols: tuple[sp.Symbol, sp.Symbol, sp.Symbol],
) -> None:
    """Expand broad homogeneous square factors instead of a fixed coefficient pattern."""

    x, y, z = ternary_symbols
    factor = HomogeneousPolynomial.from_expr(
        factor_expression(x, y, z),
        variables=ternary_symbols,
    )
    component = SquareComponent(factor=factor)

    assert component.variables == ternary_symbols
    assert component.factor == factor
    assert component.multiplier == (0, 0, 0)
    assert component.degree == 2
    _assert_expands_to(component, expected(x, y, z))


def test_square_component_applies_an_exact_monomial_multiplier(
    ternary_symbols: tuple[sp.Symbol, sp.Symbol, sp.Symbol],
) -> None:
    """Multiply a rational homogeneous square by a nonnegative monomial exactly."""

    x, y, z = ternary_symbols
    factor_expression = sp.Rational(1, 2) * x - sp.Rational(2, 3) * y + z
    factor = HomogeneousPolynomial.from_expr(
        factor_expression,
        variables=ternary_symbols,
    )
    component = SquareComponent(factor=factor, multiplier=(2, 1, 0))

    assert component.degree == 5
    assert component.multiplier == (2, 1, 0)
    _assert_expands_to(component, x**2 * y * factor_expression**2)


def test_square_component_rejects_a_zero_factor_with_ambiguous_degree(
    ternary_symbols: tuple[sp.Symbol, sp.Symbol, sp.Symbol],
) -> None:
    """Reject the canonical zero model because it carries no square-factor degree."""

    zero = HomogeneousPolynomial.from_expr(0, variables=ternary_symbols)

    with pytest.raises(PrimitiveInputError, match="nonzero"):
        SquareComponent(factor=zero)


@pytest.mark.parametrize(
    ("factor", "multiplier"),
    [
        (object(), (0, 0, 0)),
        ("x-y", (0, 0, 0)),
        (None, (0, -1, 0)),
        (None, (True, 0, 0)),
        (None, (0, 0)),
    ],
)
def test_square_component_rejects_invalid_factors_or_multipliers(
    factor: object,
    multiplier: object,
    ternary_symbols: tuple[sp.Symbol, sp.Symbol, sp.Symbol],
) -> None:
    """Require an exact homogeneous factor model and a valid monomial multiplier."""

    x, y, _ = ternary_symbols
    valid_factor = HomogeneousPolynomial.from_expr(x - y, variables=ternary_symbols)
    candidate_factor = valid_factor if factor is None else factor

    with pytest.raises(PrimitiveInputError):
        SquareComponent(
            factor=candidate_factor,  # type: ignore[arg-type]
            multiplier=multiplier,  # type: ignore[arg-type]
        )


@pytest.mark.parametrize("schur_degree", [3, 5])
def test_schur_component_matches_the_classic_cyclic_formula(
    schur_degree: int,
    ternary_symbols: tuple[sp.Symbol, sp.Symbol, sp.Symbol],
) -> None:
    """Expand cubic and quintic Schur from their theorem-defining cyclic sums."""

    x, y, z = ternary_symbols
    component = SchurComponent(
        schur_degree=schur_degree,
        arguments=((1, 0, 0), (0, 1, 0), (0, 0, 1)),
        variables=ternary_symbols,
    )

    assert component.degree == schur_degree
    assert component.variables == ternary_symbols
    _assert_expands_to(component, _classic_schur(schur_degree, (x, y, z)))


def test_schur_component_supports_equal_degree_monomial_substitutions_and_shift(
    ternary_symbols: tuple[sp.Symbol, sp.Symbol, sp.Symbol],
) -> None:
    """Substitute nonnegative equal-degree monomials and apply a monomial multiplier."""

    x, y, z = ternary_symbols
    arguments: tuple[Exponent, Exponent, Exponent] = (
        (1, 1, 0),
        (0, 1, 1),
        (1, 0, 1),
    )
    component = SchurComponent(
        schur_degree=3,
        arguments=arguments,
        variables=ternary_symbols,
        multiplier=(1, 0, 0),
    )
    substituted = (x * y, y * z, z * x)

    assert component.arguments == arguments
    assert component.multiplier == (1, 0, 0)
    assert component.degree == 7
    _assert_expands_to(component, x * _classic_schur(3, substituted))


def test_schur_component_retains_formal_degree_when_its_expansion_is_zero(
    ternary_symbols: tuple[sp.Symbol, sp.Symbol, sp.Symbol],
) -> None:
    """Keep substitution degree explicit when repeated Schur arguments cancel exactly."""

    component = SchurComponent(
        schur_degree=5,
        arguments=((1, 0, 0), (1, 0, 0), (1, 0, 0)),
        variables=ternary_symbols,
        multiplier=(0, 2, 0),
    )

    assert component.degree == 7
    assert component.expand().is_zero


@pytest.mark.parametrize("schur_degree", [2, 0, -1, True, 3.0])
def test_schur_component_rejects_invalid_schur_degrees(
    schur_degree: object,
    ternary_symbols: tuple[sp.Symbol, sp.Symbol, sp.Symbol],
) -> None:
    """Require an integer Schur degree of at least three."""

    with pytest.raises(PrimitiveInputError):
        SchurComponent(
            schur_degree=schur_degree,  # type: ignore[arg-type]
            arguments=((1, 0, 0), (0, 1, 0), (0, 0, 1)),
            variables=ternary_symbols,
        )


@pytest.mark.parametrize(
    "arguments",
    [
        (),
        ((1, 0, 0), (0, 1, 0)),
        ((1, 0, 0), (0, 1, 0), (0, 0, 1), (1, 1, 0)),
        ((1, 0, 0), (0, 1, 0), (0, -1, 1)),
        ((1, 0, 0), (0, 1, 0), (0, 0)),
        ((1, 0, 0), (0, 1, 0), (0, 1, 1)),
    ],
)
def test_schur_component_rejects_malformed_or_unequal_degree_arguments(
    arguments: object,
    ternary_symbols: tuple[sp.Symbol, sp.Symbol, sp.Symbol],
) -> None:
    """Require exactly three valid monomial arguments of one common degree."""

    with pytest.raises(PrimitiveInputError):
        SchurComponent(
            schur_degree=3,
            arguments=arguments,  # type: ignore[arg-type]
            variables=ternary_symbols,
        )


@pytest.mark.parametrize("multiplier", [(1, -1, 0), (True, 0, 0), (1, 2)])
def test_schur_component_rejects_invalid_multipliers(
    multiplier: object,
    ternary_symbols: tuple[sp.Symbol, sp.Symbol, sp.Symbol],
) -> None:
    """Require a nonnegative integer exponent triple for a Schur shift."""

    with pytest.raises(PrimitiveInputError):
        SchurComponent(
            schur_degree=3,
            arguments=((1, 0, 0), (0, 1, 0), (0, 0, 1)),
            variables=ternary_symbols,
            multiplier=multiplier,  # type: ignore[arg-type]
        )


def test_primitive_records_are_immutable(
    ternary_symbols: tuple[sp.Symbol, sp.Symbol, sp.Symbol],
) -> None:
    """Keep theorem parameters fixed after primitive validation."""

    component = MonomialComponent(exponent=(1, 0, 0), variables=ternary_symbols)

    with pytest.raises((AttributeError, TypeError)):
        component.exponent = (0, 1, 0)  # type: ignore[misc]

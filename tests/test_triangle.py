"""Regression tests for the canonical coefficient-triangle representation."""

from __future__ import annotations

from typing import Any

import pytest
import sympy as sp

from triangle_method import (
    HomogeneousPolynomial,
    PolynomialInputError,
    coefficient_rows,
    from_coefficient_rows,
    triangle_exponents,
)

x, y, z = sp.symbols("x y z")


def test_all_approved_examples_have_the_expected_coefficient_rows(
    ternary_symbols: tuple[sp.Symbol, sp.Symbol, sp.Symbol],
    approved_polynomial_cases: tuple[Any, ...],
) -> None:
    """Compare every approved polynomial with its independently specified rows."""
    for case in approved_polynomial_cases:
        polynomial = HomogeneousPolynomial.from_expr(
            case.expression,
            variables=ternary_symbols,
        )

        assert coefficient_rows(polynomial) == case.expected_rows, case.name


def test_triangle_exponents_follow_the_canonical_orientation() -> None:
    assert triangle_exponents(3) == (
        ((3, 0, 0),),
        ((2, 1, 0), (2, 0, 1)),
        ((1, 2, 0), (1, 1, 1), (1, 0, 2)),
        ((0, 3, 0), (0, 2, 1), (0, 1, 2), (0, 0, 3)),
    )


@pytest.mark.parametrize("degree", [-1, True, 2.0])
def test_triangle_exponents_reject_invalid_degrees(degree: object) -> None:
    with pytest.raises(PolynomialInputError):
        triangle_exponents(degree)  # type: ignore[arg-type]


def test_coefficient_rows_include_sparse_zeros_and_exact_rationals() -> None:
    expression = x**3 + sp.Rational(2, 3) * x * y * z - sp.Rational(5, 7) * z**3
    polynomial = HomogeneousPolynomial.from_expr(expression, variables=(x, y, z))

    assert coefficient_rows(polynomial) == (
        (sp.Integer(1),),
        (sp.Integer(0), sp.Integer(0)),
        (sp.Integer(0), sp.Rational(2, 3), sp.Integer(0)),
        (sp.Integer(0), sp.Integer(0), sp.Integer(0), sp.Rational(-5, 7)),
    )


def test_quadratic_example_has_the_established_orientation() -> None:
    expression = x**2 + y**2 + z**2 - x * y - y * z - z * x
    polynomial = HomogeneousPolynomial.from_expr(expression, variables=(x, y, z))

    assert coefficient_rows(polynomial) == (
        (sp.Integer(1),),
        (sp.Integer(-1), sp.Integer(-1)),
        (sp.Integer(1), sp.Integer(-1), sp.Integer(1)),
    )


def test_asymmetric_cubic_exposes_variable_order() -> None:
    expression = (
        x**3
        + 2 * x**2 * y
        + 3 * x**2 * z
        + 4 * x * y**2
        + 5 * x * y * z
        + 6 * x * z**2
        + 7 * y**3
        + 8 * y**2 * z
        + 9 * y * z**2
        + 10 * z**3
    )

    xyz_polynomial = HomogeneousPolynomial.from_expr(expression, variables=(x, y, z))
    zyx_polynomial = HomogeneousPolynomial.from_expr(expression, variables=(z, y, x))

    assert coefficient_rows(xyz_polynomial) == (
        (sp.Integer(1),),
        (sp.Integer(2), sp.Integer(3)),
        (sp.Integer(4), sp.Integer(5), sp.Integer(6)),
        (sp.Integer(7), sp.Integer(8), sp.Integer(9), sp.Integer(10)),
    )
    assert coefficient_rows(zyx_polynomial) == (
        (sp.Integer(10),),
        (sp.Integer(9), sp.Integer(6)),
        (sp.Integer(8), sp.Integer(5), sp.Integer(3)),
        (sp.Integer(7), sp.Integer(4), sp.Integer(2), sp.Integer(1)),
    )


def test_rows_round_trip_an_asymmetric_rational_polynomial() -> None:
    rows = (
        (sp.Rational(2, 5),),
        (sp.Rational(-3, 7), sp.Integer(0)),
        (sp.Integer(11), sp.Rational(1, 3), sp.Integer(-4)),
    )

    polynomial = from_coefficient_rows(rows, variables=(x, y, z))

    assert coefficient_rows(polynomial) == rows
    assert (
        sp.expand(
            polynomial.to_sympy()
            - (
                sp.Rational(2, 5) * x**2
                - sp.Rational(3, 7) * x * y
                + 11 * y**2
                + sp.Rational(1, 3) * y * z
                - 4 * z**2
            )
        )
        == 0
    )


def test_constant_and_zero_have_one_entry_by_default() -> None:
    constant = HomogeneousPolynomial.from_expr(sp.Rational(-7, 4), variables=(x, y, z))
    zero = HomogeneousPolynomial.from_expr(0, variables=(x, y, z))

    assert coefficient_rows(constant) == ((sp.Rational(-7, 4),),)
    assert coefficient_rows(zero) == ((sp.Integer(0),),)


def test_zero_can_be_displayed_at_a_larger_degree() -> None:
    zero = HomogeneousPolynomial.from_expr(0, variables=(x, y, z))

    assert coefficient_rows(zero, display_degree=3) == (
        (sp.Integer(0),),
        (sp.Integer(0), sp.Integer(0)),
        (sp.Integer(0), sp.Integer(0), sp.Integer(0)),
        (sp.Integer(0), sp.Integer(0), sp.Integer(0), sp.Integer(0)),
    )


def test_larger_all_zero_rows_import_as_canonical_zero() -> None:
    displayed_rows = (
        (sp.Integer(0),),
        (sp.Integer(0), sp.Integer(0)),
        (sp.Integer(0), sp.Integer(0), sp.Integer(0)),
        (sp.Integer(0), sp.Integer(0), sp.Integer(0), sp.Integer(0)),
    )

    polynomial = from_coefficient_rows(displayed_rows, variables=(x, y, z))

    assert polynomial.degree == 0
    assert dict(polynomial.coefficients) == {}
    assert coefficient_rows(polynomial) == ((sp.Integer(0),),)
    assert coefficient_rows(polynomial, display_degree=3) == displayed_rows


@pytest.mark.parametrize("display_degree", [-1, True, 2.0])
def test_coefficient_rows_reject_invalid_display_degrees(
    display_degree: object,
) -> None:
    zero = HomogeneousPolynomial.from_expr(0, variables=(x, y, z))

    with pytest.raises(PolynomialInputError):
        coefficient_rows(zero, display_degree=display_degree)  # type: ignore[arg-type]


@pytest.mark.parametrize("display_degree", [1, 3])
def test_nonzero_polynomial_rejects_a_different_display_degree(
    display_degree: int,
) -> None:
    polynomial = HomogeneousPolynomial.from_expr(x**2 + y**2, variables=(x, y, z))

    with pytest.raises(PolynomialInputError):
        coefficient_rows(polynomial, display_degree=display_degree)


def test_nonzero_polynomial_accepts_its_actual_display_degree() -> None:
    polynomial = HomogeneousPolynomial.from_expr(x**2 + y**2, variables=(x, y, z))

    assert coefficient_rows(polynomial, display_degree=2) == coefficient_rows(
        polynomial
    )


@pytest.mark.parametrize(
    "rows",
    [
        (),
        ((1,), (2,)),
        ((1, 2),),
        ((1,), (2, 3, 4)),
    ],
)
def test_from_coefficient_rows_rejects_malformed_shapes(rows: object) -> None:
    with pytest.raises(PolynomialInputError):
        from_coefficient_rows(rows, variables=(x, y, z))  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "rows",
    [
        ((1.0,),),
        ((True,),),
        ((sp.Float("0.5"),),),
    ],
)
def test_from_coefficient_rows_rejects_inexact_or_boolean_coefficients(
    rows: object,
) -> None:
    with pytest.raises(PolynomialInputError):
        from_coefficient_rows(rows, variables=(x, y, z))  # type: ignore[arg-type]

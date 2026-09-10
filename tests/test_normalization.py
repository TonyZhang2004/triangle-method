"""Regression tests for reversible coefficient and monomial normalization."""

from __future__ import annotations

import pytest
import sympy as sp

from triangle_method import HomogeneousPolynomial, Normalization, factor_content

x, y, z = sp.symbols("x y z")


def assert_restores_exactly(
    normalization: Normalization,
    original: HomogeneousPolynomial,
) -> None:
    """Assert that a normalization rebuilds the same exact polynomial model."""
    restored = normalization.restore()

    assert restored == original
    assert restored.variables == original.variables
    assert sp.expand(restored.to_sympy() - original.to_sympy()) == 0


def test_factor_content_matches_the_worked_rational_example() -> None:
    expression = sp.Rational(2, 3) * x**3 * y - sp.Rational(4, 9) * x**2 * y**2
    polynomial = HomogeneousPolynomial.from_expr(expression, variables=(x, y, z))

    normalization = factor_content(polynomial)

    assert isinstance(normalization, Normalization)
    assert normalization.scalar == sp.Rational(2, 9)
    assert normalization.monomial == (2, 1, 0)
    assert normalization.reduced.variables == (x, y, z)
    assert sp.expand(normalization.reduced.to_sympy() - (3 * x - 2 * y)) == 0
    assert_restores_exactly(normalization, polynomial)


def test_zero_uses_the_identity_normalization() -> None:
    polynomial = HomogeneousPolynomial.from_expr(0, variables=(x, y, z))

    normalization = factor_content(polynomial)

    assert normalization.scalar == 1
    assert normalization.monomial == (0, 0, 0)
    assert normalization.reduced == polynomial
    assert normalization.reduced.degree == 0
    assert_restores_exactly(normalization, polynomial)


@pytest.mark.parametrize(
    ("constant", "expected_scalar", "expected_reduced"),
    [
        (sp.Rational(6, 5), sp.Rational(6, 5), sp.Integer(1)),
        (sp.Rational(-6, 5), sp.Rational(6, 5), sp.Integer(-1)),
    ],
)
def test_positive_and_negative_constants_preserve_their_sign(
    constant: sp.Rational,
    expected_scalar: sp.Rational,
    expected_reduced: sp.Integer,
) -> None:
    polynomial = HomogeneousPolynomial.from_expr(constant, variables=(x, y, z))

    normalization = factor_content(polynomial)

    assert normalization.scalar == expected_scalar
    assert normalization.monomial == (0, 0, 0)
    assert normalization.reduced.to_sympy() == expected_reduced
    assert_restores_exactly(normalization, polynomial)


def test_all_negative_rational_coefficients_keep_their_signs() -> None:
    expression = -sp.Rational(6, 5) * x**4 * y**2 - sp.Rational(9, 10) * x**3 * y**3
    polynomial = HomogeneousPolynomial.from_expr(expression, variables=(x, y, z))

    normalization = factor_content(polynomial)

    assert normalization.scalar == sp.Rational(3, 10)
    assert normalization.monomial == (3, 2, 0)
    assert sp.expand(normalization.reduced.to_sympy() - (-4 * x - 3 * y)) == 0
    assert_restores_exactly(normalization, polynomial)


def test_mixed_rational_coefficients_extract_positive_content() -> None:
    expression = sp.Rational(5, 6) * x * y * z**2 - sp.Rational(35, 18) * x * y**2 * z
    polynomial = HomogeneousPolynomial.from_expr(expression, variables=(x, y, z))

    normalization = factor_content(polynomial)

    assert normalization.scalar == sp.Rational(5, 18)
    assert normalization.monomial == (1, 1, 1)
    assert sp.expand(normalization.reduced.to_sympy() - (3 * z - 7 * y)) == 0
    assert_restores_exactly(normalization, polynomial)


def test_monomial_shift_uses_the_explicit_variable_order() -> None:
    expression = sp.Rational(2, 3) * x**3 * y - sp.Rational(4, 9) * x**2 * y**2
    polynomial = HomogeneousPolynomial.from_expr(expression, variables=(z, y, x))

    normalization = factor_content(polynomial)

    assert normalization.scalar == sp.Rational(2, 9)
    assert normalization.monomial == (0, 1, 2)
    assert normalization.reduced.variables == (z, y, x)
    assert sp.expand(normalization.reduced.to_sympy() - (3 * x - 2 * y)) == 0
    assert_restores_exactly(normalization, polynomial)


def test_factor_content_does_not_change_the_original_polynomial() -> None:
    expression = 12 * x**3 * y + 18 * x**2 * y**2
    polynomial = HomogeneousPolynomial.from_expr(expression, variables=(x, y, z))
    original_coefficients = dict(polynomial.coefficients)

    normalization = factor_content(polynomial)

    assert dict(polynomial.coefficients) == original_coefficients
    assert polynomial.to_sympy() == expression
    assert normalization.scalar == 6
    assert normalization.monomial == (2, 1, 0)
    assert sp.expand(normalization.reduced.to_sympy() - (2 * x + 3 * y)) == 0
    assert_restores_exactly(normalization, polynomial)

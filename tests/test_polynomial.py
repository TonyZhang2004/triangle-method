"""Tests for exact homogeneous-polynomial input and storage."""

from __future__ import annotations

from fractions import Fraction
from typing import Any

import pytest
import sympy as sp

from triangle_method import HomogeneousPolynomial, PolynomialInputError

Exponent = tuple[int, int, int]


def test_approved_examples_are_preserved_exactly(
    ternary_symbols: tuple[sp.Symbol, sp.Symbol, sp.Symbol],
    approved_polynomial_cases: tuple[Any, ...],
) -> None:
    """Ensure every approved example survives construction and SymPy export."""

    for case in approved_polynomial_cases:
        polynomial = HomogeneousPolynomial.from_expr(
            case.expression,
            variables=ternary_symbols,
        )

        assert polynomial.degree == len(case.expected_rows) - 1, case.name
        assert sp.expand(polynomial.to_sympy() - case.expression) == 0, case.name
        assert not polynomial.to_sympy().atoms(sp.Float), case.name


def test_expression_mapping_and_reordered_poly_are_equivalent(
    ternary_symbols: tuple[sp.Symbol, sp.Symbol, sp.Symbol],
    asymmetric_cubic_case: Any,
) -> None:
    """Map Poly generators by symbol and canonicalize all supported input paths."""

    x, y, z = ternary_symbols
    terms: dict[Exponent, int] = {
        (3, 0, 0): 1,
        (2, 1, 0): 2,
        (2, 0, 1): 3,
        (1, 2, 0): 4,
        (1, 1, 1): 5,
        (1, 0, 2): 6,
        (0, 3, 0): 7,
        (0, 2, 1): 8,
        (0, 1, 2): 9,
        (0, 0, 3): 10,
    }
    from_expression = HomogeneousPolynomial.from_expr(
        asymmetric_cubic_case.expression,
        variables=ternary_symbols,
    )
    from_mapping = HomogeneousPolynomial.from_terms(
        terms,
        variables=ternary_symbols,
    )
    from_reordered_poly = HomogeneousPolynomial.from_expr(
        sp.Poly(asymmetric_cubic_case.expression, z, y, x),
        variables=ternary_symbols,
    )

    assert from_expression == from_mapping == from_reordered_poly


def test_poly_may_omit_an_unused_requested_variable(
    ternary_symbols: tuple[sp.Symbol, sp.Symbol, sp.Symbol],
) -> None:
    """Accept a Poly with subset generators without shifting exponent positions."""

    x, y, z = ternary_symbols
    expression = x**2 + 2 * x * z + 3 * z**2
    polynomial = HomogeneousPolynomial.from_expr(
        sp.Poly(expression, z, x),
        variables=ternary_symbols,
    )

    assert polynomial.coefficient((2, 0, 0)) == 1
    assert polynomial.coefficient((1, 0, 1)) == 2
    assert polynomial.coefficient((0, 0, 2)) == 3
    assert polynomial.coefficient((1, 1, 0)) == 0
    assert sp.expand(polynomial.to_sympy() - expression) == 0


def test_exact_supported_coefficients_share_one_representation(
    ternary_symbols: tuple[sp.Symbol, sp.Symbol, sp.Symbol],
) -> None:
    """Convert integer, Fraction, and SymPy Rational values without approximation."""

    x, y, z = ternary_symbols
    polynomial = HomogeneousPolynomial.from_terms(
        {
            (2, 0, 0): Fraction(1, 3),
            (1, 1, 0): sp.Rational(-2, 5),
            (0, 0, 2): 7,
        },
        variables=ternary_symbols,
    )

    assert polynomial.coefficient((2, 0, 0)) == sp.Rational(1, 3)
    assert polynomial.coefficient((1, 1, 0)) == sp.Rational(-2, 5)
    assert polynomial.coefficient((0, 0, 2)) == sp.Rational(7)
    assert (
        sp.expand(
            polynomial.to_sympy()
            - (sp.Rational(1, 3) * x**2 - sp.Rational(2, 5) * x * y + 7 * z**2)
        )
        == 0
    )
    assert not polynomial.to_sympy().atoms(sp.Float)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (5, sp.Integer(5)),
        (Fraction(-3, 7), sp.Rational(-3, 7)),
        (sp.Rational(11, 13), sp.Rational(11, 13)),
    ],
)
def test_exact_scalar_constants_are_supported(
    ternary_symbols: tuple[sp.Symbol, sp.Symbol, sp.Symbol],
    value: object,
    expected: sp.Rational,
) -> None:
    """Treat every supported exact scalar as a degree-zero polynomial."""

    polynomial = HomogeneousPolynomial.from_expr(
        value,
        variables=ternary_symbols,
    )

    assert polynomial.degree == 0
    assert polynomial.coefficients == {(0, 0, 0): expected}
    assert polynomial.to_sympy() == expected


def test_zero_has_canonical_degree_and_empty_sparse_storage(
    ternary_symbols: tuple[sp.Symbol, sp.Symbol, sp.Symbol],
) -> None:
    """Represent zero canonically while still returning exact zero coefficients."""

    from_expression = HomogeneousPolynomial.from_expr(
        0,
        variables=ternary_symbols,
    )
    from_mapping = HomogeneousPolynomial.from_terms(
        {(4, 0, 0): 0, (0, 0, 0): sp.Integer(0)},
        variables=ternary_symbols,
    )

    assert from_expression == from_mapping
    assert from_expression.degree == 0
    assert dict(from_expression.coefficients) == {}
    assert from_expression.coefficient((9, 2, 1)) == 0
    assert from_expression.to_sympy() == 0


def test_zero_terms_do_not_make_a_sparse_polynomial_nonhomogeneous(
    ternary_symbols: tuple[sp.Symbol, sp.Symbol, sp.Symbol],
) -> None:
    """Discard exact zeros only after validating them and infer degree from nonzeros."""

    polynomial = HomogeneousPolynomial.from_terms(
        {(2, 0, 0): 1, (1, 1, 0): -2, (0, 0, 0): 0},
        variables=ternary_symbols,
    )

    assert polynomial.degree == 2
    assert dict(polynomial.coefficients) == {
        (2, 0, 0): sp.Integer(1),
        (1, 1, 0): sp.Integer(-2),
    }


def test_negative_coefficients_and_constants_are_valid_inputs(
    ternary_symbols: tuple[sp.Symbol, sp.Symbol, sp.Symbol],
) -> None:
    """Keep signs intact because construction does not decide nonnegativity."""

    x, y, _ = ternary_symbols
    polynomial = HomogeneousPolynomial.from_expr(
        -(x**2) - 2 * x * y - 3 * y**2,
        variables=ternary_symbols,
    )
    negative_constant = HomogeneousPolynomial.from_expr(
        -7,
        variables=ternary_symbols,
    )

    assert polynomial.coefficient((2, 0, 0)) == -1
    assert polynomial.coefficient((1, 1, 0)) == -2
    assert polynomial.coefficient((0, 2, 0)) == -3
    assert negative_constant.coefficient((0, 0, 0)) == -7


def test_model_owns_terms_and_exposes_a_read_only_mapping(
    ternary_symbols: tuple[sp.Symbol, sp.Symbol, sp.Symbol],
) -> None:
    """Protect stored coefficients from caller mutation and writes through the view."""

    terms: dict[Exponent, int] = {(2, 0, 0): 1, (1, 1, 0): -2}
    polynomial = HomogeneousPolynomial.from_terms(
        terms,
        variables=ternary_symbols,
    )
    terms[(2, 0, 0)] = 99
    terms[(0, 2, 0)] = 4

    assert dict(polynomial.coefficients) == {
        (2, 0, 0): sp.Integer(1),
        (1, 1, 0): sp.Integer(-2),
    }
    with pytest.raises(TypeError):
        polynomial.coefficients[(0, 0, 2)] = sp.Integer(3)  # type: ignore[index]


def test_equality_includes_explicit_variable_order(
    ternary_symbols: tuple[sp.Symbol, sp.Symbol, sp.Symbol],
) -> None:
    """Distinguish models whose identical expressions use different basis orders."""

    x, y, z = ternary_symbols
    standard = HomogeneousPolynomial.from_expr(x, variables=(x, y, z))
    reversed_order = HomogeneousPolynomial.from_expr(x, variables=(z, y, x))

    assert standard.to_sympy() == reversed_order.to_sympy() == x
    assert standard != reversed_order


@pytest.mark.parametrize(
    "exponent",
    [
        (1, 0),
        (1, 0, 0, 0),
        [1, 0, 0],
        (1, -1, 0),
        (1.0, 0, 0),
        (True, 0, 0),
        ("1", 0, 0),
    ],
)
def test_coefficient_lookup_rejects_malformed_exponents(
    ternary_symbols: tuple[sp.Symbol, sp.Symbol, sp.Symbol],
    exponent: object,
) -> None:
    """Reject lookup keys outside nonnegative integer exponent triples."""

    polynomial = HomogeneousPolynomial.from_expr(
        1,
        variables=ternary_symbols,
    )

    with pytest.raises(PolynomialInputError):
        polynomial.coefficient(exponent)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "variables",
    [
        sp.symbols("x y"),
        sp.symbols("x y z w"),
        (sp.Symbol("x"), sp.Symbol("y"), sp.Symbol("x")),
        (sp.Symbol("x"), sp.Symbol("y"), sp.Symbol("z", commutative=False)),
        (sp.Symbol("x"), sp.Symbol("y"), sp.Symbol("z") + 1),
    ],
)
def test_variables_must_be_three_distinct_commutative_symbols(
    variables: tuple[object, ...],
) -> None:
    """Require an explicit valid ternary basis before parsing the expression."""

    with pytest.raises(PolynomialInputError):
        HomogeneousPolynomial.from_expr(1, variables=variables)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "expression",
    [
        True,
        0.5,
        "x**2",
        sp.sqrt(2),
        sp.nan,
        sp.oo,
        -sp.oo,
        sp.zoo,
    ],
)
def test_unsupported_scalar_inputs_are_rejected(
    ternary_symbols: tuple[sp.Symbol, sp.Symbol, sp.Symbol],
    expression: object,
) -> None:
    """Reject approximate, Boolean, non-rational, non-finite, and string scalars."""

    with pytest.raises(PolynomialInputError):
        HomogeneousPolynomial.from_expr(
            expression,
            variables=ternary_symbols,
        )


def test_expression_with_any_visible_float_is_rejected(
    ternary_symbols: tuple[sp.Symbol, sp.Symbol, sp.Symbol],
) -> None:
    """Reject Float atoms before polynomial-domain conversion can rationalize them."""

    x, y, _ = ternary_symbols
    expressions = (
        sp.Float("0.5") * x**2 + y**2,
        sp.Mul(sp.Float(0), x, evaluate=False),
        sp.Poly(sp.Float("1.25") * x**2 + y**2, x, y),
    )

    for expression in expressions:
        with pytest.raises(PolynomialInputError):
            HomogeneousPolynomial.from_expr(
                expression,
                variables=ternary_symbols,
            )


def test_expression_rejects_undeclared_or_symbolic_coefficients(
    ternary_symbols: tuple[sp.Symbol, sp.Symbol, sp.Symbol],
) -> None:
    """Reject symbols outside the declared ternary basis, including parameters."""

    x, y, _ = ternary_symbols
    parameter, fourth_variable = sp.symbols("a w")

    for expression in (parameter * x**2 + y**2, x**2 + fourth_variable**2):
        with pytest.raises(PolynomialInputError):
            HomogeneousPolynomial.from_expr(
                expression,
                variables=ternary_symbols,
            )


def test_nonhomogeneous_expression_and_mapping_are_rejected(
    ternary_symbols: tuple[sp.Symbol, sp.Symbol, sp.Symbol],
) -> None:
    """Require one common total degree across every nonzero term."""

    x, y, _ = ternary_symbols

    with pytest.raises(PolynomialInputError):
        HomogeneousPolynomial.from_expr(
            x**2 + y + 1,
            variables=ternary_symbols,
        )
    with pytest.raises(PolynomialInputError):
        HomogeneousPolynomial.from_terms(
            {(2, 0, 0): 1, (0, 1, 0): -1},
            variables=ternary_symbols,
        )


def test_visible_variable_denominator_is_rejected_before_cancellation(
    ternary_symbols: tuple[sp.Symbol, sp.Symbol, sp.Symbol],
) -> None:
    """Reject the supplied rational-function form even if algebra can cancel it."""

    x, y, _ = ternary_symbols
    uncancelled = sp.Mul(
        x**2 - y**2,
        sp.Pow(x - y, -1, evaluate=False),
        evaluate=False,
    )

    with pytest.raises(PolynomialInputError):
        HomogeneousPolynomial.from_expr(
            uncancelled,
            variables=ternary_symbols,
        )

    cancelled = sp.cancel((x**2 - y**2) / (x - y))
    polynomial = HomogeneousPolynomial.from_expr(
        cancelled,
        variables=ternary_symbols,
    )
    assert sp.expand(polynomial.to_sympy() - (x + y)) == 0


@pytest.mark.parametrize(
    "terms",
    [
        {(2, 0): 1},
        {(2, 0, 0, 0): 1},
        {(1, -1, 0): 1},
        {(1.0, 1, 0): 1},
        {(True, 1, 0): 1},
        {("2", 0, 0): 1},
    ],
)
def test_mapping_rejects_malformed_exponents(
    ternary_symbols: tuple[sp.Symbol, sp.Symbol, sp.Symbol],
    terms: dict[object, object],
) -> None:
    """Validate each mapping key as a nonnegative integer exponent triple."""

    with pytest.raises(PolynomialInputError):
        HomogeneousPolynomial.from_terms(
            terms,  # type: ignore[arg-type]
            variables=ternary_symbols,
        )


@pytest.mark.parametrize(
    "coefficient",
    [
        True,
        0.5,
        "1/2",
        sp.sqrt(2),
        sp.nan,
        sp.oo,
        -sp.oo,
        sp.zoo,
        sp.Symbol("a"),
    ],
)
def test_mapping_rejects_unsupported_coefficients_before_zero_removal(
    ternary_symbols: tuple[sp.Symbol, sp.Symbol, sp.Symbol],
    coefficient: object,
) -> None:
    """Validate all mapping values exactly, including unsupported zero-like values."""

    with pytest.raises(PolynomialInputError):
        HomogeneousPolynomial.from_terms(
            {(2, 0, 0): coefficient},
            variables=ternary_symbols,
        )


def test_mapping_rejects_a_float_even_when_its_value_is_zero(
    ternary_symbols: tuple[sp.Symbol, sp.Symbol, sp.Symbol],
) -> None:
    """Do not discard a zero-valued Float before enforcing the input contract."""

    with pytest.raises(PolynomialInputError):
        HomogeneousPolynomial.from_terms(
            {(2, 0, 0): 1, (0, 0, 0): 0.0},
            variables=ternary_symbols,
        )

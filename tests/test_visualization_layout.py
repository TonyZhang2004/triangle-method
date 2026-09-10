"""Tests for exact labels and equilateral coefficient-triangle layout."""

from __future__ import annotations

import math
from typing import Any

import pytest
import sympy as sp

from triangle_method import (
    CoefficientTriangle,
    HomogeneousPolynomial,
    PolynomialInputError,
    coefficient_triangle,
)
from triangle_method.visualization.layout import (
    build_triangle_layout,
    format_coefficient,
)


def test_all_approved_examples_build_the_expected_figures(
    ternary_symbols: tuple[sp.Symbol, sp.Symbol, sp.Symbol],
    approved_polynomial_cases: tuple[Any, ...],
) -> None:
    """Build every approved example from its polynomial rather than stored markup."""

    for case in approved_polynomial_cases:
        polynomial = HomogeneousPolynomial.from_expr(
            case.expression,
            variables=ternary_symbols,
        )

        figure = coefficient_triangle(polynomial)
        layout = build_triangle_layout(figure.rows)
        positioned_coefficients = {
            (mark.row, mark.column): mark.coefficient for mark in layout.marks
        }
        expected_coefficients = {
            (row, column): coefficient
            for row, values in enumerate(case.expected_rows)
            for column, coefficient in enumerate(values)
        }

        assert isinstance(figure, CoefficientTriangle), case.name
        assert figure.degree == len(case.expected_rows) - 1, case.name
        assert figure.rows == case.expected_rows, case.name
        assert positioned_coefficients == expected_coefficients, case.name


def test_asymmetric_figure_preserves_variable_order_and_left_right_orientation(
    ternary_symbols: tuple[sp.Symbol, sp.Symbol, sp.Symbol],
    asymmetric_cubic_case: Any,
) -> None:
    """Detect row reversal by rendering one asymmetric cubic in two variable orders."""

    standard = HomogeneousPolynomial.from_expr(
        asymmetric_cubic_case.expression,
        variables=ternary_symbols,
    )
    permuted = HomogeneousPolynomial.from_expr(
        asymmetric_cubic_case.expression,
        variables=asymmetric_cubic_case.permuted_variables,
    )

    assert coefficient_triangle(standard).rows == asymmetric_cubic_case.expected_rows
    assert (
        coefficient_triangle(permuted).rows
        == asymmetric_cubic_case.expected_permuted_rows
    )


def test_layout_contains_each_row_and_column_exactly_once(
    ternary_symbols: tuple[sp.Symbol, sp.Symbol, sp.Symbol],
    asymmetric_cubic_case: Any,
) -> None:
    """Keep every exact coefficient attached to its canonical row and column."""

    polynomial = HomogeneousPolynomial.from_expr(
        asymmetric_cubic_case.expression,
        variables=ternary_symbols,
    )
    figure = coefficient_triangle(polynomial)
    layout = build_triangle_layout(figure.rows)
    marks_by_position = {(mark.row, mark.column): mark for mark in layout.marks}
    expected_positions = {
        (row, column)
        for row, values in enumerate(figure.rows)
        for column, _ in enumerate(values)
    }

    assert set(marks_by_position) == expected_positions
    assert len(layout.marks) == len(expected_positions)
    for (row, column), mark in marks_by_position.items():
        coefficient = figure.rows[row][column]
        assert mark.coefficient == coefficient
        assert mark.text == format_coefficient(coefficient)


def test_layout_uses_centered_equilateral_spacing() -> None:
    """Check centered rows and the altitude ratio of an equilateral lattice."""

    rows = (
        (sp.Integer(1),),
        (sp.Integer(2), sp.Integer(3)),
        (sp.Integer(4), sp.Integer(5), sp.Integer(6)),
        (sp.Integer(7), sp.Integer(8), sp.Integer(9), sp.Integer(10)),
    )
    layout = build_triangle_layout(rows)
    apex = next(mark for mark in layout.marks if mark.row == 0)

    assert layout.width > 0
    assert layout.height > 0
    assert layout.horizontal_step > 0

    for row_index in range(len(rows)):
        row_marks = [mark for mark in layout.marks if mark.row == row_index]
        assert sum(mark.x for mark in row_marks) / len(row_marks) == pytest.approx(
            apex.x,
            abs=1e-9,
        )
        assert len({mark.y for mark in row_marks}) == 1
        for left, right in zip(row_marks, row_marks[1:], strict=False):
            assert right.x - left.x == pytest.approx(
                layout.horizontal_step,
                abs=1e-9,
            )

    row_heights = [
        next(mark.y for mark in layout.marks if mark.row == row_index)
        for row_index in range(len(rows))
    ]
    expected_vertical_step = math.sqrt(3) / 2 * layout.horizontal_step
    for upper, lower in zip(row_heights, row_heights[1:], strict=False):
        assert lower - upper == pytest.approx(expected_vertical_step, abs=1e-9)


@pytest.mark.parametrize(
    ("coefficient", "expected"),
    [
        (sp.Integer(0), "0"),
        (sp.Integer(42), "42"),
        (sp.Integer(-42), "−42"),
        (sp.Rational(3, 7), "3/7"),
        (sp.Rational(-3, 7), "−3/7"),
        (sp.Integer(12345678901234567890), "12345678901234567890"),
    ],
)
def test_coefficient_labels_preserve_exact_values(
    coefficient: sp.Rational,
    expected: str,
) -> None:
    """Format exact coefficients without decimals or loss of their signs."""

    assert format_coefficient(coefficient) == expected


def test_long_fraction_expands_the_global_equilateral_step() -> None:
    """Reserve more horizontal space for long labels without distorting the lattice."""

    short_rows = ((sp.Integer(1),), (sp.Integer(1), sp.Integer(1)))
    long_rows = (
        (sp.Rational(1234567890123456789, 1000000000000000003),),
        (sp.Integer(1), sp.Integer(1)),
    )

    short_layout = build_triangle_layout(short_rows)
    long_layout = build_triangle_layout(long_rows)

    assert long_layout.horizontal_step > short_layout.horizontal_step
    assert long_layout.width > short_layout.width


def test_constant_and_default_zero_have_positive_degree_zero_canvases(
    ternary_symbols: tuple[sp.Symbol, sp.Symbol, sp.Symbol],
) -> None:
    """Give constants and canonical zero a visible one-mark canvas."""

    x, y, z = ternary_symbols
    constant = HomogeneousPolynomial.from_expr(sp.Rational(-7, 4), variables=(x, y, z))
    zero = HomogeneousPolynomial.from_expr(0, variables=(x, y, z))

    for figure, expected_text in (
        (coefficient_triangle(constant), "−7/4"),
        (coefficient_triangle(zero), "0"),
    ):
        layout = build_triangle_layout(figure.rows)
        assert figure.degree == 0
        assert layout.width > 0
        assert layout.height > 0
        assert len(layout.marks) == 1
        assert layout.marks[0].text == expected_text


def test_zero_can_display_every_position_at_a_requested_degree(
    ternary_symbols: tuple[sp.Symbol, sp.Symbol, sp.Symbol],
) -> None:
    """Render a chosen zero triangle with all of its explicit zero positions."""

    zero = HomogeneousPolynomial.from_expr(0, variables=ternary_symbols)

    figure = coefficient_triangle(zero, display_degree=4)
    layout = build_triangle_layout(figure.rows)

    assert figure.degree == 4
    assert tuple(len(row) for row in figure.rows) == (1, 2, 3, 4, 5)
    assert len(layout.marks) == 15
    assert all(mark.coefficient == 0 and mark.text == "0" for mark in layout.marks)
    assert layout.width > 0
    assert layout.height > 0


def test_rendering_entry_point_reuses_polynomial_validation(
    ternary_symbols: tuple[sp.Symbol, sp.Symbol, sp.Symbol],
) -> None:
    """Reject a wrong model type and a degree override invalid for a nonzero input."""

    x, y, z = ternary_symbols
    quadratic = HomogeneousPolynomial.from_expr(x**2 + y**2 + z**2, variables=(x, y, z))

    with pytest.raises(PolynomialInputError):
        coefficient_triangle(quadratic, display_degree=3)
    with pytest.raises(PolynomialInputError):
        coefficient_triangle(x**2)  # type: ignore[arg-type]


def test_coefficient_triangle_is_immutable(
    ternary_symbols: tuple[sp.Symbol, sp.Symbol, sp.Symbol],
) -> None:
    """Prevent callers from replacing the exact rows after a layout is constructed."""

    zero = HomogeneousPolynomial.from_expr(0, variables=ternary_symbols)
    figure = coefficient_triangle(zero)

    with pytest.raises((AttributeError, TypeError)):
        figure.rows = ((sp.Integer(9),),)  # type: ignore[misc]

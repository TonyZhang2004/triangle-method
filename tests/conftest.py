"""Shared exact-polynomial fixtures for the Triangle Method test suite."""

from __future__ import annotations

from dataclasses import dataclass

import pytest
import sympy as sp

CoefficientRows = tuple[tuple[int, ...], ...]


@dataclass(frozen=True)
class PolynomialCase:
    """Pair an expanded ternary polynomial with its independently written rows."""

    name: str
    expression: sp.Expr
    expected_rows: CoefficientRows


@dataclass(frozen=True)
class AsymmetricPolynomialCase:
    """Store an asymmetric cubic and expected rows under two variable orders."""

    expression: sp.Expr
    expected_rows: CoefficientRows
    permuted_variables: tuple[sp.Symbol, sp.Symbol, sp.Symbol]
    expected_permuted_rows: CoefficientRows


@pytest.fixture(scope="session")
def ternary_symbols() -> tuple[sp.Symbol, sp.Symbol, sp.Symbol]:
    """Return the ordered symbols used throughout the mathematical fixtures."""

    return sp.symbols("x y z")


@pytest.fixture(scope="session")
def approved_polynomial_cases(
    ternary_symbols: tuple[sp.Symbol, sp.Symbol, sp.Symbol],
) -> tuple[PolynomialCase, ...]:
    """Return the seven approved examples with hand-written coefficient rows."""

    x, y, z = ternary_symbols

    quadratic_squares = x**2 + y**2 + z**2 - x * y - x * z - y * z
    cubic_schur = (
        x**3
        + y**3
        + z**3
        + 3 * x * y * z
        - x**2 * y
        - x**2 * z
        - x * y**2
        - x * z**2
        - y**2 * z
        - y * z**2
    )
    quintic_schur = (
        x**5
        + y**5
        + z**5
        - x**4 * y
        - x**4 * z
        - x * y**4
        - y**4 * z
        - x * z**4
        - y * z**4
        + x**3 * y * z
        + x * y**3 * z
        + x * y * z**3
    )
    cubic_weighted_squares = (
        x**2 * y + x * y**2 + y**2 * z + y * z**2 + z**2 * x + z * x**2 - 6 * x * y * z
    )
    quartic_squares = x**4 + y**4 + z**4 - x**2 * y**2 - y**2 * z**2 - z**2 * x**2
    quartic_schur_lift = (
        x**4
        + y**4
        + z**4
        + x**2 * y * z
        + x * y**2 * z
        + x * y * z**2
        - 2 * x**2 * y**2
        - 2 * y**2 * z**2
        - 2 * z**2 * x**2
    )
    quintic_schur_plus_squares = (
        x**5
        + y**5
        + z**5
        - x**4 * y
        - x**4 * z
        - x * y**4
        - y**4 * z
        - x * z**4
        - y * z**4
        + 2 * x**3 * y * z
        + 2 * x * y**3 * z
        + 2 * x * y * z**3
        - x**2 * y**2 * z
        - x**2 * y * z**2
        - x * y**2 * z**2
    )

    return (
        PolynomialCase(
            name="quadratic_squares",
            expression=quadratic_squares,
            expected_rows=((1,), (-1, -1), (1, -1, 1)),
        ),
        PolynomialCase(
            name="cubic_schur",
            expression=cubic_schur,
            expected_rows=(
                (1,),
                (-1, -1),
                (-1, 3, -1),
                (1, -1, -1, 1),
            ),
        ),
        PolynomialCase(
            name="quintic_schur",
            expression=quintic_schur,
            expected_rows=(
                (1,),
                (-1, -1),
                (0, 1, 0),
                (0, 0, 0, 0),
                (-1, 1, 0, 1, -1),
                (1, -1, 0, 0, -1, 1),
            ),
        ),
        PolynomialCase(
            name="cubic_weighted_squares",
            expression=cubic_weighted_squares,
            expected_rows=(
                (0,),
                (1, 1),
                (1, -6, 1),
                (0, 1, 1, 0),
            ),
        ),
        PolynomialCase(
            name="quartic_squares",
            expression=quartic_squares,
            expected_rows=(
                (1,),
                (0, 0),
                (-1, 0, -1),
                (0, 0, 0, 0),
                (1, 0, -1, 0, 1),
            ),
        ),
        PolynomialCase(
            name="quartic_schur_lift",
            expression=quartic_schur_lift,
            expected_rows=(
                (1,),
                (0, 0),
                (-2, 1, -2),
                (0, 1, 1, 0),
                (1, 0, -2, 0, 1),
            ),
        ),
        PolynomialCase(
            name="quintic_schur_plus_squares",
            expression=quintic_schur_plus_squares,
            expected_rows=(
                (1,),
                (-1, -1),
                (0, 2, 0),
                (0, -1, -1, 0),
                (-1, 2, -1, 2, -1),
                (1, -1, 0, 0, -1, 1),
            ),
        ),
    )


@pytest.fixture(scope="session")
def asymmetric_cubic_case(
    ternary_symbols: tuple[sp.Symbol, sp.Symbol, sp.Symbol],
) -> AsymmetricPolynomialCase:
    """Return the cubic that detects reversed or positional variable indexing."""

    x, y, z = ternary_symbols
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

    return AsymmetricPolynomialCase(
        expression=expression,
        expected_rows=((1,), (2, 3), (4, 5, 6), (7, 8, 9, 10)),
        permuted_variables=(z, y, x),
        expected_permuted_rows=(
            (10,),
            (9, 6),
            (8, 5, 3),
            (7, 4, 2, 1),
        ),
    )

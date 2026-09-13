"""Canonical coefficient indexing for ternary homogeneous polynomials."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from typing import TypeAlias

import sympy as sp

from .errors import PolynomialInputError
from .polynomial import ExactCoefficient, Exponent, HomogeneousPolynomial

CoefficientRows: TypeAlias = tuple[tuple[ExactCoefficient, ...], ...]


def _validate_degree(degree: object, *, context: str = "degree") -> int:
    """Validate a nonnegative integer degree and return it unchanged."""
    if isinstance(degree, bool) or not isinstance(degree, int):
        raise PolynomialInputError(f"{context} must be a nonnegative integer")
    if degree < 0:
        raise PolynomialInputError(f"{context} must be a nonnegative integer")
    return degree


def _triangle_exponent_rows(degree: int) -> Iterator[tuple[Exponent, ...]]:
    """Yield canonical degree-n exponent rows without materializing the full triangle."""
    validated_degree = _validate_degree(degree)
    for row in range(validated_degree + 1):
        yield tuple(
            (validated_degree - row, row - column, column) for column in range(row + 1)
        )


def _triangle_index(exponent: Exponent) -> int:
    """Return the flattened canonical triangle index of a validated exponent."""
    row = exponent[1] + exponent[2]
    return row * (row + 1) // 2 + exponent[2]


def triangle_exponents(degree: int) -> tuple[tuple[Exponent, ...], ...]:
    """Return all degree-n exponent triples in the canonical triangular rows."""
    return tuple(_triangle_exponent_rows(degree))


def coefficient_rows(
    polynomial: HomogeneousPolynomial,
    *,
    display_degree: int | None = None,
) -> CoefficientRows:
    """Return exact coefficient rows, including zeros, at the requested degree."""
    if not isinstance(polynomial, HomogeneousPolynomial):
        raise PolynomialInputError("polynomial must be a HomogeneousPolynomial")

    degree = polynomial.degree
    if display_degree is not None:
        degree = _validate_degree(display_degree, context="display_degree")
        if not polynomial.is_zero and degree != polynomial.degree:
            raise PolynomialInputError(
                "display_degree must equal the degree of a nonzero polynomial"
            )

    return tuple(
        tuple(polynomial.coefficient(exponent) for exponent in exponent_row)
        for exponent_row in _triangle_exponent_rows(degree)
    )


def from_coefficient_rows(
    rows: Sequence[Sequence[object]],
    *,
    variables: Sequence[sp.Symbol],
) -> HomogeneousPolynomial:
    """Validate triangular coefficient rows and return their exact polynomial."""
    if isinstance(rows, (str, bytes)):
        raise PolynomialInputError("coefficient rows must be a nonempty sequence")
    try:
        materialized_rows = tuple(rows)
    except TypeError as error:
        raise PolynomialInputError(
            "coefficient rows must be a nonempty sequence"
        ) from error
    if not materialized_rows:
        raise PolynomialInputError("coefficient rows cannot be empty")

    degree = len(materialized_rows) - 1
    exponents = triangle_exponents(degree)
    terms: dict[Exponent, object] = {}

    for row_index, (row, exponent_row) in enumerate(
        zip(materialized_rows, exponents, strict=True)
    ):
        if isinstance(row, (str, bytes)):
            raise PolynomialInputError(
                f"coefficient row {row_index} must be a sequence of coefficients"
            )
        try:
            values = tuple(row)
        except TypeError as error:
            raise PolynomialInputError(
                f"coefficient row {row_index} must be a sequence of coefficients"
            ) from error
        expected_length = row_index + 1
        if len(values) != expected_length:
            raise PolynomialInputError(
                f"coefficient row {row_index} must contain {expected_length} "
                f"entries; received {len(values)}"
            )
        terms.update(zip(exponent_row, values, strict=True))

    return HomogeneousPolynomial.from_terms(terms, variables=variables)

"""Reversible content and common-monomial normalization."""

from __future__ import annotations

from dataclasses import dataclass
from math import gcd, lcm

import sympy as sp

from .errors import PolynomialInputError
from .polynomial import Exponent, HomogeneousPolynomial, _validate_exponent


@dataclass(frozen=True, slots=True)
class Normalization:
    """Record positive scalar and monomial factors with a reduced polynomial."""

    scalar: sp.Rational
    monomial: Exponent
    reduced: HomogeneousPolynomial

    def __post_init__(self) -> None:
        """Validate that the stored factors form a usable exact normalization."""
        if not isinstance(self.scalar, sp.Rational) or self.scalar <= 0:
            raise PolynomialInputError(
                "normalization scalar must be a positive rational"
            )
        _validate_exponent(self.monomial, context="normalization monomial")
        if not isinstance(self.reduced, HomogeneousPolynomial):
            raise PolynomialInputError(
                "normalization reduced value must be a HomogeneousPolynomial"
            )

    def restore(self) -> HomogeneousPolynomial:
        """Recombine the exact factors and return the original polynomial model."""
        restored_terms = {
            tuple(
                power + shift
                for power, shift in zip(exponent, self.monomial, strict=True)
            ): (self.scalar * coefficient)
            for exponent, coefficient in self.reduced.coefficients.items()
        }
        return HomogeneousPolynomial.from_terms(
            restored_terms,
            variables=self.reduced.variables,
        )


def _rational_content(coefficients: tuple[sp.Rational, ...]) -> sp.Rational:
    """Return the positive gcd content of a nonempty rational coefficient tuple."""
    numerator_gcd = 0
    denominator_lcm = 1
    for coefficient in coefficients:
        numerator_gcd = gcd(numerator_gcd, abs(int(coefficient.p)))
        denominator_lcm = lcm(denominator_lcm, int(coefficient.q))
    return sp.Rational(numerator_gcd, denominator_lcm)


def factor_content(polynomial: HomogeneousPolynomial) -> Normalization:
    """Extract positive rational content and a common monomial for exact recovery."""
    if not isinstance(polynomial, HomogeneousPolynomial):
        raise PolynomialInputError("polynomial must be a HomogeneousPolynomial")
    if polynomial.is_zero:
        return Normalization(sp.S.One, (0, 0, 0), polynomial)

    terms = tuple(polynomial.coefficients.items())
    common_monomial = tuple(
        min(exponent[coordinate] for exponent, _ in terms) for coordinate in range(3)
    )
    scalar = _rational_content(tuple(coefficient for _, coefficient in terms))
    reduced_terms = {
        tuple(
            power - common_monomial[coordinate]
            for coordinate, power in enumerate(exponent)
        ): coefficient / scalar
        for exponent, coefficient in terms
    }
    reduced = HomogeneousPolynomial.from_terms(
        reduced_terms,
        variables=polynomial.variables,
    )
    return Normalization(scalar, common_monomial, reduced)

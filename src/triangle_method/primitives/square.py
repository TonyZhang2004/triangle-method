"""Monomial multiples of exact homogeneous polynomial squares."""

from __future__ import annotations

from dataclasses import dataclass, field

import sympy as sp

from ..polynomial import Exponent, HomogeneousPolynomial, Variables
from ._validation import (
    copy_nonzero_factor,
    monomial_expression,
    validate_primitive_exponent,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class SquareComponent:
    """Represent a nonnegative monomial times a nonzero homogeneous square."""

    factor: HomogeneousPolynomial
    multiplier: Exponent = (0, 0, 0)
    variables: Variables = field(init=False)
    degree: int = field(init=False)

    def __init__(
        self,
        *,
        factor: HomogeneousPolynomial,
        multiplier: Exponent = (0, 0, 0),
    ) -> None:
        """Validate and copy a homogeneous factor and monomial multiplier."""
        exact_factor = copy_nonzero_factor(factor)
        exact_multiplier = validate_primitive_exponent(
            multiplier,
            context="multiplier",
        )
        object.__setattr__(self, "factor", exact_factor)
        object.__setattr__(self, "multiplier", exact_multiplier)
        object.__setattr__(self, "variables", exact_factor.variables)
        object.__setattr__(
            self,
            "degree",
            2 * exact_factor.degree + sum(exact_multiplier),
        )

    def expand(self) -> HomogeneousPolynomial:
        """Expand the monomial-weighted square into an exact homogeneous polynomial."""
        multiplier = monomial_expression(self.multiplier, self.variables)
        expression = multiplier * self.factor.to_sympy() ** 2
        return HomogeneousPolynomial.from_expr(
            sp.expand(expression),
            variables=self.variables,
        )

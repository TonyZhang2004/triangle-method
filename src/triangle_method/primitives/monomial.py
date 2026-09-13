"""Coefficient-one monomial primitives on the nonnegative orthant."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

import sympy as sp

from ..polynomial import Exponent, HomogeneousPolynomial, Variables
from ._validation import validate_primitive_exponent, validate_primitive_variables


@dataclass(frozen=True, slots=True, kw_only=True)
class MonomialComponent:
    """Represent a coefficient-one monomial that is nonnegative on the domain."""

    exponent: Exponent
    variables: Variables
    degree: int = field(init=False)

    def __init__(
        self,
        *,
        exponent: Exponent,
        variables: Sequence[sp.Symbol],
    ) -> None:
        """Validate and copy one exponent and its three ordered variables."""
        exact_exponent = validate_primitive_exponent(exponent, context="exponent")
        ordered_variables = validate_primitive_variables(variables)
        object.__setattr__(self, "exponent", exact_exponent)
        object.__setattr__(self, "variables", ordered_variables)
        object.__setattr__(self, "degree", sum(exact_exponent))

    def expand(self) -> HomogeneousPolynomial:
        """Return the exact coefficient-one monomial as a homogeneous polynomial."""
        return HomogeneousPolynomial.from_terms(
            {self.exponent: 1},
            variables=self.variables,
        )

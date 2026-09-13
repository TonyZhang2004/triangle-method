"""Schur primitives under equal-degree nonnegative monomial substitutions."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import TypeAlias

import sympy as sp

from ..errors import PrimitiveInputError
from ..polynomial import Exponent, HomogeneousPolynomial, Variables
from ._validation import (
    monomial_expression,
    validate_primitive_exponent,
    validate_primitive_variables,
)

SchurArguments: TypeAlias = tuple[Exponent, Exponent, Exponent]


def _validate_schur_degree(schur_degree: object) -> int:
    """Require an integer Schur degree at least three and reject booleans."""
    if isinstance(schur_degree, bool) or not isinstance(schur_degree, int):
        raise PrimitiveInputError("schur_degree must be an integer at least 3")
    if schur_degree < 3:
        raise PrimitiveInputError("schur_degree must be an integer at least 3")
    return schur_degree


def _validate_arguments(arguments: Sequence[Exponent]) -> SchurArguments:
    """Copy three monomial exponents and require one common total degree."""
    if isinstance(arguments, (str, bytes)):
        raise PrimitiveInputError("arguments must contain three exponent triples")
    try:
        supplied_arguments = tuple(arguments)
    except TypeError as error:
        raise PrimitiveInputError(
            "arguments must contain three exponent triples"
        ) from error
    if len(supplied_arguments) != 3:
        raise PrimitiveInputError("arguments must contain three exponent triples")

    exact_arguments = tuple(
        validate_primitive_exponent(
            argument,
            context=f"argument {index}",
        )
        for index, argument in enumerate(supplied_arguments)
    )
    argument_degrees = {sum(argument) for argument in exact_arguments}
    if len(argument_degrees) != 1:
        raise PrimitiveInputError("Schur arguments must have equal total degree")
    return exact_arguments  # type: ignore[return-value]


@dataclass(frozen=True, slots=True, kw_only=True)
class SchurComponent:
    """Represent Schur's inequality after equal-degree monomial substitution."""

    schur_degree: int
    arguments: SchurArguments
    variables: Variables
    multiplier: Exponent = (0, 0, 0)
    degree: int = field(init=False)

    def __init__(
        self,
        *,
        schur_degree: int,
        arguments: Sequence[Exponent],
        variables: Sequence[sp.Symbol],
        multiplier: Exponent = (0, 0, 0),
    ) -> None:
        """Validate Schur degree, monomial arguments, variables, and multiplier."""
        exact_schur_degree = _validate_schur_degree(schur_degree)
        exact_arguments = _validate_arguments(arguments)
        ordered_variables = validate_primitive_variables(variables)
        exact_multiplier = validate_primitive_exponent(
            multiplier,
            context="multiplier",
        )
        argument_degree = sum(exact_arguments[0])

        object.__setattr__(self, "schur_degree", exact_schur_degree)
        object.__setattr__(self, "arguments", exact_arguments)
        object.__setattr__(self, "variables", ordered_variables)
        object.__setattr__(self, "multiplier", exact_multiplier)
        object.__setattr__(
            self,
            "degree",
            exact_schur_degree * argument_degree + sum(exact_multiplier),
        )

    def expand(self) -> HomogeneousPolynomial:
        """Expand the substituted Schur cyclic sum as an exact homogeneous polynomial."""
        first, second, third = (
            monomial_expression(argument, self.variables) for argument in self.arguments
        )
        degree_offset = self.schur_degree - 2
        schur_expression = (
            first**degree_offset * (first - second) * (first - third)
            + second**degree_offset * (second - third) * (second - first)
            + third**degree_offset * (third - first) * (third - second)
        )
        multiplier = monomial_expression(self.multiplier, self.variables)
        return HomogeneousPolynomial.from_expr(
            sp.expand(multiplier * schur_expression),
            variables=self.variables,
        )

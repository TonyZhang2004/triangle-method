"""Shared validation and monomial helpers for primitive components."""

from __future__ import annotations

from collections.abc import Sequence

import sympy as sp

from ..errors import PolynomialInputError, PrimitiveInputError
from ..polynomial import (
    Exponent,
    HomogeneousPolynomial,
    Variables,
    _validate_exponent,
    _validate_variables,
)


def validate_primitive_exponent(value: object, *, context: str) -> Exponent:
    """Validate one primitive exponent with the polynomial model's exact rules."""
    try:
        return _validate_exponent(value, context=context)
    except PolynomialInputError as error:
        raise PrimitiveInputError(str(error)) from error


def validate_primitive_variables(variables: Sequence[sp.Symbol]) -> Variables:
    """Validate and copy three ordered variables using the polynomial model rules."""
    try:
        return _validate_variables(variables)
    except PolynomialInputError as error:
        raise PrimitiveInputError(str(error)) from error


def copy_nonzero_factor(factor: object) -> HomogeneousPolynomial:
    """Validate and copy a nonzero exact homogeneous polynomial square factor."""
    if not isinstance(factor, HomogeneousPolynomial):
        raise PrimitiveInputError("factor must be a HomogeneousPolynomial")
    if factor.is_zero:
        raise PrimitiveInputError("square factor must be nonzero")

    try:
        return HomogeneousPolynomial.from_terms(
            factor.coefficients,
            variables=factor.variables,
        )
    except PolynomialInputError as error:
        raise PrimitiveInputError(f"invalid square factor: {error}") from error


def monomial_expression(exponent: Exponent, variables: Variables) -> sp.Expr:
    """Return the coefficient-one monomial for an exponent and ordered variables."""
    expression = sp.S.One
    for variable, power in zip(variables, exponent, strict=True):
        expression *= variable**power
    return expression

"""Exact immutable models for ternary homogeneous polynomials."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from types import MappingProxyType
from typing import TypeAlias

import sympy as sp
from sympy.polys.polyerrors import CoercionFailed, PolynomialError

from .errors import PolynomialInputError

Exponent: TypeAlias = tuple[int, int, int]
Variables: TypeAlias = tuple[sp.Symbol, sp.Symbol, sp.Symbol]
ExactCoefficient: TypeAlias = sp.Rational
ExactCoefficientInput: TypeAlias = int | Fraction | sp.Rational


def _validate_variables(variables: Sequence[sp.Symbol]) -> Variables:
    """Validate an explicitly ordered sequence and return three distinct symbols."""
    if isinstance(variables, (str, bytes)):
        raise PolynomialInputError("variables must be three SymPy symbols")

    try:
        ordered = tuple(variables)
    except TypeError as error:
        raise PolynomialInputError(
            "variables must be an iterable of three SymPy symbols"
        ) from error

    if len(ordered) != 3:
        raise PolynomialInputError(
            f"variables must contain exactly three symbols; received {len(ordered)}"
        )
    if any(not isinstance(symbol, sp.Symbol) for symbol in ordered):
        raise PolynomialInputError("variables must contain only SymPy Symbol objects")
    if any(symbol.is_commutative is not True for symbol in ordered):
        raise PolynomialInputError("variables must be commutative SymPy symbols")
    if len(set(ordered)) != 3:
        raise PolynomialInputError("variables must be three distinct symbols")

    return ordered  # type: ignore[return-value]


def _validate_exponent(exponent: object, *, context: str = "exponent") -> Exponent:
    """Validate one exponent key and return a triple of nonnegative integers."""
    if not isinstance(exponent, tuple) or len(exponent) != 3:
        raise PolynomialInputError(
            f"{context} must be a tuple of three nonnegative integers"
        )
    if any(isinstance(value, bool) or not isinstance(value, int) for value in exponent):
        raise PolynomialInputError(
            f"{context} must be a tuple of three nonnegative integers"
        )
    if any(value < 0 for value in exponent):
        raise PolynomialInputError(f"{context} cannot contain negative values")
    return exponent


def _coerce_exact_rational(
    value: object, *, context: str = "coefficient"
) -> ExactCoefficient:
    """Convert a supported exact coefficient to SymPy Rational or reject it."""
    if isinstance(value, bool):
        raise PolynomialInputError(f"{context} cannot be a boolean")
    if isinstance(value, (float, sp.Float)):
        raise PolynomialInputError(
            f"{context} must be exact; use sympy.Rational or fractions.Fraction "
            "instead of a float"
        )
    if isinstance(value, Fraction):
        return sp.Rational(value.numerator, value.denominator)
    if isinstance(value, int):
        return sp.Integer(value)
    if isinstance(value, sp.Rational):
        return value
    raise PolynomialInputError(
        f"{context} must be an integer or exact rational number; received "
        f"{type(value).__name__}"
    )


def _expression_from_input(expression: object) -> sp.Expr:
    """Convert a supported expression, Poly, or scalar to a SymPy expression."""
    if isinstance(expression, bool):
        raise PolynomialInputError("a polynomial expression cannot be a boolean")
    if isinstance(expression, float):
        raise PolynomialInputError(
            "polynomial coefficients must be exact; use sympy.Rational or "
            "fractions.Fraction instead of a float"
        )
    if isinstance(expression, sp.Poly):
        return expression.as_expr()
    if isinstance(expression, Fraction):
        return sp.Rational(expression.numerator, expression.denominator)
    if isinstance(expression, int):
        return sp.Integer(expression)
    if isinstance(expression, sp.Expr):
        return expression
    raise PolynomialInputError(
        "expected a SymPy expression, SymPy Poly, integer, Fraction, or SymPy Rational"
    )


def _terms_from_expression(
    expression: sp.Expr, variables: Variables
) -> dict[Exponent, object]:
    """Extract exponent terms from a polynomial expression in the ordered variables."""
    if expression.atoms(sp.Float):
        raise PolynomialInputError(
            "polynomial coefficients must be exact; replace floating values with "
            "sympy.Rational"
        )
    nonfinite_values = (
        sp.S.NaN,
        sp.S.Infinity,
        sp.S.NegativeInfinity,
        sp.S.ComplexInfinity,
    )
    if expression.has(*nonfinite_values):
        raise PolynomialInputError("polynomial coefficients must be finite")

    undeclared = expression.free_symbols.difference(variables)
    if undeclared:
        names = ", ".join(sorted(str(symbol) for symbol in undeclared))
        raise PolynomialInputError(f"expression contains undeclared symbols: {names}")

    _, denominator = expression.as_numer_denom()
    denominator_variables = denominator.free_symbols.intersection(variables)
    if denominator_variables:
        names = ", ".join(sorted(str(symbol) for symbol in denominator_variables))
        raise PolynomialInputError(
            f"variable denominators are unsupported; denominator contains: {names}"
        )

    try:
        polynomial = sp.Poly(expression, *variables, domain=sp.QQ)
    except (CoercionFailed, PolynomialError, TypeError, ValueError) as error:
        raise PolynomialInputError(
            "expression must be a polynomial with exact rational coefficients"
        ) from error

    return {exponent: coefficient for exponent, coefficient in polynomial.terms()}


@dataclass(frozen=True, slots=True, init=False)
class HomogeneousPolynomial:
    """Store a ternary homogeneous polynomial with exact immutable coefficients."""

    variables: Variables
    degree: int
    _terms: tuple[tuple[Exponent, ExactCoefficient], ...]

    def __init__(
        self,
        terms: Mapping[object, object],
        *,
        variables: Sequence[sp.Symbol],
    ) -> None:
        """Validate coefficient terms and initialize an immutable polynomial model."""
        ordered_variables = _validate_variables(variables)
        if not isinstance(terms, Mapping):
            raise PolynomialInputError(
                "terms must be an exponent-to-coefficient mapping"
            )

        validated: dict[Exponent, ExactCoefficient] = {}
        for raw_exponent, raw_coefficient in list(terms.items()):
            exponent = _validate_exponent(raw_exponent, context="term exponent")
            coefficient = _coerce_exact_rational(
                raw_coefficient, context=f"coefficient at exponent {exponent}"
            )
            if coefficient != 0:
                validated[exponent] = coefficient

        degrees = {sum(exponent) for exponent in validated}
        if len(degrees) > 1:
            listed = ", ".join(str(degree) for degree in sorted(degrees))
            raise PolynomialInputError(
                f"polynomial must be homogeneous; found term degrees {listed}"
            )

        degree = next(iter(degrees), 0)
        canonical_terms = tuple(sorted(validated.items(), reverse=True))
        object.__setattr__(self, "variables", ordered_variables)
        object.__setattr__(self, "degree", degree)
        object.__setattr__(self, "_terms", canonical_terms)

    @classmethod
    def from_expr(
        cls,
        expression: object,
        *,
        variables: Sequence[sp.Symbol],
    ) -> HomogeneousPolynomial:
        """Convert an expression or Poly in ordered variables to an exact model."""
        ordered_variables = _validate_variables(variables)
        sympy_expression = _expression_from_input(expression)
        terms = _terms_from_expression(sympy_expression, ordered_variables)
        return cls.from_terms(terms, variables=ordered_variables)

    @classmethod
    def from_terms(
        cls,
        terms: Mapping[object, object],
        *,
        variables: Sequence[sp.Symbol],
    ) -> HomogeneousPolynomial:
        """Convert exponent coefficients in ordered variables to an exact model."""
        return cls(terms, variables=variables)

    @property
    def coefficients(self) -> Mapping[Exponent, ExactCoefficient]:
        """Return a read-only copy of the sparse exact coefficient mapping."""
        return MappingProxyType(dict(self._terms))

    @property
    def is_zero(self) -> bool:
        """Return whether the polynomial has no nonzero terms."""
        return not self._terms

    def coefficient(self, exponent: object) -> ExactCoefficient:
        """Return the exact coefficient at a valid exponent, or zero if absent."""
        validated_exponent = _validate_exponent(exponent)
        return dict(self._terms).get(validated_exponent, sp.S.Zero)

    def to_sympy(self) -> sp.Expr:
        """Return an exact SymPy expression in the stored variable order."""
        expression = sp.S.Zero
        for exponent, coefficient in self._terms:
            monomial = sp.S.One
            for variable, power in zip(self.variables, exponent, strict=True):
                monomial *= variable**power
            expression += coefficient * monomial
        return expression

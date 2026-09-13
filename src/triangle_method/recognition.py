"""Pure direct recognizers that propose exact nonnegative certificate terms."""

from __future__ import annotations

from dataclasses import dataclass, replace
from math import isqrt
from typing import TypeAlias

import sympy as sp
from sympy.polys.polyerrors import PolynomialError

from .certificate import WeightedComponent
from .normalization import Normalization
from .polynomial import HomogeneousPolynomial
from .primitives import MonomialComponent, SchurComponent, SquareComponent
from .results import ProofDiagnostic

WeightedTerms: TypeAlias = tuple[WeightedComponent, ...]
SquareFreeFactors: TypeAlias = tuple[tuple[sp.Poly, int], ...]
LiftableComponent: TypeAlias = SquareComponent | SchurComponent

_MAX_SQUARE_DEGREE = 12
_MAX_SQUARE_TERMS = 128
_MAX_SQUARE_COEFFICIENT_BITS = 4096
_UNIT_ARGUMENTS = ((1, 0, 0), (0, 1, 0), (0, 0, 1))


@dataclass(frozen=True, slots=True)
class RecognitionCandidate:
    """Store one recognizer name and its exact proposed weighted components."""

    method: str
    terms: WeightedTerms


@dataclass(frozen=True, slots=True)
class RecognitionAttempt:
    """Return either one exact candidate or a diagnostic explaining no match."""

    candidate: RecognitionCandidate | None
    diagnostic: ProofDiagnostic


def _matched(
    method: str,
    terms: WeightedTerms,
    *,
    code: str,
    message: str,
) -> RecognitionAttempt:
    """Build a successful immutable recognition attempt from exact weighted terms."""
    return RecognitionAttempt(
        candidate=RecognitionCandidate(method=method, terms=terms),
        diagnostic=ProofDiagnostic(code=code, message=message),
    )


def _not_matched(*, code: str, message: str) -> RecognitionAttempt:
    """Build an unsuccessful recognition attempt with a stable diagnostic code."""
    return RecognitionAttempt(
        candidate=None,
        diagnostic=ProofDiagnostic(code=code, message=message),
    )


def _exception_detail(error: Exception) -> str:
    """Return trimmed exception prose or its type name when no prose is available."""
    return str(error).strip() or type(error).__name__


def _lift_normalized_component(
    normalization: Normalization,
    component: LiftableComponent,
) -> WeightedComponent:
    """Restore one normalized component's scalar and common monomial factors."""
    combined_multiplier = tuple(
        component_power + common_power
        for component_power, common_power in zip(
            component.multiplier,
            normalization.monomial,
            strict=True,
        )
    )
    lifted = replace(component, multiplier=combined_multiplier)
    return WeightedComponent(weight=normalization.scalar, component=lifted)


def recognize_zero(target: HomogeneousPolynomial) -> RecognitionAttempt:
    """Recognize zero as the empty exact sum of nonnegative components."""
    if not target.is_zero:
        return _not_matched(
            code="zero.not_zero",
            message="the target is not the zero polynomial",
        )
    return _matched(
        "zero",
        (),
        code="zero.matched",
        message="the zero polynomial is represented by an empty sum",
    )


def recognize_positive_monomial(
    target: HomogeneousPolynomial,
) -> RecognitionAttempt:
    """Recognize one positive term as a weighted nonnegative monomial."""
    terms = tuple(target.coefficients.items())
    if len(terms) != 1 or terms[0][1] <= 0:
        return _not_matched(
            code="monomial.not_single_positive",
            message="the target is not a single monomial with positive coefficient",
        )

    exponent, coefficient = terms[0]
    weighted = WeightedComponent(
        weight=coefficient,
        component=MonomialComponent(
            exponent=exponent,
            variables=target.variables,
        ),
    )
    return _matched(
        "monomial",
        (weighted,),
        code="monomial.matched",
        message="the target is a positive multiple of one nonnegative monomial",
    )


def recognize_classic_schur(normalization: Normalization) -> RecognitionAttempt:
    """Recognize a scalar and monomial lift of classic three-variable Schur."""
    reduced = normalization.reduced
    if reduced.degree < 3:
        return _not_matched(
            code="schur.degree_too_low",
            message="the reduced target has degree below the supported Schur range",
        )

    base_component = SchurComponent(
        schur_degree=reduced.degree,
        arguments=_UNIT_ARGUMENTS,
        variables=reduced.variables,
    )
    if base_component.expand() != reduced:
        return _not_matched(
            code="schur.not_classic",
            message="the reduced target is not classic Schur in the ordered variables",
        )

    weighted = _lift_normalized_component(normalization, base_component)
    return _matched(
        "classic_schur",
        (weighted,),
        code="schur.matched",
        message="the normalized target is a classic Schur component",
    )


def _square_limit_reason(polynomial: HomogeneousPolynomial) -> str | None:
    """Return the first deterministic square-discovery limit exceeded, if any."""
    if polynomial.degree > _MAX_SQUARE_DEGREE:
        return (
            f"reduced degree {polynomial.degree} exceeds the limit {_MAX_SQUARE_DEGREE}"
        )
    if len(polynomial.coefficients) > _MAX_SQUARE_TERMS:
        return (
            f"reduced term count {len(polynomial.coefficients)} exceeds "
            f"the limit {_MAX_SQUARE_TERMS}"
        )
    if any(
        max(abs(int(coefficient.p)).bit_length(), int(coefficient.q).bit_length())
        > _MAX_SQUARE_COEFFICIENT_BITS
        for coefficient in polynomial.coefficients.values()
    ):
        return (
            "a reduced coefficient exceeds the bit-length limit "
            f"{_MAX_SQUARE_COEFFICIENT_BITS}"
        )
    return None


def _exact_rational_square_root(value: sp.Rational) -> sp.Rational | None:
    """Return the nonnegative rational square root, or None when none exists."""
    if value < 0:
        return None
    numerator_root = isqrt(int(value.p))
    denominator_root = isqrt(int(value.q))
    if numerator_root**2 != value.p or denominator_root**2 != value.q:
        return None
    return sp.Rational(numerator_root, denominator_root)


def _square_free_decomposition(
    polynomial: HomogeneousPolynomial,
) -> tuple[sp.Rational, SquareFreeFactors]:
    """Return the exact QQ square-free coefficient and factors of a polynomial."""
    exact_polynomial = sp.Poly(
        polynomial.to_sympy(),
        *polynomial.variables,
        domain=sp.QQ,
    )
    coefficient, factors = exact_polynomial.sqf_list()
    return sp.Rational(coefficient), tuple(factors)


def _canonical_factor(
    expression: sp.Expr, reduced: HomogeneousPolynomial
) -> HomogeneousPolynomial:
    """Build a homogeneous square factor with positive leading coefficient."""
    factor = HomogeneousPolynomial.from_expr(
        sp.expand(expression),
        variables=reduced.variables,
    )
    leading_exponent = max(factor.coefficients)
    if factor.coefficient(leading_exponent) < 0:
        factor = HomogeneousPolynomial.from_terms(
            {
                exponent: -coefficient
                for exponent, coefficient in factor.coefficients.items()
            },
            variables=factor.variables,
        )
    return factor


def _exact_square_factor(
    reduced: HomogeneousPolynomial,
) -> HomogeneousPolynomial | None:
    """Recover an exact homogeneous factor H when the reduced polynomial is H squared."""
    coefficient, factors = _square_free_decomposition(reduced)
    coefficient_root = _exact_rational_square_root(coefficient)
    if coefficient_root is None or any(multiplicity % 2 for _, multiplicity in factors):
        return None

    root_expression: sp.Expr = coefficient_root
    for factor, multiplicity in factors:
        root_expression *= factor.as_expr() ** (multiplicity // 2)
    root = _canonical_factor(root_expression, reduced)
    reconstructed = HomogeneousPolynomial.from_expr(
        sp.expand(root.to_sympy() ** 2),
        variables=reduced.variables,
    )
    return root if reconstructed == reduced else None


def recognize_exact_square(normalization: Normalization) -> RecognitionAttempt:
    """Recognize a bounded exact rational square with restored scalar and monomial."""
    reduced = normalization.reduced
    if reduced.is_zero:
        return _not_matched(
            code="square.not_exact",
            message="the zero reduced target has no nonzero supported square factor",
        )
    if reduced.degree % 2:
        return _not_matched(
            code="square.degree_odd",
            message="the reduced target does not have even degree",
        )

    leading_exponent = max(reduced.coefficients)
    leading_coefficient = reduced.coefficient(leading_exponent)
    if leading_coefficient <= 0 or any(power % 2 for power in leading_exponent):
        return _not_matched(
            code="square.not_exact",
            message=(
                "the reduced target's leading monomial cannot be the leading "
                "monomial of a rational polynomial square"
            ),
        )

    limit_reason = _square_limit_reason(reduced)
    if limit_reason is not None:
        return _not_matched(
            code="square.limit_exceeded",
            message=f"exact square recognition was skipped because {limit_reason}",
        )

    try:
        factor = _exact_square_factor(reduced)
    except (PolynomialError, NotImplementedError) as error:
        return _not_matched(
            code="square.factorization_failed",
            message=(
                f"exact QQ square-free decomposition failed: {_exception_detail(error)}"
            ),
        )
    if factor is None:
        return _not_matched(
            code="square.not_exact",
            message="the reduced target is not one exact rational polynomial square",
        )

    weighted = _lift_normalized_component(
        normalization,
        SquareComponent(factor=factor),
    )
    return _matched(
        "exact_square",
        (weighted,),
        code="square.matched",
        message="the normalized target is one exact homogeneous square",
    )


def recognize_nonnegative_coefficients(
    target: HomogeneousPolynomial,
) -> RecognitionAttempt:
    """Recognize a polynomial whose exact coefficients are all nonnegative."""
    if any(coefficient < 0 for coefficient in target.coefficients.values()):
        return _not_matched(
            code="coefficients.negative_present",
            message="the target contains at least one negative coefficient",
        )

    terms = tuple(
        WeightedComponent(
            weight=coefficient,
            component=MonomialComponent(
                exponent=exponent,
                variables=target.variables,
            ),
        )
        for exponent, coefficient in sorted(
            target.coefficients.items(),
            reverse=True,
        )
    )
    return _matched(
        "nonnegative_coefficients",
        terms,
        code="coefficients.matched",
        message="every target coefficient is nonnegative",
    )

"""Independent exact verification for Triangle Method certificates."""

from __future__ import annotations

from dataclasses import dataclass

import sympy as sp

from .certificate import (
    PRIMITIVE_VERSION,
    SCHEMA_VERSION,
    DecompositionCertificate,
    WeightedComponent,
)
from .errors import CertificateInputError, PolynomialInputError, PrimitiveInputError
from .polynomial import HomogeneousPolynomial
from .primitives import MonomialComponent, SchurComponent, SquareComponent


@dataclass(frozen=True, slots=True)
class VerificationIssue:
    """Describe one failed certificate check and its optional component position."""

    code: str
    message: str
    term_index: int | None = None


@dataclass(frozen=True, slots=True)
class VerificationReport:
    """Return exact verification status, diagnostics, reconstructed sum, and residual."""

    valid: bool
    issues: tuple[VerificationIssue, ...]
    reconstructed: HomogeneousPolynomial | None
    residual: HomogeneousPolynomial | None

    @property
    def errors(self) -> tuple[str, ...]:
        """Return the human-readable message from every verification issue."""
        return tuple(issue.message for issue in self.issues)


def _rebuild_polynomial(polynomial: HomogeneousPolynomial) -> HomogeneousPolynomial:
    """Reconstruct a polynomial from exact terms instead of trusting object identity."""
    return HomogeneousPolynomial.from_terms(
        polynomial.coefficients,
        variables=polynomial.variables,
    )


def _rebuild_component(
    component: object,
) -> MonomialComponent | SquareComponent | SchurComponent:
    """Reconstruct one supported primitive from its theorem-relevant parameters."""
    if type(component) is MonomialComponent:
        return MonomialComponent(
            exponent=component.exponent,
            variables=component.variables,
        )
    if type(component) is SquareComponent:
        return SquareComponent(
            factor=_rebuild_polynomial(component.factor),
            multiplier=component.multiplier,
        )
    if type(component) is SchurComponent:
        return SchurComponent(
            schur_degree=component.schur_degree,
            arguments=component.arguments,
            variables=component.variables,
            multiplier=component.multiplier,
        )
    raise PrimitiveInputError(
        f"unsupported primitive component type: {type(component).__name__}"
    )


def _add_scaled_terms(
    coefficients: dict[tuple[int, int, int], sp.Rational],
    polynomial: HomogeneousPolynomial,
    weight: sp.Rational,
) -> None:
    """Accumulate one exactly weighted polynomial into a sparse coefficient mapping."""
    for exponent, coefficient in polynomial.coefficients.items():
        updated = coefficients.get(exponent, sp.S.Zero) + weight * coefficient
        if updated == 0:
            coefficients.pop(exponent, None)
        else:
            coefficients[exponent] = updated


def _subtract_polynomials(
    minuend: HomogeneousPolynomial,
    subtrahend: HomogeneousPolynomial,
) -> HomogeneousPolynomial:
    """Return the exact sparse difference of two polynomials in the same basis."""
    coefficients = dict(minuend.coefficients)
    for exponent, coefficient in subtrahend.coefficients.items():
        updated = coefficients.get(exponent, sp.S.Zero) - coefficient
        if updated == 0:
            coefficients.pop(exponent, None)
        else:
            coefficients[exponent] = updated
    return HomogeneousPolynomial.from_terms(coefficients, variables=minuend.variables)


def verify_certificate(certificate: DecompositionCertificate) -> VerificationReport:
    """Rebuild and exactly check every weighted primitive against its target identity."""
    if type(certificate) is not DecompositionCertificate:
        raise CertificateInputError("certificate must be a DecompositionCertificate")

    issues: list[VerificationIssue] = []
    for field, expected in (
        ("schema_version", SCHEMA_VERSION),
        ("primitive_version", PRIMITIVE_VERSION),
    ):
        actual = getattr(certificate, field, None)
        if type(actual) is not int or actual != expected:
            issues.append(
                VerificationIssue(
                    code=f"unsupported_{field}",
                    message=(
                        f"certificate {field} {actual!r} is unsupported; "
                        f"expected {expected}"
                    ),
                )
            )

    if issues:
        return VerificationReport(
            valid=False,
            issues=tuple(issues),
            reconstructed=None,
            residual=None,
        )

    target = _rebuild_polynomial(certificate.target)
    accumulated: dict[tuple[int, int, int], sp.Rational] = {}
    can_reconstruct = True

    for term_index, weighted in enumerate(certificate.terms):
        if type(weighted) is not WeightedComponent:
            issues.append(
                VerificationIssue(
                    code="unsupported_weighted_term",
                    message=f"term {term_index} is not a supported weighted component",
                    term_index=term_index,
                )
            )
            can_reconstruct = False
            continue

        weight = weighted.weight
        if not isinstance(weight, sp.Rational):
            issues.append(
                VerificationIssue(
                    code="inexact_weight",
                    message=f"term {term_index} weight is not an exact rational",
                    term_index=term_index,
                )
            )
            can_reconstruct = False
            continue
        if weight < 0:
            issues.append(
                VerificationIssue(
                    code="negative_weight",
                    message=f"term {term_index} has negative weight {weight}",
                    term_index=term_index,
                )
            )

        try:
            component = _rebuild_component(weighted.component)
        except (PolynomialInputError, PrimitiveInputError) as error:
            issues.append(
                VerificationIssue(
                    code="invalid_component",
                    message=f"term {term_index} is invalid: {error}",
                    term_index=term_index,
                )
            )
            can_reconstruct = False
            continue

        if component.variables != target.variables:
            issues.append(
                VerificationIssue(
                    code="variable_order_mismatch",
                    message=(
                        f"term {term_index} variable order does not match the target"
                    ),
                    term_index=term_index,
                )
            )
            can_reconstruct = False
            continue
        if component.degree != target.degree:
            issues.append(
                VerificationIssue(
                    code="degree_mismatch",
                    message=(
                        f"term {term_index} has formal degree {component.degree}; "
                        f"target degree is {target.degree}"
                    ),
                    term_index=term_index,
                )
            )
            can_reconstruct = False
            continue

        try:
            expanded = component.expand()
        except (PolynomialInputError, PrimitiveInputError) as error:
            issues.append(
                VerificationIssue(
                    code="component_expansion_failed",
                    message=f"term {term_index} could not be expanded: {error}",
                    term_index=term_index,
                )
            )
            can_reconstruct = False
            continue
        if not expanded.is_zero and expanded.degree != component.degree:
            issues.append(
                VerificationIssue(
                    code="expansion_degree_mismatch",
                    message=(
                        f"term {term_index} expansion degree does not match its "
                        "formal degree"
                    ),
                    term_index=term_index,
                )
            )
            can_reconstruct = False
            continue
        _add_scaled_terms(accumulated, expanded, weight)

    if not can_reconstruct:
        return VerificationReport(
            valid=False,
            issues=tuple(issues),
            reconstructed=None,
            residual=None,
        )

    reconstructed = HomogeneousPolynomial.from_terms(
        accumulated,
        variables=target.variables,
    )
    residual = _subtract_polynomials(target, reconstructed)
    if not residual.is_zero:
        issues.append(
            VerificationIssue(
                code="identity_mismatch",
                message="weighted components do not reconstruct the target exactly",
            )
        )

    return VerificationReport(
        valid=not issues,
        issues=tuple(issues),
        reconstructed=reconstructed,
        residual=residual,
    )

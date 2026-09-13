"""Immutable exact weighted components and manual decomposition certificates."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import TypeAlias

from .errors import CertificateInputError, PolynomialInputError
from .polynomial import (
    ExactCoefficient,
    ExactCoefficientInput,
    HomogeneousPolynomial,
    _coerce_exact_rational,
)
from .primitives import MonomialComponent, SchurComponent, SquareComponent

SupportedComponent: TypeAlias = MonomialComponent | SquareComponent | SchurComponent
_COMPONENT_TYPES = (MonomialComponent, SquareComponent, SchurComponent)
SCHEMA_VERSION = 1
PRIMITIVE_VERSION = 1


@dataclass(frozen=True, slots=True, init=False, kw_only=True)
class WeightedComponent:
    """Pair a supported primitive with an exact nonnegative rational weight."""

    weight: ExactCoefficient
    component: SupportedComponent

    def __init__(
        self,
        *,
        weight: ExactCoefficientInput,
        component: SupportedComponent,
    ) -> None:
        """Validate an exact nonnegative weight and store its supported component."""
        try:
            exact_weight = _coerce_exact_rational(weight, context="component weight")
        except PolynomialInputError as error:
            raise CertificateInputError(str(error)) from error
        if exact_weight < 0:
            raise CertificateInputError("component weight must be nonnegative")
        if type(component) not in _COMPONENT_TYPES:
            raise CertificateInputError(
                "component must be an exact supported primitive type"
            )

        object.__setattr__(self, "weight", exact_weight)
        object.__setattr__(self, "component", component)


@dataclass(frozen=True, slots=True, init=False, kw_only=True)
class DecompositionCertificate:
    """Store a target and immutable weighted terms for independent exact verification."""

    target: HomogeneousPolynomial
    terms: tuple[WeightedComponent, ...]
    schema_version: int = field(default=SCHEMA_VERSION, init=False)
    primitive_version: int = field(default=PRIMITIVE_VERSION, init=False)

    def __init__(
        self,
        *,
        target: HomogeneousPolynomial,
        terms: Iterable[WeightedComponent],
    ) -> None:
        """Copy weighted terms and validate their types and target variable order."""
        if not isinstance(target, HomogeneousPolynomial):
            raise CertificateInputError("target must be a HomogeneousPolynomial")
        if isinstance(terms, (str, bytes)):
            raise CertificateInputError(
                "terms must be an iterable of WeightedComponent objects"
            )
        try:
            copied_terms = tuple(terms)
        except TypeError as error:
            raise CertificateInputError(
                "terms must be an iterable of WeightedComponent objects"
            ) from error

        for index, term in enumerate(copied_terms):
            if type(term) is not WeightedComponent:
                raise CertificateInputError(f"term {index} must be a WeightedComponent")
            if type(term.component) not in _COMPONENT_TYPES:
                raise CertificateInputError(
                    f"term {index} has an unsupported component type"
                )
            if term.component.variables != target.variables:
                raise CertificateInputError(
                    f"term {index} must use the target's exact variable order"
                )

        object.__setattr__(self, "target", target)
        object.__setattr__(self, "terms", copied_terms)
        object.__setattr__(self, "schema_version", SCHEMA_VERSION)
        object.__setattr__(self, "primitive_version", PRIMITIVE_VERSION)

    def to_json(self, *, indent: int | None = 2) -> str:
        """Serialize exact primitive parameters and the target as deterministic JSON."""
        from .serialization import certificate_to_json

        return certificate_to_json(self, indent=indent)

    @classmethod
    def from_json(cls, document: str) -> DecompositionCertificate:
        """Parse strict versioned JSON into a certificate without asserting validity."""
        from .serialization import certificate_from_json

        return certificate_from_json(document)

"""Closed built-in nonnegative primitive component types."""

from typing import TypeAlias

from .monomial import MonomialComponent
from .schur import SchurComponent
from .square import SquareComponent

PrimitiveComponent: TypeAlias = MonomialComponent | SquareComponent | SchurComponent

__all__ = [
    "MonomialComponent",
    "PrimitiveComponent",
    "SchurComponent",
    "SquareComponent",
]

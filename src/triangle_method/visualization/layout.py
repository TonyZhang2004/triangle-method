"""Exact coefficient labels and deterministic equilateral layout data."""

from __future__ import annotations

from dataclasses import dataclass
from math import sqrt

import sympy as sp

from ..polynomial import ExactCoefficient
from ..triangle import CoefficientRows

_FONT_SIZE = 20.0
_MINIMUM_HORIZONTAL_STEP = 88.0
_MONOSPACE_CHARACTER_WIDTH = 0.65 * _FONT_SIZE
_LABEL_GAP = 32.0
_MINIMUM_EDGE_PADDING = 24.0
_LABEL_EDGE_PADDING = 16.0
_VERTICAL_PADDING = 24.0
_EQUILATERAL_ALTITUDE = sqrt(3.0) / 2.0
_MINUS_SIGN = "−"


@dataclass(frozen=True, slots=True)
class CoefficientMark:
    """Describe one exact coefficient and its rendered triangle position."""

    row: int
    column: int
    coefficient: ExactCoefficient
    text: str
    x: float
    y: float


@dataclass(frozen=True, slots=True)
class TriangleLayout:
    """Store immutable coefficient marks and deterministic canvas geometry."""

    rows: CoefficientRows
    degree: int
    marks: tuple[CoefficientMark, ...]
    horizontal_step: float
    vertical_step: float
    font_size: float
    width: float
    height: float


def format_coefficient(coefficient: ExactCoefficient) -> str:
    """Format one exact rational as integer or numerator/denominator display text."""
    if not isinstance(coefficient, sp.Rational):
        raise TypeError("coefficient must be an exact SymPy rational")

    numerator = int(coefficient.p)
    denominator = int(coefficient.q)
    sign = _MINUS_SIGN if numerator < 0 else ""
    magnitude = abs(numerator)
    if denominator == 1:
        return f"{sign}{magnitude}"
    return f"{sign}{magnitude}/{denominator}"


def _validate_rows(rows: CoefficientRows) -> CoefficientRows:
    """Copy and validate exact triangular rows for immutable layout construction."""
    materialized = tuple(tuple(row) for row in rows)
    if not materialized:
        raise ValueError("coefficient rows cannot be empty")

    for row_index, row in enumerate(materialized):
        expected_length = row_index + 1
        if len(row) != expected_length:
            raise ValueError(
                f"coefficient row {row_index} must contain {expected_length} entries"
            )
        if any(not isinstance(coefficient, sp.Rational) for coefficient in row):
            raise TypeError("coefficient rows must contain exact SymPy rationals")

    return materialized


def _label_geometry(labels: tuple[str, ...]) -> tuple[float, float]:
    """Choose one global row step and edge padding from the longest label."""
    longest_label = max(len(label) for label in labels)
    longest_width = longest_label * _MONOSPACE_CHARACTER_WIDTH
    horizontal_step = max(
        _MINIMUM_HORIZONTAL_STEP,
        longest_width + _LABEL_GAP,
    )
    edge_padding = max(
        _MINIMUM_EDGE_PADDING,
        longest_width / 2.0 + _LABEL_EDGE_PADDING,
    )
    return horizontal_step, edge_padding


def build_triangle_layout(rows: CoefficientRows) -> TriangleLayout:
    """Place exact coefficient rows on an equilateral lattice and size the canvas."""
    exact_rows = _validate_rows(rows)
    degree = len(exact_rows) - 1
    labels = tuple(
        format_coefficient(coefficient) for row in exact_rows for coefficient in row
    )
    horizontal_step, edge_padding = _label_geometry(labels)
    vertical_step = _EQUILATERAL_ALTITUDE * horizontal_step

    marks: list[CoefficientMark] = []
    label_index = 0
    for row_index, row in enumerate(exact_rows):
        y = _VERTICAL_PADDING + row_index * vertical_step
        for column_index, coefficient in enumerate(row):
            x = (
                edge_padding
                + ((degree - row_index) / 2.0 + column_index) * horizontal_step
            )
            marks.append(
                CoefficientMark(
                    row=row_index,
                    column=column_index,
                    coefficient=coefficient,
                    text=labels[label_index],
                    x=x,
                    y=y,
                )
            )
            label_index += 1

    width = 2.0 * edge_padding + degree * horizontal_step
    height = 2.0 * _VERTICAL_PADDING + degree * vertical_step
    return TriangleLayout(
        rows=exact_rows,
        degree=degree,
        marks=tuple(marks),
        horizontal_step=horizontal_step,
        vertical_step=vertical_step,
        font_size=_FONT_SIZE,
        width=width,
        height=height,
    )

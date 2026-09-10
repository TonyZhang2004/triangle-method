"""Public reusable coefficient-triangle figure and explicit file exports."""

from __future__ import annotations

from dataclasses import dataclass, field
from os import PathLike
from pathlib import Path

from ..polynomial import HomogeneousPolynomial
from ..triangle import CoefficientRows, coefficient_rows
from .layout import TriangleLayout, build_triangle_layout
from .rendering import render_html_document, render_html_fragment, render_svg


def _write_text(
    path: str | PathLike[str],
    content: str,
    *,
    overwrite: bool,
) -> Path:
    """Write UTF-8 text to an explicit path and return it, protecting existing files."""
    destination = Path(path)
    mode = "w" if overwrite else "x"
    with destination.open(mode, encoding="utf-8", newline="\n") as output:
        output.write(content)
    return destination


@dataclass(frozen=True, slots=True, repr=False)
class CoefficientTriangle:
    """Store one immutable exact coefficient layout with SVG and HTML renderers."""

    _layout: TriangleLayout = field(repr=False)

    @property
    def degree(self) -> int:
        """Return the displayed homogeneous degree."""
        return self._layout.degree

    @property
    def rows(self) -> CoefficientRows:
        """Return the exact immutable coefficient rows shown by the figure."""
        return self._layout.rows

    def to_svg(self) -> str:
        """Return deterministic self-contained SVG for this coefficient triangle."""
        return render_svg(self._layout)

    def to_html(self) -> str:
        """Return a notebook-safe HTML fragment containing this triangle's SVG."""
        return render_html_fragment(self._layout)

    def _repr_html_(self) -> str:
        """Return the same HTML fragment when a notebook displays this figure."""
        return self.to_html()

    def save_svg(
        self,
        path: str | PathLike[str],
        *,
        overwrite: bool = False,
    ) -> Path:
        """Write SVG to an explicit UTF-8 path and return the written path."""
        return _write_text(path, self.to_svg(), overwrite=overwrite)

    def save_html(
        self,
        path: str | PathLike[str],
        *,
        overwrite: bool = False,
    ) -> Path:
        """Write standalone HTML to an explicit UTF-8 path and return that path."""
        return _write_text(
            path,
            render_html_document(self._layout),
            overwrite=overwrite,
        )

    def __repr__(self) -> str:
        """Return a concise text representation containing degree and exact rows."""
        return f"CoefficientTriangle(degree={self.degree}, rows={self.rows!r})"


def coefficient_triangle(
    polynomial: HomogeneousPolynomial,
    *,
    display_degree: int | None = None,
) -> CoefficientTriangle:
    """Build a reusable coefficient triangle from an exact polynomial model."""
    rows = coefficient_rows(polynomial, display_degree=display_degree)
    return CoefficientTriangle(build_triangle_layout(rows))

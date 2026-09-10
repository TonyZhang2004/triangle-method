"""Tests for explicit and overwrite-safe SVG and HTML exports."""

from __future__ import annotations

from pathlib import Path

import pytest
import sympy as sp

from triangle_method import (
    CoefficientTriangle,
    HomogeneousPolynomial,
    coefficient_triangle,
)


def _sample_figure(
    ternary_symbols: tuple[sp.Symbol, sp.Symbol, sp.Symbol],
) -> CoefficientTriangle:
    """Build a small exact figure containing a typographic negative sign."""

    x, y, z = ternary_symbols
    polynomial = HomogeneousPolynomial.from_expr(
        x**2 + y**2 + z**2 - x * y - x * z - y * z,
        variables=(x, y, z),
    )
    return coefficient_triangle(polynomial)


def test_save_svg_writes_exact_utf8_serialization_and_returns_path(
    ternary_symbols: tuple[sp.Symbol, sp.Symbol, sp.Symbol],
    tmp_path: Path,
) -> None:
    """Write the in-memory SVG bytes to the caller's explicit path."""

    figure = _sample_figure(ternary_symbols)
    destination = tmp_path / "triangle.svg"

    returned = figure.save_svg(destination)

    assert returned == destination
    assert isinstance(returned, Path)
    assert destination.read_text(encoding="utf-8") == figure.to_svg()
    assert "−".encode() in destination.read_bytes()


def test_save_html_writes_a_standalone_document_around_the_same_fragment(
    ternary_symbols: tuple[sp.Symbol, sp.Symbol, sp.Symbol],
    tmp_path: Path,
) -> None:
    """Export self-contained UTF-8 HTML containing the notebook fragment unchanged."""

    figure = _sample_figure(ternary_symbols)
    destination = tmp_path / "triangle.html"

    returned = figure.save_html(str(destination))
    document = destination.read_text(encoding="utf-8")

    assert returned == destination
    assert document.lstrip().casefold().startswith("<!doctype html")
    assert 'charset="utf-8"' in document.casefold()
    assert figure.to_html() in document
    assert figure.to_svg() in document
    assert "<script" not in document.casefold()
    assert "<link" not in document.casefold()
    assert " src=" not in document.casefold()


@pytest.mark.parametrize("method_name", ["save_svg", "save_html"])
def test_exports_require_an_existing_parent_directory(
    method_name: str,
    ternary_symbols: tuple[sp.Symbol, sp.Symbol, sp.Symbol],
    tmp_path: Path,
) -> None:
    """Surface normal filesystem errors instead of creating parent directories."""

    figure = _sample_figure(ternary_symbols)
    missing_parent = (
        tmp_path / "missing" / f"triangle.{method_name.removeprefix('save_')}"
    )

    with pytest.raises(OSError):
        getattr(figure, method_name)(missing_parent)

    assert not missing_parent.parent.exists()


@pytest.mark.parametrize("method_name", ["save_svg", "save_html"])
def test_exports_refuse_to_replace_an_existing_file_by_default(
    method_name: str,
    ternary_symbols: tuple[sp.Symbol, sp.Symbol, sp.Symbol],
    tmp_path: Path,
) -> None:
    """Leave existing contents untouched unless overwrite is explicitly requested."""

    figure = _sample_figure(ternary_symbols)
    destination = tmp_path / f"existing.{method_name.removeprefix('save_')}"
    destination.write_text("keep me", encoding="utf-8")

    with pytest.raises(FileExistsError):
        getattr(figure, method_name)(destination)

    assert destination.read_text(encoding="utf-8") == "keep me"


@pytest.mark.parametrize("method_name", ["save_svg", "save_html"])
def test_exports_replace_an_existing_file_when_explicitly_requested(
    method_name: str,
    ternary_symbols: tuple[sp.Symbol, sp.Symbol, sp.Symbol],
    tmp_path: Path,
) -> None:
    """Honor overwrite=True and return the path containing the new serialization."""

    figure = _sample_figure(ternary_symbols)
    destination = tmp_path / f"replace.{method_name.removeprefix('save_')}"
    destination.write_text("old contents", encoding="utf-8")

    returned = getattr(figure, method_name)(destination, overwrite=True)

    assert returned == destination
    assert destination.read_text(encoding="utf-8") != "old contents"
    if method_name == "save_svg":
        assert destination.read_text(encoding="utf-8") == figure.to_svg()
    else:
        assert figure.to_html() in destination.read_text(encoding="utf-8")

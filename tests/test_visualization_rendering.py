"""Structural tests for deterministic coefficient-only SVG and HTML."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

import pytest
import sympy as sp

from triangle_method import HomogeneousPolynomial, coefficient_triangle
from triangle_method.visualization.layout import build_triangle_layout

SVG_NAMESPACE = "http://www.w3.org/2000/svg"


def _svg_element(markup: str) -> ET.Element:
    """Parse SVG markup and return its root element."""

    return ET.fromstring(markup)


def _coefficient_text_elements(root: ET.Element) -> list[ET.Element]:
    """Return the visible coefficient nodes, excluding title and description text."""

    return [
        element
        for element in root.findall(f".//{{{SVG_NAMESPACE}}}text")
        if "data-row" in element.attrib
    ]


def _local_name(element: ET.Element) -> str:
    """Return an XML element name without its namespace."""

    return element.tag.rsplit("}", maxsplit=1)[-1]


def test_svg_text_and_metadata_come_from_the_exact_layout(
    ternary_symbols: tuple[sp.Symbol, sp.Symbol, sp.Symbol],
) -> None:
    """Match every rendered mark to its exact row, column, label, and coefficient."""

    x, y, z = ternary_symbols
    expression = (
        x**2
        - sp.Rational(3, 7) * x * y
        + 2 * x * z
        + 12345678901234567890 * y**2
        + sp.Rational(2, 5) * y * z
        - 9 * z**2
    )
    figure = coefficient_triangle(
        HomogeneousPolynomial.from_expr(expression, variables=(x, y, z))
    )
    layout = build_triangle_layout(figure.rows)
    root = _svg_element(figure.to_svg())
    elements = _coefficient_text_elements(root)
    by_position = {
        (int(element.attrib["data-row"]), int(element.attrib["data-column"])): element
        for element in elements
    }

    assert len(elements) == len(layout.marks)
    for mark in layout.marks:
        element = by_position[(mark.row, mark.column)]
        assert element.text == mark.text
        assert element.attrib["data-coefficient"] == str(mark.coefficient)
        assert float(element.attrib["x"]) == pytest.approx(mark.x)
        assert float(element.attrib["y"]) == pytest.approx(mark.y)


def test_svg_has_a_positive_matching_viewbox_and_accessible_row_description(
    ternary_symbols: tuple[sp.Symbol, sp.Symbol, sp.Symbol],
) -> None:
    """Expose figure dimensions and readable rows without document-global IDs."""

    x, y, z = ternary_symbols
    expression = x**2 - sp.Rational(3, 7) * x * y + y**2 + z**2
    figure = coefficient_triangle(
        HomogeneousPolynomial.from_expr(expression, variables=(x, y, z))
    )
    layout = build_triangle_layout(figure.rows)
    root = _svg_element(figure.to_svg())
    viewbox = tuple(float(value) for value in root.attrib["viewBox"].split())
    title = root.find(f"{{{SVG_NAMESPACE}}}title")
    description = root.find(f"{{{SVG_NAMESPACE}}}desc")

    assert viewbox[:2] == pytest.approx((0.0, 0.0))
    assert viewbox[2:] == pytest.approx((layout.width, layout.height))
    assert viewbox[2] > 0
    assert viewbox[3] > 0
    assert root.attrib["role"] == "img"
    assert root.attrib["preserveAspectRatio"] == "xMidYMid meet"
    assert root.attrib.get("aria-label")
    assert title is not None and title.text
    assert description is not None and description.text
    accessible_text = " ".join(
        filter(None, (root.attrib.get("aria-label"), title.text, description.text))
    ).casefold()
    assert "row 1" in accessible_text
    assert "row 2" in accessible_text
    assert "negative 3 over 7" in accessible_text
    assert "zero" in accessible_text


def test_svg_contains_coefficients_but_no_grid_or_monomial_labels(
    ternary_symbols: tuple[sp.Symbol, sp.Symbol, sp.Symbol],
) -> None:
    """Limit visible geometry to coefficient text with no triangle decoration."""

    x, y, z = ternary_symbols
    polynomial = HomogeneousPolynomial.from_expr(
        x**2 + y**2 + z**2 - x * y - x * z - y * z,
        variables=(x, y, z),
    )
    root = _svg_element(coefficient_triangle(polynomial).to_svg())
    forbidden_shapes = {"line", "path", "polygon", "polyline", "circle", "rect"}
    element_names = {_local_name(element) for element in root.iter()}
    coefficient_nodes = _coefficient_text_elements(root)
    visible_labels = [node.text or "" for node in coefficient_nodes]
    all_prose = " ".join(
        element.text or ""
        for element in root.iter()
        if _local_name(element) in {"title", "desc", "text"}
    )

    assert forbidden_shapes.isdisjoint(element_names)
    assert visible_labels == ["1", "−1", "−1", "1", "−1", "1"]
    assert not re.search(r"\b[xyz]\b", all_prose, flags=re.IGNORECASE)
    assert "^" not in all_prose


def test_html_fragment_and_notebook_representation_reuse_the_same_svg(
    ternary_symbols: tuple[sp.Symbol, sp.Symbol, sp.Symbol],
) -> None:
    """Wrap one SVG for notebook use with local horizontal scrolling."""

    x, y, z = ternary_symbols
    figure = coefficient_triangle(
        HomogeneousPolynomial.from_expr(x**2 + y**2 + z**2, variables=(x, y, z))
    )

    svg = figure.to_svg()
    html = figure.to_html()

    assert svg in html
    assert figure._repr_html_() == html
    assert "overflow-x:auto" in re.sub(r"\s+", "", html)
    assert "<script" not in html.casefold()
    assert "<link" not in html.casefold()
    assert " src=" not in html.casefold()
    assert " href=" not in html.casefold()


def test_svg_and_html_serialization_are_byte_for_byte_deterministic(
    ternary_symbols: tuple[sp.Symbol, sp.Symbol, sp.Symbol],
) -> None:
    """Exclude random IDs, timestamps, and environment state from serialization."""

    x, y, z = ternary_symbols
    polynomial = HomogeneousPolynomial.from_expr(
        x**3 + 2 * x * y * z - z**3,
        variables=(x, y, z),
    )
    first = coefficient_triangle(polynomial)
    second = coefficient_triangle(polynomial)

    assert first.to_svg() == first.to_svg() == second.to_svg()
    assert first.to_html() == first.to_html() == second.to_html()


def test_svg_is_well_formed_with_negative_and_rational_accessibility_text(
    ternary_symbols: tuple[sp.Symbol, sp.Symbol, sp.Symbol],
) -> None:
    """Keep exact signs and rational wording valid in both XML text and attributes."""

    x, y, z = ternary_symbols
    polynomial = HomogeneousPolynomial.from_expr(
        -sp.Rational(11, 13) * x + 2 * y,
        variables=(x, y, z),
    )

    root = _svg_element(coefficient_triangle(polynomial).to_svg())
    marks = _coefficient_text_elements(root)

    assert [mark.text for mark in marks] == ["−11/13", "2", "0"]
    assert [mark.attrib["data-coefficient"] for mark in marks] == ["-11/13", "2", "0"]
    assert "negative 11 over 13" in " ".join(root.itertext()).casefold()

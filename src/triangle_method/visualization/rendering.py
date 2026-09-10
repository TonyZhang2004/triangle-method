"""Deterministic accessible SVG and HTML coefficient-triangle rendering."""

from __future__ import annotations

from html import escape

from ..polynomial import ExactCoefficient
from .layout import CoefficientMark, TriangleLayout

_SVG_TITLE = "Coefficient triangle"


def _format_number(value: float) -> str:
    """Serialize a presentation coordinate compactly with stable precision."""
    formatted = f"{value:.6f}".rstrip("0").rstrip(".")
    return formatted or "0"


def _spoken_coefficient(coefficient: ExactCoefficient) -> str:
    """Describe an exact coefficient using screen-reader-friendly sign and fraction words."""
    numerator = int(coefficient.p)
    denominator = int(coefficient.q)
    if numerator == 0:
        return "zero"

    sign = "negative " if numerator < 0 else ""
    magnitude = abs(numerator)
    if denominator == 1:
        return f"{sign}{magnitude}"
    return f"{sign}{magnitude} over {denominator}"


def _describe_rows(layout: TriangleLayout) -> str:
    """Return an accessible row-by-row description including every coefficient."""
    descriptions = []
    for row_index, row in enumerate(layout.rows, start=1):
        coefficients = ", ".join(_spoken_coefficient(value) for value in row)
        descriptions.append(f"row {row_index}: {coefficients}.")
    return f"{_SVG_TITLE}. {' '.join(descriptions)}"


def _render_mark(mark: CoefficientMark) -> str:
    """Serialize one positioned coefficient mark as an SVG text element."""
    attributes = (
        f'data-row="{mark.row}" '
        f'data-column="{mark.column}" '
        f'data-coefficient="{escape(str(mark.coefficient), quote=True)}" '
        f'x="{_format_number(mark.x)}" '
        f'y="{_format_number(mark.y)}"'
    )
    return f"<text {attributes}>{escape(mark.text)}</text>"


def render_svg(layout: TriangleLayout) -> str:
    """Serialize one layout as self-contained accessible coefficient-only SVG."""
    width = _format_number(layout.width)
    height = _format_number(layout.height)
    description = _describe_rows(layout)
    escaped_description = escape(description)
    escaped_label = escape(description, quote=True)
    mark_lines = "\n".join(f"    {_render_mark(mark)}" for mark in layout.marks)

    return (
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'role="img" focusable="false" '
        f'aria-label="{escaped_label}" '
        f'width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" '
        'preserveAspectRatio="xMidYMid meet" '
        'style="display: block; margin-inline: auto; color: inherit;">\n'
        f"  <title>{_SVG_TITLE}</title>\n"
        f"  <desc>{escaped_description}</desc>\n"
        '  <g fill="currentColor" text-anchor="middle" '
        'dominant-baseline="middle" '
        'font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" '
        f'font-size="{_format_number(layout.font_size)}">\n'
        f"{mark_lines}\n"
        "  </g>\n"
        "</svg>"
    )


def render_html_fragment(layout: TriangleLayout) -> str:
    """Wrap a layout's SVG in a scoped horizontally scrollable notebook fragment."""
    svg = render_svg(layout)
    return (
        '<div class="triangle-method-coefficient-triangle" '
        'style="max-width: 100%; overflow-x: auto; color: inherit;">\n'
        f"{svg}\n"
        "</div>"
    )


def render_html_document(layout: TriangleLayout) -> str:
    """Wrap a layout's notebook fragment in a standalone UTF-8 HTML document."""
    fragment = render_html_fragment(layout)
    return (
        "<!doctype html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '  <meta charset="utf-8">\n'
        '  <meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"  <title>{_SVG_TITLE}</title>\n"
        "  <style>\n"
        "    :root { color-scheme: light dark; }\n"
        "    body { margin: 0; padding: 1rem; color: CanvasText; "
        "background: Canvas; }\n"
        "  </style>\n"
        "</head>\n"
        "<body>\n"
        f"{fragment}\n"
        "</body>\n"
        "</html>"
    )

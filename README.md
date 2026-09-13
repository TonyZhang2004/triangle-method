# Triangle Method

Triangle Method is a Python package for working with exact coefficient triangles
of ternary homogeneous polynomials. It provides the mathematical data model,
coefficient-row conversion, reversible content normalization, and static SVG/HTML
rendering. It also supports manually authored, exactly verified decomposition
certificates. Automatic proof search belongs to later batches.

## Exact polynomial model

The package accepts a SymPy expression or `Poly`, an exact scalar constant, or
an exponent-to-coefficient mapping. Every input uses three explicitly ordered,
distinct commutative SymPy symbols. Variables may be absent from the polynomial,
but their order is never inferred.

Coefficients must be exact integers or rational numbers. Use `sympy.Rational`
or `fractions.Fraction` for fractions; floating coefficients are rejected so
that an approximate value cannot silently change the polynomial being studied.

```python
import sympy as sp

from triangle_method import (
    HomogeneousPolynomial,
    coefficient_rows,
    from_coefficient_rows,
)

x, y, z = sp.symbols("x y z")
expression = x**2 + y**2 + z**2 - x * y - y * z - z * x

polynomial = HomogeneousPolynomial.from_expr(
    expression,
    variables=(x, y, z),
)
rows = coefficient_rows(polynomial)

assert rows == ((1,), (-1, -1), (1, -1, 1))

reconstructed = from_coefficient_rows(rows, variables=(x, y, z))
assert reconstructed == polynomial
assert sp.expand(reconstructed.to_sympy() - expression) == 0
```

For a degree `n` polynomial, row `r`, column `j` stores the coefficient

```text
(n - r, r - j, j) -> coefficient of x**(n-r) * y**(r-j) * z**j.
```

Missing terms appear as exact zeros in the rows. The zero polynomial has
canonical degree zero; pass `display_degree` to `coefficient_rows` when an
all-zero triangle of a larger degree is needed.

## Static coefficient triangles

Create one immutable figure from the exact polynomial model. The same figure can
be displayed in a notebook or serialized as SVG and HTML:

```python
from triangle_method import coefficient_triangle

triangle = coefficient_triangle(polynomial)

assert triangle.degree == 2
assert triangle.rows == ((1,), (-1, -1), (1, -1, 1))

svg = triangle.to_svg()
html = triangle.to_html()
```

In Jupyter, leave `triangle` as the final expression in a cell to display its
notebook HTML representation. `to_html()` returns the same inline fragment,
whereas `save_html()` wraps it in a complete standalone HTML document. The
drawing contains coefficients only, including every zero. Integers and rational
numbers remain exact; no monomial labels, grid lines, cells, or triangle outline
are drawn.

The first ordered variable is the top vertex. The second and third ordered
variables determine the left and right base directions. This is the same
orientation used by `coefficient_rows`.

Exports require an explicit path and return the `Path` written. Parent
directories are not created automatically, and existing files are preserved
unless `overwrite=True` is requested:

```python
from pathlib import Path

output_directory = Path(".tmp/readme-example")
output_directory.mkdir(parents=True, exist_ok=True)

triangle.save_svg(output_directory / "quadratic.svg", overwrite=True)
triangle.save_html(output_directory / "quadratic.html", overwrite=True)
```

To draw an all-zero triangle at a chosen degree, pass that degree when creating
the figure:

```python
zero = HomogeneousPolynomial.from_expr(0, variables=(x, y, z))
zero_triangle = coefficient_triangle(zero, display_degree=5)

assert zero_triangle.degree == 5
assert len(zero_triangle.rows) == 6
```

Rendering uses only the Python standard library beyond the package's existing
SymPy dependency. It does not require IPython, a browser package, or a numerical
solver.

## Manual exact certificates

A certificate expresses one target as an exact nonnegative rational combination
of built-in components. Batch 3 supports coefficient-one monomials, monomial
multiples of homogeneous polynomial squares, and Schur components with
equal-degree monomial substitutions. These primitives are nonnegative on the
nonnegative orthant of the certificate's three ordered variables.

For example, the quadratic coefficient triangle has the certificate

\[
x^2+y^2+z^2-xy-yz-zx
=\tfrac12(x-y)^2+\tfrac12(y-z)^2+\tfrac12(z-x)^2.
\]

```python
from triangle_method import (
    DecompositionCertificate,
    SquareComponent,
    WeightedComponent,
    verify_certificate,
)

linear_factors = (
    HomogeneousPolynomial.from_expr(x - y, variables=(x, y, z)),
    HomogeneousPolynomial.from_expr(y - z, variables=(x, y, z)),
    HomogeneousPolynomial.from_expr(z - x, variables=(x, y, z)),
)
certificate = DecompositionCertificate(
    target=polynomial,
    terms=tuple(
        WeightedComponent(
            weight=sp.Rational(1, 2),
            component=SquareComponent(factor=factor),
        )
        for factor in linear_factors
    ),
)

report = verify_certificate(certificate)
assert report.valid
assert report.residual is not None and report.residual.is_zero
```

Verification reconstructs every built-in component from its defining parameters,
checks supported certificate versions, formal degrees, and exact nonnegative
weights, and compares the resulting coefficient mapping with the target. A failed
identity returns a report with diagnostic issues; it is never treated as evidence
that the target is negative.

Certificates have deterministic, versioned JSON serialization:

```python
document = certificate.to_json()
restored = DecompositionCertificate.from_json(document)

assert verify_certificate(restored).valid
assert restored.to_json() == document
```

JSON stores rational numerators and denominators, exponent triples, ordered
ordinary SymPy symbols and their assumptions, and primitive parameters. It does
not store trusted expanded arrays or execute mathematical expression strings.
Symbol subclasses such as `Dummy` remain supported for in-memory certificates but
are deliberately rejected by the self-contained JSON format.

## Reversible normalization

`factor_content` extracts a positive rational coefficient content and the
largest common monomial while preserving all signs:

```python
from triangle_method import factor_content

expression = sp.Rational(2, 3) * x**3 * y - sp.Rational(4, 9) * x**2 * y**2
polynomial = HomogeneousPolynomial.from_expr(expression, variables=(x, y, z))
normalization = factor_content(polynomial)

assert normalization.scalar == sp.Rational(2, 9)
assert normalization.monomial == (2, 1, 0)
assert sp.expand(normalization.reduced.to_sympy() - (3 * x - 2 * y)) == 0
assert normalization.restore() == polynomial
```

Normalization is explicit and reversible. Constructing a polynomial never
divides away a coefficient or monomial factor.

## Supported inputs

- Homogeneous polynomials in exactly three explicitly ordered variables.
- Integer and rational coefficients represented exactly.
- Negative coefficients, negative constants, omitted variables, and sparse
  coefficient dictionaries.
- SymPy `Poly` inputs whose generator order differs from the requested variable
  order.

The current package rejects floating or non-finite coefficients, irrational or
symbolic coefficients, undeclared variables, negative or fractional exponents,
nonhomogeneous inputs, and expressions with variable denominators. Strings and
expression parsing are not part of the current interface.

## Development

Keep the environment, caches, and temporary files inside the repository:

```bash
python3 -m venv .venv
mkdir -p .tmp .pip-cache
TMPDIR="$PWD/.tmp" .venv/bin/python -m pip install --cache-dir .pip-cache -e '.[dev]'

.venv/bin/python -m pytest
.venv/bin/ruff check .
.venv/bin/ruff format --check .
```

The current implementation is verified with Python 3.13.7, SymPy 1.14.0,
pytest 9.1.1, and Ruff 0.16.6.

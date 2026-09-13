# Triangle Method

Triangle Method is a Python package for working with exact coefficient triangles
of ternary homogeneous polynomials. It provides the mathematical data model,
coefficient-row conversion, reversible content normalization, and static SVG/HTML
rendering. It also supports manually authored certificates, direct exact recognition,
automatic fitting over a finite library of nonnegative components, and bounded exact
rational counterexample search. Every successful proof and counterexample is checked
again with exact arithmetic before it becomes a mathematical result.

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

## Automatic backend

`prove()` returns one of three structured outcomes: `PROVED` with a verified
decomposition certificate, `DISPROVED` with an exact negative rational point, or
`UNKNOWN` with diagnostics describing the finite work that was exhausted. Its input
is the validated polynomial model, which keeps expression parsing and variable order
explicit.

```python
from triangle_method import ProofStatus, prove

result = prove(polynomial)

assert result.status is ProofStatus.PROVED
assert result.method == "candidate_combination"
assert result.certificate is not None
assert result.verification is not None and result.verification.valid
assert result.verification.residual is not None
assert result.verification.residual.is_zero
```

The prover first recognizes zero, a positive monomial, one classic Schur component,
one exact homogeneous square, or a polynomial with nonnegative coefficients. A direct
match is preferred because it produces a smaller semantic certificate. Otherwise the
backend generates monomial, weighted binomial-square, and translated or power-dilated
Schur candidates and solves for nonnegative exact weights.

The combination solver uses a deterministic rational Phase I simplex. Its coefficient
matrix comes from the canonical coefficient triangle, and its result is accepted only
when all weights are exact and nonnegative, the matrix residual is exactly zero, and
the independent certificate verifier reconstructs the original target. Dependent
columns and degenerate supports are handled directly. Solver time, pivot count, and
candidate generation all have separate limits.

SciPy/HiGHS is an optional support proposer. It is lazy-loaded and
its floating output never serves as evidence. Install it with the `search` extra:

```bash
.venv/bin/python -m pip install -e '.[search]'
```

The exact backend is the default, so installing SciPy does not change the selected
certificate. Choose `SolverBackend.AUTO` or `SolverBackend.SCIPY_HIGHS` to request a
numerical support proposal followed by exact recovery. Search behavior is configured
through one immutable options object:

```python
from triangle_method import (
    CandidateGenerationLimits,
    CombinationSearchLimits,
    CounterexampleSearchLimits,
    ProofSearchOptions,
    SolverBackend,
)

options = ProofSearchOptions(
    candidate_limits=CandidateGenerationLimits(max_candidates=5_000),
    combination_limits=CombinationSearchLimits(
        max_seconds=10,
        max_pivots=20_000,
        backend=SolverBackend.EXACT,
    ),
    counterexample_limits=CounterexampleSearchLimits(
        max_denominator=16,
        max_points=20_000,
    ),
)
configured_result = prove(polynomial, options=options)
```

When the component search does not find a proof, the backend checks reduced rational
points on `x + y + z = 1`, including the boundary. Homogeneity justifies this
normalization for positive-degree inputs; constants receive a separate exact check.
For example:

```python
false_target = HomogeneousPolynomial.from_expr(
    x**2 + y**2 + z**2 - 4 * x * y,
    variables=(x, y, z),
)
false_result = prove(false_target)

assert false_result.status is ProofStatus.DISPROVED
assert false_result.counterexample is not None
assert false_result.counterexample.coordinates == (
    sp.Rational(1, 2),
    sp.Rational(1, 2),
    0,
)
assert false_result.counterexample.value == sp.Rational(-1, 2)
```

`UNKNOWN` means that the configured component cone and rational grid were
inconclusive. Numerical infeasibility, exact infeasibility within the finite candidate
library, generation interruption, and search limits cannot produce `DISPROVED`.

Exact square recognition uses rational square-free decomposition followed by a
complete exact re-square check. It has preflight limits of reduced degree 12, 128
nonzero terms, and 4096 bits per rational numerator or denominator. Larger squares
can still be supplied as manual certificates or found by a configured binomial-square
candidate search.

## Finite component candidates

`generate_candidates()` builds an inspectable finite library of nonnegative primitives
at the target degree. Candidate generation uses only the degree and ordered variables;
the target's coefficient signs and zero positions never prune the library.

```python
from triangle_method import (
    CandidateFamily,
    CandidateGenerationLimits,
    generate_candidates,
)

limits = CandidateGenerationLimits()
library = generate_candidates(polynomial, limits=limits)

assert library.metadata.complete
assert library.metadata.retained_count == 15
assert limits.square_ratios == (
    sp.Rational(1, 2),
    sp.Integer(1),
    sp.Integer(2),
)
assert (
    sum(
        candidate.family is CandidateFamily.BINOMIAL_SQUARE
        for candidate in library.candidates
    )
    == 9
)
```

Candidates appear in fixed family order: all coefficient-one monomials, bounded
weighted binomial squares, then translated or power-dilated cubic and quintic Schur
components. The default limits retain at most 10,000 unique columns, check a cooperative
five-second budget, bound ratio numerators and denominators by two, and bound each
unshifted square or Schur pattern at degree ten.

Each candidate retains its primitive object as exact mathematical provenance. Its full
coefficient column includes positional zeros and is reduced to primitive integers by a
positive scale only:

```text
component expansion = expansion_scale * candidate column
```

`candidate.weighted_component(column_weight)` converts an exact nonnegative column
weight back to the correct exact primitive weight. Positive proportional columns are
deduplicated without changing signs. Completion metadata distinguishes a fully
enumerated configured library from a candidate-count or time-limited prefix.
`attempted_count`, `retained_count`, `duplicate_count`, and `zero_count` expose the
work performed; `completed_families`, `interrupted_family`, and
`GenerationStopReason` locate an interruption. The time limit is cooperative: one
candidate expansion and full-column canonicalization can overrun it before the next
check.

`solve_candidate_combination()` fits a generated library directly when lower-level
control is useful. `complete=True` on a candidate library still refers only to the
configured finite family and never claims that the family contains every possible
nonnegative polynomial.

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
TMPDIR="$PWD/.tmp" .venv/bin/python -m pip install --cache-dir .pip-cache -e '.[dev,search]'

.venv/bin/python -m pytest
.venv/bin/ruff check .
.venv/bin/ruff format --check .
```

The current implementation is verified with Python 3.13.7, SymPy 1.14.0,
SciPy 1.18.1, pytest 9.1.1, and Ruff 0.16.6. SciPy is optional at runtime.

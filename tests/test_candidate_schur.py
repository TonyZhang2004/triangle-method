"""Schur-family acceptance tests for the finite candidate library."""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from collections.abc import Iterable
from itertools import chain
from pathlib import Path
from typing import Any, TypeAlias

import sympy as sp

from triangle_method import (
    CandidateFamily,
    CandidateGenerationLimits,
    ComponentCandidate,
    DecompositionCertificate,
    HomogeneousPolynomial,
    SchurComponent,
    coefficient_rows,
    generate_candidates,
    triangle_exponents,
    verify_certificate,
)

Variables: TypeAlias = tuple[sp.Symbol, sp.Symbol, sp.Symbol]
Exponent: TypeAlias = tuple[int, int, int]
SchurSignature: TypeAlias = tuple[int, int, Exponent]


def _generous_limits(*, max_base_degree: int = 10) -> CandidateGenerationLimits:
    """Keep acceptance runs complete while using only the unit square ratio."""

    return CandidateGenerationLimits(
        max_candidates=100_000,
        max_seconds=30.0,
        max_ratio_numerator=1,
        max_ratio_denominator=1,
        max_base_degree=max_base_degree,
    )


def _target_of_degree(degree: int, variables: Variables) -> HomogeneousPolynomial:
    """Create a sparse target whose degree controls coefficient-independent generation."""

    return HomogeneousPolynomial.from_terms(
        {(degree, 0, 0): 1},
        variables=variables,
    )


def _schur_candidates(
    candidates: Iterable[ComponentCandidate],
) -> tuple[ComponentCandidate, ...]:
    """Return Schur candidates without depending on private generator helpers."""

    return tuple(
        candidate
        for candidate in candidates
        if candidate.family is CandidateFamily.SCHUR
    )


def _schur_signature(candidate: ComponentCandidate) -> SchurSignature:
    """Describe an allowed variable-power Schur translation by ``(d, k, mu)``."""

    assert candidate.family is CandidateFamily.SCHUR
    assert type(candidate.component) is SchurComponent
    component = candidate.component
    power = component.arguments[0][0]
    assert power >= 1
    assert component.arguments == (
        (power, 0, 0),
        (0, power, 0),
        (0, 0, power),
    )
    return component.schur_degree, power, component.multiplier


def _flattened_coefficients(
    polynomial: HomogeneousPolynomial,
) -> tuple[sp.Rational, ...]:
    """Flatten exact coefficients in the public canonical triangle order."""

    return tuple(chain.from_iterable(coefficient_rows(polynomial)))


def _case_by_name(cases: tuple[Any, ...], name: str) -> Any:
    """Select one approved polynomial fixture by its stable descriptive name."""

    return next(case for case in cases if case.name == name)


def test_unshifted_cubic_and_quintic_schur_match_approved_fixtures(
    ternary_symbols: Variables,
    approved_polynomial_cases: tuple[Any, ...],
) -> None:
    """Include the classic degree-three and degree-five Schur expansions exactly."""

    for case_name, schur_degree in (("cubic_schur", 3), ("quintic_schur", 5)):
        case = _case_by_name(approved_polynomial_cases, case_name)
        target = HomogeneousPolynomial.from_expr(
            case.expression,
            variables=ternary_symbols,
        )
        library = generate_candidates(target, limits=_generous_limits())
        signature = (schur_degree, 1, (0, 0, 0))
        matches = tuple(
            candidate
            for candidate in _schur_candidates(library.candidates)
            if _schur_signature(candidate) == signature
        )

        assert library.metadata.complete, case_name
        assert len(matches) == 1, case_name
        assert matches[0].expand() == target, case_name


def test_all_cubic_shifts_reconstruct_the_quartic_schur_lift_and_ignore_target_zeros(
    ternary_symbols: Variables,
    approved_polynomial_cases: tuple[Any, ...],
) -> None:
    """Retain all three shifts, including terms that cancel at target-zero positions."""

    case = _case_by_name(approved_polynomial_cases, "quartic_schur_lift")
    target = HomogeneousPolynomial.from_expr(
        case.expression,
        variables=ternary_symbols,
    )
    library = generate_candidates(target, limits=_generous_limits())
    shifted = tuple(
        candidate
        for candidate in _schur_candidates(library.candidates)
        if _schur_signature(candidate)[0:2] == (3, 1)
    )

    expected_multipliers = tuple(chain.from_iterable(triangle_exponents(1)))
    assert tuple(_schur_signature(candidate)[2] for candidate in shifted) == (
        expected_multipliers
    )
    assert target.coefficient((3, 1, 0)) == 0
    assert {candidate.expand().coefficient((3, 1, 0)) for candidate in shifted} == {
        sp.Integer(-1),
        sp.Integer(0),
        sp.Integer(1),
    }

    certificate = DecompositionCertificate(
        target=target,
        terms=tuple(
            candidate.weighted_component(candidate.expansion_scale)
            for candidate in shifted
        ),
    )
    report = verify_certificate(certificate)

    assert report.valid, report.errors
    assert report.reconstructed == target
    assert report.residual is not None and report.residual.is_zero

    sparse_target = _target_of_degree(4, ternary_symbols)
    sparse_library = generate_candidates(sparse_target, limits=_generous_limits())
    assert sparse_library.candidates == library.candidates


def test_power_two_cubic_and_quintic_dilations_have_exact_coefficients(
    ternary_symbols: Variables,
) -> None:
    """Generate both approved theorem degrees after the substitution x,y,z -> x²,y²,z²."""

    expected_by_signature: dict[SchurSignature, dict[Exponent, int]] = {
        (3, 2, (0, 0, 0)): {
            (6, 0, 0): 1,
            (0, 6, 0): 1,
            (0, 0, 6): 1,
            (4, 2, 0): -1,
            (4, 0, 2): -1,
            (2, 4, 0): -1,
            (0, 4, 2): -1,
            (2, 0, 4): -1,
            (0, 2, 4): -1,
            (2, 2, 2): 3,
        },
        (5, 2, (0, 0, 0)): {
            (10, 0, 0): 1,
            (0, 10, 0): 1,
            (0, 0, 10): 1,
            (8, 2, 0): -1,
            (8, 0, 2): -1,
            (2, 8, 0): -1,
            (0, 8, 2): -1,
            (2, 0, 8): -1,
            (0, 2, 8): -1,
            (6, 2, 2): 1,
            (2, 6, 2): 1,
            (2, 2, 6): 1,
        },
    }

    for signature, expected_coefficients in expected_by_signature.items():
        target_degree = signature[0] * signature[1]
        library = generate_candidates(
            _target_of_degree(target_degree, ternary_symbols),
            limits=_generous_limits(),
        )
        matches = tuple(
            candidate
            for candidate in _schur_candidates(library.candidates)
            if _schur_signature(candidate) == signature
        )

        assert library.metadata.complete, signature
        assert len(matches) == 1, signature
        assert dict(matches[0].expand().coefficients) == {
            exponent: sp.Integer(coefficient)
            for exponent, coefficient in expected_coefficients.items()
        }


def test_translated_power_two_cubic_schur_has_the_expected_support(
    ternary_symbols: Variables,
) -> None:
    """Combine a power-two substitution with an independent monomial translation."""

    signature = (3, 2, (1, 0, 1))
    library = generate_candidates(
        _target_of_degree(8, ternary_symbols),
        limits=_generous_limits(),
    )
    candidate = next(
        candidate
        for candidate in _schur_candidates(library.candidates)
        if _schur_signature(candidate) == signature
    )

    assert dict(candidate.expand().coefficients) == {
        (7, 0, 1): sp.Integer(1),
        (1, 6, 1): sp.Integer(1),
        (1, 0, 7): sp.Integer(1),
        (5, 2, 1): sp.Integer(-1),
        (5, 0, 3): sp.Integer(-1),
        (3, 4, 1): sp.Integer(-1),
        (1, 4, 3): sp.Integer(-1),
        (3, 0, 5): sp.Integer(-1),
        (1, 2, 5): sp.Integer(-1),
        (3, 2, 3): sp.Integer(3),
    }


def test_schur_enumeration_uses_only_d3_d5_and_pure_variable_powers(
    ternary_symbols: Variables,
) -> None:
    """Exclude degree-four Schur and arbitrary equal-degree monomial substitutions."""

    for target_degree in (4, 8, 10):
        library = generate_candidates(
            _target_of_degree(target_degree, ternary_symbols),
            limits=_generous_limits(),
        )
        candidates = _schur_candidates(library.candidates)

        assert candidates
        assert {candidate.component.schur_degree for candidate in candidates} <= {3, 5}
        for candidate in candidates:
            _schur_signature(candidate)

    degree_four_signatures = {
        _schur_signature(candidate)
        for candidate in _schur_candidates(
            generate_candidates(
                _target_of_degree(4, ternary_symbols),
                limits=_generous_limits(),
            ).candidates
        )
    }
    assert (4, 1, (0, 0, 0)) not in degree_four_signatures


def test_schur_order_exact_columns_and_self_certificates_follow_target_order(
    ternary_symbols: Variables,
) -> None:
    """Keep deterministic proposal order, exact columns, and verifiable provenance."""

    x, y, z = ternary_symbols
    variables = (z, x, y)
    target = _target_of_degree(6, variables)
    library = generate_candidates(target, limits=_generous_limits())
    repeated = generate_candidates(target, limits=_generous_limits())
    candidates = _schur_candidates(library.candidates)
    expected_signatures = (
        *(
            (3, 1, multiplier)
            for multiplier in chain.from_iterable(triangle_exponents(3))
        ),
        (3, 2, (0, 0, 0)),
        *(
            (5, 1, multiplier)
            for multiplier in chain.from_iterable(triangle_exponents(1))
        ),
    )

    assert library.metadata.complete
    assert library.candidates == repeated.candidates
    assert tuple(_schur_signature(candidate) for candidate in candidates) == (
        expected_signatures
    )

    for candidate in candidates:
        expansion = candidate.expand()
        assert candidate.component.variables == variables
        assert candidate.component.degree == target.degree
        assert expansion.variables == variables
        assert expansion.degree == target.degree
        assert isinstance(candidate.expansion_scale, sp.Rational)
        assert candidate.expansion_scale > 0
        assert all(
            isinstance(coefficient, sp.Integer) for coefficient in candidate.column
        )
        assert not any(
            isinstance(value, (float, sp.Float))
            for value in (*candidate.column, candidate.expansion_scale)
        )
        assert _flattened_coefficients(expansion) == tuple(
            candidate.expansion_scale * coefficient for coefficient in candidate.column
        )

        certificate = DecompositionCertificate(
            target=expansion,
            terms=(candidate.weighted_component(candidate.expansion_scale),),
        )
        report = verify_certificate(certificate)
        assert report.valid, (_schur_signature(candidate), report.errors)


def test_required_schur_candidates_exist_for_every_approved_schur_fixture(
    ternary_symbols: Variables,
    approved_polynomial_cases: tuple[Any, ...],
) -> None:
    """Cover every Schur primitive used by the approved mixed-component identities."""

    required: dict[str, set[SchurSignature]] = {
        "cubic_schur": {(3, 1, (0, 0, 0))},
        "quintic_schur": {(5, 1, (0, 0, 0))},
        "quartic_schur_lift": {
            (3, 1, (1, 0, 0)),
            (3, 1, (0, 1, 0)),
            (3, 1, (0, 0, 1)),
        },
        "quintic_schur_plus_squares": {(5, 1, (0, 0, 0))},
    }

    for case_name, required_signatures in required.items():
        case = _case_by_name(approved_polynomial_cases, case_name)
        target = HomogeneousPolynomial.from_expr(
            case.expression,
            variables=ternary_symbols,
        )
        library = generate_candidates(target, limits=_generous_limits())
        actual_signatures = {
            _schur_signature(candidate)
            for candidate in _schur_candidates(library.candidates)
        }

        assert library.metadata.complete, case_name
        assert required_signatures <= actual_signatures, case_name


def test_candidate_generation_imports_no_numerical_solver_in_isolation(
    tmp_path: Path,
) -> None:
    """Keep finite Schur enumeration independent from SciPy and solver backends."""

    script = textwrap.dedent(
        """
        import sys
        import sympy as sp

        from triangle_method import (
            CandidateFamily,
            CandidateGenerationLimits,
            HomogeneousPolynomial,
            generate_candidates,
        )

        x, y, z = sp.symbols("x y z")
        target = HomogeneousPolynomial.from_expr(x**4, variables=(x, y, z))
        limits = CandidateGenerationLimits(
            max_candidates=10000,
            max_seconds=30.0,
            max_ratio_numerator=1,
            max_ratio_denominator=1,
            max_base_degree=10,
        )
        library = generate_candidates(target, limits=limits)
        shifts = tuple(
            candidate
            for candidate in library.candidates
            if candidate.family is CandidateFamily.SCHUR
        )
        assert library.metadata.complete
        assert len(shifts) == 3
        assert not any(
            name == "scipy" or name.startswith("scipy.") for name in sys.modules
        )
        """
    )
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"

    completed = subprocess.run(
        [sys.executable, "-I", "-c", script],
        cwd=tmp_path,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr

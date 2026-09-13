"""Budgeted nonnegative candidate fitting with exact rational certification."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import Enum
from fractions import Fraction
from math import isfinite
from time import monotonic as _monotonic
from typing import Any, TypeAlias

import sympy as sp

from .candidates import CandidateLibrary, _flatten_coefficients
from .normalization import _rational_content
from .results import ProofDiagnostic

ExactNumber: TypeAlias = Fraction
SparseRow: TypeAlias = dict[int, ExactNumber]


class SolverBackend(str, Enum):
    """Select the optional proposal backend used before exact feasibility search."""

    AUTO = "auto"
    EXACT = "exact"
    SCIPY_HIGHS = "scipy_highs"


class CombinationSearchStatus(str, Enum):
    """Describe the exact outcome of fitting one finite candidate library."""

    FEASIBLE = "FEASIBLE"
    INFEASIBLE_IN_LIBRARY = "INFEASIBLE_IN_LIBRARY"
    LIMIT_REACHED = "LIMIT_REACHED"
    ERROR = "ERROR"


def _validate_nonnegative_integer(value: object, *, name: str) -> int:
    """Return a nonnegative integer limit or reject booleans and other values."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a nonnegative integer")
    return value


def _validate_nonnegative_float(value: object, *, name: str) -> float:
    """Return a finite nonnegative floating limit or reject malformed values."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a nonnegative finite number")
    try:
        result = float(value)
    except (OverflowError, TypeError, ValueError) as error:
        raise ValueError(f"{name} must be a nonnegative finite number") from error
    if not isfinite(result) or result < 0:
        raise ValueError(f"{name} must be a nonnegative finite number")
    return result


@dataclass(frozen=True, slots=True, kw_only=True)
class CombinationSearchLimits:
    """Bound numerical support recovery and the authoritative exact search."""

    max_seconds: float = 5.0
    max_pivots: int = 10_000
    max_recovery_candidates: int = 256
    numerical_tolerance: float = 1e-9
    backend: SolverBackend = SolverBackend.EXACT

    def __post_init__(self) -> None:
        """Validate finite operational limits and a supported backend choice."""
        object.__setattr__(
            self,
            "max_seconds",
            _validate_nonnegative_float(self.max_seconds, name="max_seconds"),
        )
        _validate_nonnegative_integer(self.max_pivots, name="max_pivots")
        _validate_nonnegative_integer(
            self.max_recovery_candidates,
            name="max_recovery_candidates",
        )
        tolerance = _validate_nonnegative_float(
            self.numerical_tolerance,
            name="numerical_tolerance",
        )
        if tolerance == 0:
            raise ValueError("numerical_tolerance must be positive")
        object.__setattr__(self, "numerical_tolerance", tolerance)
        if not isinstance(self.backend, SolverBackend):
            raise ValueError("backend must be a SolverBackend")


@dataclass(frozen=True, slots=True, kw_only=True)
class CombinationSearchResult:
    """Store exact candidate weights or a structured finite-search failure."""

    status: CombinationSearchStatus
    weights: tuple[sp.Rational, ...]
    backend: SolverBackend
    diagnostics: tuple[ProofDiagnostic, ...]
    pivots: int
    attempted_supports: int
    exact_residual: tuple[sp.Rational, ...] | None

    def __post_init__(self) -> None:
        """Freeze result sequences and enforce evidence appropriate to its status."""
        if not isinstance(self.status, CombinationSearchStatus):
            raise ValueError("status must be a CombinationSearchStatus")
        if (
            not isinstance(self.backend, SolverBackend)
            or self.backend is SolverBackend.AUTO
        ):
            raise ValueError("result backend must identify an actual solver backend")

        if isinstance(self.weights, (str, bytes)):
            raise ValueError("weights must contain exact rational values")
        try:
            weights = tuple(self.weights)
        except TypeError as error:
            raise ValueError(
                "weights must be an iterable of exact rational values"
            ) from error
        if any(not isinstance(weight, sp.Rational) for weight in weights):
            raise ValueError("weights must contain exact rational values")
        if any(weight < 0 for weight in weights):
            raise ValueError("weights must be nonnegative")
        object.__setattr__(self, "weights", weights)

        if isinstance(self.diagnostics, (str, bytes)):
            raise ValueError("diagnostics must contain ProofDiagnostic objects")
        try:
            diagnostics = tuple(self.diagnostics)
        except TypeError as error:
            raise ValueError(
                "diagnostics must be an iterable of ProofDiagnostic objects"
            ) from error
        if not diagnostics or any(
            not isinstance(diagnostic, ProofDiagnostic) for diagnostic in diagnostics
        ):
            raise ValueError("diagnostics must contain ProofDiagnostic objects")
        object.__setattr__(self, "diagnostics", diagnostics)

        _validate_nonnegative_integer(self.pivots, name="pivots")
        _validate_nonnegative_integer(
            self.attempted_supports,
            name="attempted_supports",
        )

        residual = self.exact_residual
        if residual is not None:
            if isinstance(residual, (str, bytes)):
                raise ValueError("exact_residual must contain exact rational values")
            try:
                residual = tuple(residual)
            except TypeError as error:
                raise ValueError(
                    "exact_residual must be an iterable of exact rational values"
                ) from error
            if any(not isinstance(value, sp.Rational) for value in residual):
                raise ValueError("exact_residual must contain exact rational values")
            object.__setattr__(self, "exact_residual", residual)

        if self.status is CombinationSearchStatus.FEASIBLE:
            if not residual or any(residual):
                raise ValueError(
                    "a feasible result requires a nonempty exact zero residual"
                )
        elif weights or residual is not None:
            raise ValueError("an unsuccessful result cannot contain proof weights")


class _ExactAttemptStatus(str, Enum):
    """Describe one internal exact feasibility attempt."""

    FEASIBLE = "feasible"
    INFEASIBLE = "infeasible"
    ERROR = "error"


class _NumericalProposalStatus(str, Enum):
    """Describe the optional numerical backend without assigning proof meaning."""

    PROPOSED = "proposed"
    UNAVAILABLE = "unavailable"
    INFEASIBLE = "infeasible"
    LIMIT_REACHED = "limit_reached"
    ERROR = "error"


class _SearchLimitReached(RuntimeError):
    """Stop exact work when the cooperative wall-clock budget is exhausted."""


class _PivotLimitReached(RuntimeError):
    """Stop exact work before exceeding the configured pivot count."""


@dataclass(slots=True, kw_only=True)
class _SearchBudget:
    """Share time and pivot limits across support recovery and full fallback."""

    limits: CombinationSearchLimits
    started_at: float
    pivots: int = 0

    def require_time(self) -> None:
        """Raise when the cooperative search deadline has been reached."""
        if _monotonic() - self.started_at >= self.limits.max_seconds:
            raise _SearchLimitReached

    def remaining_seconds(self) -> float:
        """Return the nonnegative wall-clock budget remaining for a proposal."""
        return max(
            0.0,
            self.limits.max_seconds - (_monotonic() - self.started_at),
        )

    def begin_pivot(self) -> None:
        """Reserve one exact pivot after checking both operational budgets."""
        self.require_time()
        if self.pivots >= self.limits.max_pivots:
            raise _PivotLimitReached
        self.pivots += 1


@dataclass(frozen=True, slots=True)
class _ExactAttempt:
    """Return one exact phase-I outcome in local support coordinates."""

    status: _ExactAttemptStatus
    weights: tuple[ExactNumber, ...] = ()


@dataclass(frozen=True, slots=True)
class _NumericalProposal:
    """Return floating weights solely for deterministic exact support selection."""

    status: _NumericalProposalStatus
    values: tuple[float, ...] = ()


def _fraction(value: sp.Rational) -> Fraction:
    """Convert one exact SymPy rational to the standard-library exact type."""
    return Fraction(int(value.p), int(value.q))


def _sympy_rational(value: Fraction) -> sp.Rational:
    """Convert one standard-library fraction to the package's exact scalar type."""
    return sp.Rational(value.numerator, value.denominator)


def _set_sparse_value(row: SparseRow, column: int, value: Fraction) -> None:
    """Set one sparse tableau entry while removing exact zeros."""
    if value:
        row[column] = value
    else:
        row.pop(column, None)


def _initial_phase_one_tableau(
    library: CandidateLibrary,
    normalized_target: tuple[sp.Integer, ...],
    support: tuple[int, ...],
    budget: _SearchBudget,
) -> tuple[list[SparseRow], list[Fraction], list[int], SparseRow, Fraction]:
    """Build a feasible artificial-variable basis for one exact support."""
    row_count = len(normalized_target)
    candidate_count = len(support)
    rows: list[SparseRow] = []
    right_sides: list[Fraction] = []
    operation_count = 0

    for row_index, target_value in enumerate(normalized_target):
        sign = -1 if target_value < 0 else 1
        row: SparseRow = {}
        for local_column, candidate_index in enumerate(support):
            coefficient = sign * int(
                library.candidates[candidate_index].column[row_index]
            )
            if coefficient:
                row[local_column] = Fraction(coefficient)
            operation_count += 1
            if operation_count % 2048 == 0:
                budget.require_time()
        row[candidate_count + row_index] = Fraction(1)
        rows.append(row)
        right_sides.append(Fraction(sign * int(target_value)))

    basis = [candidate_count + row_index for row_index in range(row_count)]
    reduced_costs: SparseRow = {}
    for candidate_index in range(candidate_count):
        reduced_cost = Fraction(0)
        for row in rows:
            reduced_cost -= row.get(candidate_index, Fraction(0))
            operation_count += 1
            if operation_count % 2048 == 0:
                budget.require_time()
        if reduced_cost:
            reduced_costs[candidate_index] = reduced_cost
    objective = sum(right_sides, Fraction(0))
    return rows, right_sides, basis, reduced_costs, objective


def _choose_entering_column(
    reduced_costs: SparseRow,
    basis: set[int],
) -> int | None:
    """Choose the smallest-index improving nonbasic variable by Bland's rule."""
    entering = (
        column
        for column, reduced_cost in reduced_costs.items()
        if reduced_cost < 0 and column not in basis
    )
    return min(entering, default=None)


def _choose_leaving_row(
    rows: Sequence[SparseRow],
    right_sides: Sequence[Fraction],
    basis: Sequence[int],
    entering: int,
) -> int | None:
    """Use the exact minimum-ratio test with Bland's tie breaking."""
    eligible = [
        row_index
        for row_index, row in enumerate(rows)
        if row.get(entering, Fraction(0)) > 0
    ]
    if not eligible:
        return None
    minimum_ratio = min(
        right_sides[row_index] / rows[row_index][entering] for row_index in eligible
    )
    tied = [
        row_index
        for row_index in eligible
        if right_sides[row_index] / rows[row_index][entering] == minimum_ratio
    ]
    return min(tied, key=lambda row_index: basis[row_index])


def _pivot_phase_one_tableau(
    rows: list[SparseRow],
    right_sides: list[Fraction],
    basis: list[int],
    reduced_costs: SparseRow,
    objective: Fraction,
    *,
    entering: int,
    leaving_row: int,
    budget: _SearchBudget,
) -> Fraction:
    """Pivot one exact sparse tableau and return its updated objective value."""
    budget.begin_pivot()
    pivot = rows[leaving_row][entering]
    pivot_row: SparseRow = {}
    operation_count = 0
    for column, value in rows[leaving_row].items():
        pivot_row[column] = value / pivot
        operation_count += 1
        if operation_count % 2048 == 0:
            budget.require_time()
    pivot_right_side = right_sides[leaving_row] / pivot
    rows[leaving_row] = pivot_row
    right_sides[leaving_row] = pivot_right_side

    for row_index, row in enumerate(rows):
        if row_index == leaving_row:
            continue
        factor = row.get(entering, Fraction(0))
        if not factor:
            continue
        for column, pivot_value in pivot_row.items():
            updated = row.get(column, Fraction(0)) - factor * pivot_value
            _set_sparse_value(row, column, updated)
            operation_count += 1
            if operation_count % 2048 == 0:
                budget.require_time()
        right_sides[row_index] -= factor * pivot_right_side

    objective_factor = reduced_costs.get(entering, Fraction(0))
    objective += objective_factor * pivot_right_side
    for column, pivot_value in pivot_row.items():
        updated = reduced_costs.get(column, Fraction(0)) - (
            objective_factor * pivot_value
        )
        _set_sparse_value(reduced_costs, column, updated)
        operation_count += 1
        if operation_count % 2048 == 0:
            budget.require_time()
    basis[leaving_row] = entering
    return objective


def _validate_local_solution(
    library: CandidateLibrary,
    normalized_target: tuple[sp.Integer, ...],
    support: tuple[int, ...],
    weights: tuple[Fraction, ...],
    budget: _SearchBudget,
) -> bool:
    """Check one nonnegative local solution against every original exact equation."""
    if len(weights) != len(support) or any(weight < 0 for weight in weights):
        return False
    operation_count = 0
    for row_index, target_value in enumerate(normalized_target):
        reconstructed = Fraction(0)
        for local_column, candidate_index in enumerate(support):
            reconstructed += weights[local_column] * int(
                library.candidates[candidate_index].column[row_index]
            )
            operation_count += 1
            if operation_count % 2048 == 0:
                budget.require_time()
        if reconstructed != Fraction(int(target_value)):
            return False
    return True


def _exact_phase_one(
    library: CandidateLibrary,
    normalized_target: tuple[sp.Integer, ...],
    support: tuple[int, ...],
    budget: _SearchBudget,
) -> _ExactAttempt:
    """Solve one support exactly by a Bland-rule phase-I simplex tableau."""
    budget.require_time()
    if not support:
        if all(value == 0 for value in normalized_target):
            return _ExactAttempt(_ExactAttemptStatus.FEASIBLE, ())
        return _ExactAttempt(_ExactAttemptStatus.INFEASIBLE)

    rows, right_sides, basis, reduced_costs, objective = _initial_phase_one_tableau(
        library,
        normalized_target,
        support,
        budget,
    )
    candidate_count = len(support)
    basis_set = set(basis)

    while True:
        if objective == 0:
            break
        budget.require_time()
        entering = _choose_entering_column(reduced_costs, basis_set)
        if entering is None:
            break
        leaving_row = _choose_leaving_row(
            rows,
            right_sides,
            basis,
            entering,
        )
        if leaving_row is None:
            return _ExactAttempt(_ExactAttemptStatus.ERROR)
        leaving_variable = basis[leaving_row]
        objective = _pivot_phase_one_tableau(
            rows,
            right_sides,
            basis,
            reduced_costs,
            objective,
            entering=entering,
            leaving_row=leaving_row,
            budget=budget,
        )
        basis_set.remove(leaving_variable)
        basis_set.add(entering)

    if any(right_side < 0 for right_side in right_sides):
        return _ExactAttempt(_ExactAttemptStatus.ERROR)
    artificial_objective = sum(
        (
            right_sides[row_index]
            for row_index, basic_variable in enumerate(basis)
            if basic_variable >= candidate_count
        ),
        Fraction(0),
    )
    if artificial_objective != objective or objective < 0:
        return _ExactAttempt(_ExactAttemptStatus.ERROR)
    if objective > 0:
        return _ExactAttempt(_ExactAttemptStatus.INFEASIBLE)

    weights = [Fraction(0) for _ in support]
    for row_index, basic_variable in enumerate(basis):
        if basic_variable < candidate_count:
            weights[basic_variable] = right_sides[row_index]
    frozen_weights = tuple(weights)
    if not _validate_local_solution(
        library,
        normalized_target,
        support,
        frozen_weights,
        budget,
    ):
        return _ExactAttempt(_ExactAttemptStatus.ERROR)
    return _ExactAttempt(_ExactAttemptStatus.FEASIBLE, frozen_weights)


def _load_scipy_linprog() -> Callable[..., Any] | None:
    """Load SciPy's HiGHS adapter lazily when the optional dependency is usable."""
    try:
        from scipy.optimize import linprog
    except Exception:
        return None
    return linprog


def _scaled_float_system(
    library: CandidateLibrary,
    target: tuple[sp.Rational, ...],
) -> tuple[list[list[float]], list[float]]:
    """Row-scale the exact system before bounded conversion to binary floats."""
    matrix: list[list[float]] = []
    right_side: list[float] = []
    for row_index, target_value in enumerate(target):
        row_values = tuple(
            candidate.column[row_index] for candidate in library.candidates
        )
        scale = max(
            (sp.S.One, abs(target_value), *(abs(value) for value in row_values))
        )
        matrix.append([float(sp.Rational(value) / scale) for value in row_values])
        right_side.append(float(target_value / scale))
    return matrix, right_side


def _scipy_highs_proposal(
    library: CandidateLibrary,
    target: tuple[sp.Rational, ...],
    *,
    max_seconds: float,
    tolerance: float,
) -> _NumericalProposal:
    """Ask SciPy/HiGHS for a floating support proposal without trusting feasibility."""
    if max_seconds <= 0:
        return _NumericalProposal(_NumericalProposalStatus.LIMIT_REACHED)
    linprog = _load_scipy_linprog()
    if linprog is None:
        return _NumericalProposal(_NumericalProposalStatus.UNAVAILABLE)

    candidate_count = len(library.candidates)
    matrix, right_side = _scaled_float_system(library, target)
    objective = [
        1.0 + (candidate_index / max(1, candidate_count)) * 1e-6
        for candidate_index in range(candidate_count)
    ]
    try:
        proposal = linprog(
            objective,
            A_eq=matrix,
            b_eq=right_side,
            bounds=(0, None),
            method="highs-ds",
            options={"presolve": True, "time_limit": max_seconds},
        )
    except Exception:
        return _NumericalProposal(_NumericalProposalStatus.ERROR)

    status = getattr(proposal, "status", None)
    if status == 1:
        return _NumericalProposal(_NumericalProposalStatus.LIMIT_REACHED)
    if status == 2:
        return _NumericalProposal(_NumericalProposalStatus.INFEASIBLE)
    if status != 0 or getattr(proposal, "success", False) is not True:
        return _NumericalProposal(_NumericalProposalStatus.ERROR)

    raw_values = getattr(proposal, "x", None)
    if raw_values is None:
        return _NumericalProposal(_NumericalProposalStatus.ERROR)
    try:
        values = tuple(float(value) for value in raw_values)
    except (TypeError, ValueError, OverflowError):
        return _NumericalProposal(_NumericalProposalStatus.ERROR)
    if len(values) != candidate_count or any(not isfinite(value) for value in values):
        return _NumericalProposal(_NumericalProposalStatus.ERROR)
    magnitude = max((1.0, *(abs(value) for value in values)))
    if any(value < -(tolerance * magnitude) for value in values):
        return _NumericalProposal(_NumericalProposalStatus.ERROR)
    return _NumericalProposal(_NumericalProposalStatus.PROPOSED, values)


def _proposal_supports(
    values: tuple[float, ...],
    limits: CombinationSearchLimits,
) -> tuple[tuple[int, ...], ...]:
    """Return strong then near-zero-expanded supports in canonical column order."""
    if limits.max_recovery_candidates == 0 or not values:
        return ()
    magnitude = max((1.0, *(abs(value) for value in values)))
    threshold = limits.numerical_tolerance * magnitude
    ranked = tuple(
        sorted(range(len(values)), key=lambda index: (-abs(values[index]), index))
    )
    strong_ranked = tuple(index for index in ranked if values[index] > threshold)
    cap = limits.max_recovery_candidates
    strong = tuple(sorted(strong_ranked[:cap]))
    expanded = tuple(sorted(ranked[:cap]))
    supports: list[tuple[int, ...]] = []
    for support in (strong, expanded):
        if support and support not in supports:
            supports.append(support)
    return tuple(supports)


def _diagnostic(code: str, message: str) -> ProofDiagnostic:
    """Build one stable proof diagnostic for the combination search layer."""
    return ProofDiagnostic(code=code, message=message)


def _full_weights(
    candidate_count: int,
    support: tuple[int, ...],
    local_weights: tuple[Fraction, ...],
    scale: sp.Rational,
) -> tuple[sp.Rational, ...]:
    """Restore target content and expand local weights to every library column."""
    weights = [sp.S.Zero for _ in range(candidate_count)]
    for local_column, candidate_index in enumerate(support):
        weights[candidate_index] = scale * _sympy_rational(local_weights[local_column])
    return tuple(weights)


def _exact_residual(
    library: CandidateLibrary,
    target: tuple[sp.Rational, ...],
    weights: tuple[sp.Rational, ...],
    budget: _SearchBudget,
) -> tuple[sp.Rational, ...]:
    """Return target minus the exactly reconstructed candidate-column vector."""
    residual: list[sp.Rational] = []
    operation_count = 0
    selected = tuple(
        (weight, library.candidates[candidate_index])
        for candidate_index, weight in enumerate(weights)
        if weight
    )
    for row_index, target_value in enumerate(target):
        reconstructed = sp.S.Zero
        for weight, candidate in selected:
            reconstructed += weight * candidate.column[row_index]
            operation_count += 1
            if operation_count % 2048 == 0:
                budget.require_time()
        residual.append(target_value - reconstructed)
    return tuple(residual)


def _feasible_result(
    library: CandidateLibrary,
    target: tuple[sp.Rational, ...],
    support: tuple[int, ...],
    attempt: _ExactAttempt,
    scale: sp.Rational,
    backend: SolverBackend,
    diagnostics: list[ProofDiagnostic],
    budget: _SearchBudget,
    attempted_supports: int,
) -> CombinationSearchResult | None:
    """Build a feasible public result only after a second full exact residual check."""
    weights = _full_weights(
        len(library.candidates),
        support,
        attempt.weights,
        scale,
    )
    residual = _exact_residual(library, target, weights, budget)
    if any(residual) or any(weight < 0 for weight in weights):
        return None
    diagnostics.append(
        _diagnostic(
            "combination.matched",
            "The exact candidate combination reconstructs the target.",
        )
    )
    return CombinationSearchResult(
        status=CombinationSearchStatus.FEASIBLE,
        weights=weights,
        backend=backend,
        diagnostics=tuple(diagnostics),
        pivots=budget.pivots,
        attempted_supports=attempted_supports,
        exact_residual=residual,
    )


def _unsuccessful_result(
    status: CombinationSearchStatus,
    backend: SolverBackend,
    diagnostics: list[ProofDiagnostic],
    budget: _SearchBudget,
    attempted_supports: int,
) -> CombinationSearchResult:
    """Build one public result without proof weights or a claimed exact identity."""
    return CombinationSearchResult(
        status=status,
        weights=(),
        backend=backend,
        diagnostics=tuple(diagnostics),
        pivots=budget.pivots,
        attempted_supports=attempted_supports,
        exact_residual=None,
    )


def solve_candidate_combination(
    library: CandidateLibrary,
    limits: CombinationSearchLimits | None = None,
) -> CombinationSearchResult:
    """Fit nonnegative candidate weights and accept only an exact rational identity."""
    if type(library) is not CandidateLibrary:
        raise TypeError("library must be a CandidateLibrary")
    if limits is None:
        limits = CombinationSearchLimits()
    elif type(limits) is not CombinationSearchLimits:
        raise TypeError("limits must be a CombinationSearchLimits object or None")

    budget = _SearchBudget(limits=limits, started_at=_monotonic())
    diagnostics: list[ProofDiagnostic] = []
    attempted_supports = 0
    target = _flatten_coefficients(library.target)
    candidate_count = len(library.candidates)

    if all(value == 0 for value in target):
        residual = tuple(sp.S.Zero for _ in target)
        diagnostics.append(
            _diagnostic(
                "combination.matched",
                "The zero target has the empty exact candidate combination.",
            )
        )
        return CombinationSearchResult(
            status=CombinationSearchStatus.FEASIBLE,
            weights=tuple(sp.S.Zero for _ in library.candidates),
            backend=SolverBackend.EXACT,
            diagnostics=tuple(diagnostics),
            pivots=0,
            attempted_supports=0,
            exact_residual=residual,
        )

    if candidate_count == 0:
        diagnostics.append(
            _diagnostic(
                "combination.exact.infeasible_in_library",
                "The nonzero target is outside the empty generated candidate cone.",
            )
        )
        return _unsuccessful_result(
            CombinationSearchStatus.INFEASIBLE_IN_LIBRARY,
            SolverBackend.EXACT,
            diagnostics,
            budget,
            attempted_supports,
        )

    content = _rational_content(target)
    normalized_target = tuple(value / content for value in target)
    if any(not isinstance(value, sp.Integer) for value in normalized_target):
        diagnostics.append(
            _diagnostic(
                "combination.exact.error",
                "Target content normalization did not produce exact integers.",
            )
        )
        return _unsuccessful_result(
            CombinationSearchStatus.ERROR,
            SolverBackend.EXACT,
            diagnostics,
            budget,
            attempted_supports,
        )

    supports: list[tuple[tuple[int, ...], SolverBackend, str]] = []
    if limits.backend in (SolverBackend.AUTO, SolverBackend.SCIPY_HIGHS):
        proposal_seconds = min(
            1.0,
            budget.remaining_seconds() / 4.0,
        )
        proposal = _scipy_highs_proposal(
            library,
            target,
            max_seconds=proposal_seconds,
            tolerance=limits.numerical_tolerance,
        )
        proposal_diagnostics = {
            _NumericalProposalStatus.UNAVAILABLE: (
                "combination.numeric.unavailable",
                "SciPy/HiGHS is unavailable; exact search will continue.",
            ),
            _NumericalProposalStatus.INFEASIBLE: (
                "combination.numeric.infeasible",
                "The numerical backend reported infeasibility; exact search will decide the generated cone.",
            ),
            _NumericalProposalStatus.LIMIT_REACHED: (
                "combination.numeric.time_limit",
                "The numerical proposal reached its time limit; exact search will continue if time remains.",
            ),
            _NumericalProposalStatus.ERROR: (
                "combination.numeric.error",
                "The numerical proposal failed; exact search will continue.",
            ),
        }
        if proposal.status is _NumericalProposalStatus.PROPOSED:
            diagnostics.append(
                _diagnostic(
                    "combination.numeric.proposed_support",
                    "SciPy/HiGHS supplied a support proposal for exact recovery.",
                )
            )
            proposed_supports = _proposal_supports(proposal.values, limits)
            for support_index, support in enumerate(proposed_supports):
                if len(support) == candidate_count:
                    failure_code = ""
                else:
                    failure_code = (
                        "combination.recovery.support_failed"
                        if support_index == 0
                        else "combination.recovery.expanded_support_failed"
                    )
                supports.append((support, SolverBackend.SCIPY_HIGHS, failure_code))
        else:
            code, message = proposal_diagnostics[proposal.status]
            diagnostics.append(_diagnostic(code, message))

    full_support = tuple(range(candidate_count))
    if all(support != full_support for support, _, _ in supports):
        supports.append((full_support, SolverBackend.EXACT, ""))

    last_backend = SolverBackend.EXACT
    for support, backend, failure_code in supports:
        last_backend = backend
        try:
            budget.require_time()
            attempted_supports += 1
            attempt = _exact_phase_one(
                library,
                normalized_target,  # type: ignore[arg-type]
                support,
                budget,
            )
        except _SearchLimitReached:
            diagnostics.append(
                _diagnostic(
                    "combination.exact.time_limit",
                    "The exact combination search reached its time limit.",
                )
            )
            return _unsuccessful_result(
                CombinationSearchStatus.LIMIT_REACHED,
                last_backend,
                diagnostics,
                budget,
                attempted_supports,
            )
        except _PivotLimitReached:
            diagnostics.append(
                _diagnostic(
                    "combination.exact.pivot_limit",
                    "The exact combination search reached its pivot limit.",
                )
            )
            return _unsuccessful_result(
                CombinationSearchStatus.LIMIT_REACHED,
                last_backend,
                diagnostics,
                budget,
                attempted_supports,
            )

        if attempt.status is _ExactAttemptStatus.FEASIBLE:
            try:
                result = _feasible_result(
                    library,
                    target,
                    support,
                    attempt,
                    content,
                    backend,
                    diagnostics,
                    budget,
                    attempted_supports,
                )
            except _SearchLimitReached:
                diagnostics.append(
                    _diagnostic(
                        "combination.exact.time_limit",
                        "The exact combination search reached its time limit.",
                    )
                )
                return _unsuccessful_result(
                    CombinationSearchStatus.LIMIT_REACHED,
                    backend,
                    diagnostics,
                    budget,
                    attempted_supports,
                )
            if result is not None:
                return result
            attempt = _ExactAttempt(_ExactAttemptStatus.ERROR)

        if attempt.status is _ExactAttemptStatus.ERROR:
            if failure_code:
                diagnostics.append(
                    _diagnostic(
                        failure_code,
                        "The proposed support could not be recovered as a valid exact solution.",
                    )
                )
                continue
            diagnostics.append(
                _diagnostic(
                    "combination.exact.error",
                    "The exact solver rejected an internally inconsistent result.",
                )
            )
            return _unsuccessful_result(
                CombinationSearchStatus.ERROR,
                backend,
                diagnostics,
                budget,
                attempted_supports,
            )

        if failure_code:
            diagnostics.append(
                _diagnostic(
                    failure_code,
                    "The proposed support was not feasible over the exact rationals.",
                )
            )
            continue

        diagnostics.append(
            _diagnostic(
                "combination.exact.infeasible_in_library",
                "The target is outside the generated finite candidate cone.",
            )
        )
        return _unsuccessful_result(
            CombinationSearchStatus.INFEASIBLE_IN_LIBRARY,
            SolverBackend.EXACT,
            diagnostics,
            budget,
            attempted_supports,
        )

    diagnostics.append(
        _diagnostic(
            "combination.exact.error",
            "The combination search ended without an exact outcome.",
        )
    )
    return _unsuccessful_result(
        CombinationSearchStatus.ERROR,
        last_backend,
        diagnostics,
        budget,
        attempted_supports,
    )

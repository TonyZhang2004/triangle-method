"""Public orchestration for exact Triangle Method proofs and counterexamples."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from .candidates import CandidateGenerationLimits, CandidateLibrary, generate_candidates
from .certificate import DecompositionCertificate
from .counterexamples import (
    Counterexample,
    CounterexampleSearchError,
    CounterexampleSearchLimits,
    search_counterexample,
)
from .errors import (
    CandidateGenerationError,
    CertificateInputError,
    PolynomialInputError,
)
from .normalization import factor_content
from .polynomial import HomogeneousPolynomial
from .recognition import (
    RecognitionCandidate,
    recognize_classic_schur,
    recognize_exact_square,
    recognize_nonnegative_coefficients,
    recognize_positive_monomial,
    recognize_zero,
)
from .results import ProofDiagnostic, ProofResult, ProofStatus
from .search import (
    CombinationSearchLimits,
    CombinationSearchStatus,
    solve_candidate_combination,
)
from .verify import VerificationReport, verify_certificate


@dataclass(frozen=True, slots=True, kw_only=True)
class ProofSearchOptions:
    """Configure candidate fitting and bounded exact counterexample discovery."""

    candidate_limits: CandidateGenerationLimits = field(
        default_factory=CandidateGenerationLimits
    )
    combination_limits: CombinationSearchLimits = field(
        default_factory=CombinationSearchLimits
    )
    counterexample_limits: CounterexampleSearchLimits = field(
        default_factory=CounterexampleSearchLimits
    )
    enable_combination_search: bool = True
    enable_counterexample_search: bool = True

    def __post_init__(self) -> None:
        """Require immutable typed sub-options and explicit boolean phase switches."""
        expected_types = (
            ("candidate_limits", self.candidate_limits, CandidateGenerationLimits),
            ("combination_limits", self.combination_limits, CombinationSearchLimits),
            (
                "counterexample_limits",
                self.counterexample_limits,
                CounterexampleSearchLimits,
            ),
        )
        for field_name, value, expected_type in expected_types:
            if type(value) is not expected_type:
                raise ValueError(
                    f"{field_name} must be a {expected_type.__name__} object"
                )
        for field_name, value in (
            ("enable_combination_search", self.enable_combination_search),
            ("enable_counterexample_search", self.enable_counterexample_search),
        ):
            if type(value) is not bool:
                raise ValueError(f"{field_name} must be a boolean")


def _unknown_result(
    target: HomogeneousPolynomial,
    diagnostics: Iterable[ProofDiagnostic],
) -> ProofResult:
    """Build an inconclusive result with immutable diagnostics and no proof objects."""
    return ProofResult(
        target=target,
        status=ProofStatus.UNKNOWN,
        method=None,
        certificate=None,
        verification=None,
        diagnostics=tuple(diagnostics),
    )


def _verification_failure(
    target: HomogeneousPolynomial,
    diagnostics: tuple[ProofDiagnostic, ...],
    detail: str,
) -> ProofResult:
    """Return UNKNOWN when an internal proposal cannot pass the certificate boundary."""
    cleaned_detail = detail.strip() or "no additional detail"
    failure = ProofDiagnostic(
        code="verification.failed",
        message=(
            "A proof stage proposed a match, but independent certificate "
            f"verification failed: {cleaned_detail}"
        ),
    )
    return _unknown_result(target, (*diagnostics, failure))


def _verify_candidate(
    target: HomogeneousPolynomial,
    candidate: RecognitionCandidate,
    diagnostics: tuple[ProofDiagnostic, ...],
) -> ProofResult:
    """Certify one proposed term sequence and return PROVED only for an exact match."""
    try:
        certificate = DecompositionCertificate(
            target=target,
            terms=candidate.terms,
        )
        report = verify_certificate(certificate)
    except CertificateInputError as error:
        return _verification_failure(target, diagnostics, str(error))

    if type(report) is not VerificationReport:
        return _verification_failure(
            target,
            diagnostics,
            "the verifier returned an unsupported report object",
        )

    identity_is_exact = (
        report.valid is True
        and report.issues == ()
        and report.reconstructed == target
        and report.residual is not None
        and report.residual.is_zero
    )
    if not identity_is_exact:
        issue_codes = ", ".join(issue.code for issue in report.issues)
        detail = (
            issue_codes or "the verification report did not contain an exact identity"
        )
        return _verification_failure(target, diagnostics, detail)

    passed = ProofDiagnostic(
        code="verification.passed",
        message="The independent exact verifier accepted the proposed certificate.",
    )
    try:
        return ProofResult(
            target=target,
            status=ProofStatus.PROVED,
            method=candidate.method,
            certificate=certificate,
            verification=report,
            diagnostics=(*diagnostics, passed),
        )
    except ValueError as error:
        return _verification_failure(target, diagnostics, str(error))


def _candidate_library_diagnostics(
    library: CandidateLibrary,
) -> tuple[ProofDiagnostic, ...]:
    """Describe an interrupted finite enumeration without assigning proof meaning."""
    if library.metadata.complete:
        return ()
    stop_reason = library.metadata.stop_reason
    if stop_reason is None:
        return (
            ProofDiagnostic(
                code="candidates.error",
                message="Candidate generation stopped without a recorded reason.",
            ),
        )
    return (
        ProofDiagnostic(
            code=f"candidates.incomplete.{stop_reason.value}",
            message=(
                "Candidate generation retained "
                f"{library.metadata.retained_count} columns before reaching its "
                f"{stop_reason.value.replace('_', ' ')}."
            ),
        ),
    )


def _search_candidate_combination(
    target: HomogeneousPolynomial,
    options: ProofSearchOptions,
    diagnostics: list[ProofDiagnostic],
) -> ProofResult | None:
    """Search a finite component cone and verify any exact weighted-term proposal."""
    try:
        library = generate_candidates(target, limits=options.candidate_limits)
    except CandidateGenerationError as error:
        diagnostics.append(
            ProofDiagnostic(
                code="candidates.error",
                message=f"Candidate generation failed: {str(error).strip() or type(error).__name__}.",
            )
        )
        return None

    diagnostics.extend(_candidate_library_diagnostics(library))
    search_result = solve_candidate_combination(
        library,
        limits=options.combination_limits,
    )
    diagnostics.extend(search_result.diagnostics)
    if search_result.status is not CombinationSearchStatus.FEASIBLE:
        return None

    if len(search_result.weights) != len(library.candidates):
        return _verification_failure(
            target,
            tuple(diagnostics),
            "the combination solver returned the wrong number of exact weights",
        )
    try:
        terms = tuple(
            candidate.weighted_component(column_weight)
            for candidate, column_weight in zip(
                library.candidates,
                search_result.weights,
                strict=True,
            )
            if column_weight > 0
        )
    except CandidateGenerationError as error:
        return _verification_failure(target, tuple(diagnostics), str(error))

    proposal = RecognitionCandidate(method="candidate_combination", terms=terms)
    return _verify_candidate(target, proposal, tuple(diagnostics))


def _disproved_result(
    target: HomogeneousPolynomial,
    counterexample: Counterexample,
    diagnostics: Iterable[ProofDiagnostic],
) -> ProofResult:
    """Build a DISPROVED result whose exact witness is rechecked by ProofResult."""
    return ProofResult(
        target=target,
        status=ProofStatus.DISPROVED,
        method="rational_counterexample",
        counterexample=counterexample,
        diagnostics=tuple(diagnostics),
    )


def _search_exact_counterexample(
    target: HomogeneousPolynomial,
    options: ProofSearchOptions,
    diagnostics: list[ProofDiagnostic],
) -> ProofResult | None:
    """Search a bounded rational simplex grid and return exact negative evidence."""
    try:
        search_result = search_counterexample(
            target,
            limits=options.counterexample_limits,
        )
    except (CounterexampleSearchError, PolynomialInputError) as error:
        diagnostics.append(
            ProofDiagnostic(
                code="counterexample.error",
                message=f"Exact counterexample search failed: {str(error).strip() or type(error).__name__}.",
            )
        )
        return None

    if search_result.counterexample is not None:
        diagnostics.append(
            ProofDiagnostic(
                code="counterexample.found",
                message=(
                    "An exact negative rational point was found after checking "
                    f"{search_result.checked_points} simplex points."
                ),
            )
        )
        return _disproved_result(
            target,
            search_result.counterexample,
            diagnostics,
        )

    if search_result.complete:
        code = "counterexample.exhausted"
        message = (
            "No negative point was found among "
            f"{search_result.checked_points} checked rational simplex points; "
            "the bounded search is inconclusive."
        )
    else:
        code = "counterexample.point_limit"
        message = (
            "Exact counterexample search reached its point limit after checking "
            f"{search_result.checked_points} points."
        )
    diagnostics.append(ProofDiagnostic(code=code, message=message))
    return None


def prove(
    target: HomogeneousPolynomial,
    *,
    options: ProofSearchOptions | None = None,
) -> ProofResult:
    """Return an exact proof, an exact rational counterexample, or structured UNKNOWN."""
    if not isinstance(target, HomogeneousPolynomial):
        raise PolynomialInputError(
            "prove() requires a HomogeneousPolynomial; construct one with "
            "HomogeneousPolynomial.from_expr()"
        )
    target = HomogeneousPolynomial.from_terms(
        target.coefficients,
        variables=target.variables,
    )
    if options is None:
        options = ProofSearchOptions()
    elif type(options) is not ProofSearchOptions:
        raise ValueError("options must be a ProofSearchOptions object or None")

    diagnostics: list[ProofDiagnostic] = []
    for recognizer in (recognize_zero, recognize_positive_monomial):
        attempt = recognizer(target)
        diagnostics.append(attempt.diagnostic)
        if attempt.candidate is not None:
            return _verify_candidate(target, attempt.candidate, tuple(diagnostics))

    normalization = factor_content(target)
    for recognizer in (recognize_classic_schur, recognize_exact_square):
        attempt = recognizer(normalization)
        diagnostics.append(attempt.diagnostic)
        if attempt.candidate is not None:
            return _verify_candidate(target, attempt.candidate, tuple(diagnostics))

    coefficient_attempt = recognize_nonnegative_coefficients(target)
    diagnostics.append(coefficient_attempt.diagnostic)
    if coefficient_attempt.candidate is not None:
        return _verify_candidate(
            target,
            coefficient_attempt.candidate,
            tuple(diagnostics),
        )

    diagnostics.append(
        ProofDiagnostic(
            code="direct.no_match",
            message=(
                "The fixed direct recognizers found no certificate; this result is "
                "inconclusive and does not assert that the target is negative."
            ),
        )
    )

    if options.enable_combination_search:
        combination_result = _search_candidate_combination(
            target,
            options,
            diagnostics,
        )
        if combination_result is not None:
            return combination_result

    if options.enable_counterexample_search:
        counterexample_result = _search_exact_counterexample(
            target,
            options,
            diagnostics,
        )
        if counterexample_result is not None:
            return counterexample_result

    return _unknown_result(target, diagnostics)

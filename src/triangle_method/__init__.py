"""Exact proof, polynomial, and coefficient-triangle tools for Triangle Method."""

from .candidates import (
    CandidateFamily,
    CandidateGenerationLimits,
    CandidateGenerationMetadata,
    CandidateLibrary,
    ComponentCandidate,
    GenerationStopReason,
    generate_candidates,
)
from .certificate import DecompositionCertificate, WeightedComponent
from .counterexamples import (
    Counterexample,
    CounterexampleSearchError,
    CounterexampleSearchLimits,
    CounterexampleSearchResult,
    CounterexampleSearchStopReason,
    evaluate_on_simplex,
    search_counterexample,
    verify_counterexample,
)
from .errors import (
    CandidateGenerationError,
    CertificateInputError,
    PolynomialInputError,
    PrimitiveInputError,
)
from .normalization import Normalization, factor_content
from .polynomial import HomogeneousPolynomial
from .primitives import (
    MonomialComponent,
    PrimitiveComponent,
    SchurComponent,
    SquareComponent,
)
from .proof import ProofSearchOptions, prove
from .results import ProofDiagnostic, ProofResult, ProofStatus
from .search import (
    CombinationSearchLimits,
    CombinationSearchResult,
    CombinationSearchStatus,
    SolverBackend,
    solve_candidate_combination,
)
from .triangle import coefficient_rows, from_coefficient_rows, triangle_exponents
from .verify import VerificationIssue, VerificationReport, verify_certificate
from .visualization import CoefficientTriangle, coefficient_triangle

__all__ = [
    "CandidateFamily",
    "CandidateGenerationError",
    "CandidateGenerationLimits",
    "CandidateGenerationMetadata",
    "CandidateLibrary",
    "CertificateInputError",
    "CoefficientTriangle",
    "CombinationSearchLimits",
    "CombinationSearchResult",
    "CombinationSearchStatus",
    "ComponentCandidate",
    "Counterexample",
    "CounterexampleSearchError",
    "CounterexampleSearchLimits",
    "CounterexampleSearchResult",
    "CounterexampleSearchStopReason",
    "DecompositionCertificate",
    "GenerationStopReason",
    "HomogeneousPolynomial",
    "MonomialComponent",
    "Normalization",
    "PolynomialInputError",
    "ProofDiagnostic",
    "ProofResult",
    "ProofSearchOptions",
    "ProofStatus",
    "PrimitiveComponent",
    "PrimitiveInputError",
    "SchurComponent",
    "SolverBackend",
    "SquareComponent",
    "VerificationIssue",
    "VerificationReport",
    "WeightedComponent",
    "coefficient_rows",
    "coefficient_triangle",
    "evaluate_on_simplex",
    "factor_content",
    "from_coefficient_rows",
    "generate_candidates",
    "prove",
    "search_counterexample",
    "solve_candidate_combination",
    "triangle_exponents",
    "verify_certificate",
    "verify_counterexample",
]

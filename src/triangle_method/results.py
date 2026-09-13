"""Stable result and diagnostic records for automatic proof attempts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .certificate import DecompositionCertificate
from .counterexamples import Counterexample, verify_counterexample
from .errors import PolynomialInputError
from .polynomial import HomogeneousPolynomial
from .verify import VerificationReport, verify_certificate

_SUCCESS_METHODS = frozenset(
    {
        "zero",
        "monomial",
        "classic_schur",
        "exact_square",
        "nonnegative_coefficients",
        "candidate_combination",
    }
)
_DISPROOF_METHOD = "rational_counterexample"


class ProofStatus(str, Enum):
    """Name the three possible mathematical outcomes of a proof workflow."""

    PROVED = "PROVED"
    UNKNOWN = "UNKNOWN"
    DISPROVED = "DISPROVED"


@dataclass(frozen=True, slots=True)
class ProofDiagnostic:
    """Store a stable machine-readable code and its human-readable explanation."""

    code: str
    message: str

    def __post_init__(self) -> None:
        """Require nonempty diagnostic text without silently rewriting either field."""
        for field_name, value in (("code", self.code), ("message", self.message)):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"diagnostic {field_name} must be a nonempty string")
            if value != value.strip():
                raise ValueError(
                    f"diagnostic {field_name} cannot have leading or trailing whitespace"
                )


@dataclass(frozen=True, slots=True, kw_only=True)
class ProofResult:
    """Store one proof outcome and its independently checked proof or witness evidence."""

    target: HomogeneousPolynomial
    status: ProofStatus
    method: str | None = None
    certificate: DecompositionCertificate | None = None
    verification: VerificationReport | None = None
    counterexample: Counterexample | None = None
    diagnostics: tuple[ProofDiagnostic, ...] = ()

    def __post_init__(self) -> None:
        """Copy immutable inputs and enforce the evidence required by each status."""
        if not isinstance(self.target, HomogeneousPolynomial):
            raise PolynomialInputError("result target must be a HomogeneousPolynomial")
        copied_target = HomogeneousPolynomial.from_terms(
            self.target.coefficients,
            variables=self.target.variables,
        )
        object.__setattr__(self, "target", copied_target)

        if not isinstance(self.status, ProofStatus):
            raise ValueError("result status must be a ProofStatus")
        if self.method is not None:
            if not isinstance(self.method, str) or not self.method.strip():
                raise ValueError("result method must be None or a nonempty string")
            if self.method != self.method.strip():
                raise ValueError(
                    "result method cannot have leading or trailing whitespace"
                )

        if isinstance(self.diagnostics, (str, bytes)):
            raise ValueError("result diagnostics must contain ProofDiagnostic objects")
        try:
            copied_diagnostics = tuple(self.diagnostics)
        except TypeError as error:
            raise ValueError(
                "result diagnostics must be an iterable of ProofDiagnostic objects"
            ) from error
        if any(
            not isinstance(diagnostic, ProofDiagnostic)
            for diagnostic in copied_diagnostics
        ):
            raise ValueError("result diagnostics must contain ProofDiagnostic objects")
        object.__setattr__(self, "diagnostics", copied_diagnostics)

        if self.status is ProofStatus.PROVED:
            self._validate_proved_state(copied_target)
        elif self.status is ProofStatus.UNKNOWN:
            self._validate_unknown_state(copied_diagnostics)
        else:
            self._validate_disproved_state(copied_target, copied_diagnostics)

    def _validate_proved_state(self, target: HomogeneousPolynomial) -> None:
        """Require a matching certificate and a successful exact verification report."""
        if self.method is None:
            raise ValueError("a PROVED result must identify its proof method")
        if self.method not in _SUCCESS_METHODS:
            raise ValueError(f"unsupported proof method: {self.method!r}")
        if self.counterexample is not None:
            raise ValueError("a PROVED result cannot contain a counterexample")
        if type(self.certificate) is not DecompositionCertificate:
            raise ValueError("a PROVED result must contain a decomposition certificate")
        if self.certificate.target != target:
            raise ValueError(
                "result certificate target does not match the result target"
            )
        if type(self.verification) is not VerificationReport:
            raise ValueError("a PROVED result must contain a verification report")
        if self.verification.valid is not True or self.verification.issues != ():
            raise ValueError("a PROVED result requires a valid verification report")
        if self.verification.reconstructed != target:
            raise ValueError(
                "a PROVED result verification must reconstruct the result target"
            )
        if self.verification.residual is None or not self.verification.residual.is_zero:
            raise ValueError(
                "a PROVED result verification must have an exact zero residual"
            )

        independent_report = verify_certificate(self.certificate)
        if self.verification != independent_report:
            raise ValueError(
                "a PROVED result verification must be the exact report for its "
                "certificate"
            )
        object.__setattr__(self, "verification", independent_report)

    def _validate_unknown_state(
        self,
        diagnostics: tuple[ProofDiagnostic, ...],
    ) -> None:
        """Require an inconclusive result to carry explanations and no proof evidence."""
        if self.method is not None:
            raise ValueError("an UNKNOWN result cannot identify a successful method")
        if self.certificate is not None or self.verification is not None:
            raise ValueError("an UNKNOWN result cannot contain proof evidence")
        if self.counterexample is not None:
            raise ValueError("an UNKNOWN result cannot contain a counterexample")
        if not diagnostics:
            raise ValueError("an UNKNOWN result must contain at least one diagnostic")

    def _validate_disproved_state(
        self,
        target: HomogeneousPolynomial,
        diagnostics: tuple[ProofDiagnostic, ...],
    ) -> None:
        """Require one exact negative witness and exclude decomposition evidence."""
        if self.method != _DISPROOF_METHOD:
            raise ValueError(f"a DISPROVED result must use method {_DISPROOF_METHOD!r}")
        if self.certificate is not None or self.verification is not None:
            raise ValueError("a DISPROVED result cannot contain proof evidence")
        if type(self.counterexample) is not Counterexample:
            raise ValueError("a DISPROVED result must contain a counterexample")
        if not diagnostics:
            raise ValueError("a DISPROVED result must contain at least one diagnostic")
        if not verify_counterexample(target, self.counterexample):
            raise ValueError(
                "a DISPROVED result requires an exact counterexample for its target"
            )

        rebuilt = Counterexample(
            target=target,
            coordinates=self.counterexample.coordinates,
            value=self.counterexample.value,
        )
        object.__setattr__(self, "counterexample", rebuilt)

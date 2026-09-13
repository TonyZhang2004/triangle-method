import type {
  DiagnosticPayload,
  ProofRequest,
  ProofResponse,
  RationalRecord,
  SupportedDegree,
} from "../../contracts/index.js";

export const ZERO: RationalRecord = { numerator: "0", denominator: "1" };

export function rational(
  numerator: string,
  denominator = "1",
): RationalRecord {
  return { numerator, denominator };
}

export function rationalRows(
  degree: SupportedDegree,
  coefficient: RationalRecord = ZERO,
): RationalRecord[][] {
  return Array.from({ length: degree + 1 }, (_, row) =>
    Array.from({ length: row + 1 }, () => ({ ...coefficient })),
  );
}

export function requestRows(degree: SupportedDegree): string[][] {
  return Array.from({ length: degree + 1 }, (_, row) =>
    Array.from({ length: row + 1 }, () => "0"),
  );
}

export function proofRequest(degree: SupportedDegree = 2): ProofRequest {
  return {
    schema: "triangle_method.proof_request",
    schemaVersion: 1,
    degree,
    coefficientRows: requestRows(degree),
  };
}

const diagnostic: DiagnosticPayload = {
  code: "test.result",
  message: "A deterministic test result.",
};

export function provedResponse(
  degree: SupportedDegree = 2,
): ProofResponse {
  return {
    schema: "triangle_method.proof_response",
    schemaVersion: 1,
    outcome: "PROVED",
    method: "zero",
    target: {
      degree,
      coefficientRows: rationalRows(degree),
      latex: "0 \\ge 0",
    },
    proof: {
      verified: true,
      residualZero: true,
      identityLatex: "0 = 0 \\ge 0",
      terms: [],
      steps: [],
      groups: [],
    },
    counterexample: null,
    diagnostics: [diagnostic],
  };
}

export function unknownResponse(
  degree: SupportedDegree = 2,
): ProofResponse {
  return {
    schema: "triangle_method.proof_response",
    schemaVersion: 1,
    outcome: "UNKNOWN",
    method: null,
    target: {
      degree,
      coefficientRows: rationalRows(degree),
      latex: "0 \\ge 0",
    },
    proof: null,
    counterexample: null,
    diagnostics: [diagnostic],
  };
}

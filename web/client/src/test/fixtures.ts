import type {
  ProofResponse,
  RationalRecord,
  SupportedDegree,
} from "../types";

export const rational = (
  numerator: string,
  denominator = "1",
): RationalRecord => ({ numerator, denominator });

export function zeroRows(degree: SupportedDegree): RationalRecord[][] {
  return Array.from({ length: degree + 1 }, (_, row) =>
    Array.from({ length: row + 1 }, () => rational("0")),
  );
}

export function zeroProof(degree: SupportedDegree = 3): ProofResponse {
  return {
    schema: "triangle_method.proof_response",
    schemaVersion: 1,
    outcome: "PROVED",
    method: "zero",
    target: {
      degree,
      coefficientRows: zeroRows(degree),
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
    diagnostics: [
      { code: "zero.matched", message: "The exact zero polynomial matched." },
    ],
  };
}

export function positiveCubicMonomialProof(): ProofResponse {
  const targetRows = zeroRows(3);
  targetRows[0][0] = rational("1");
  return {
    schema: "triangle_method.proof_response",
    schemaVersion: 1,
    outcome: "PROVED",
    method: "monomial",
    target: {
      degree: 3,
      coefficientRows: targetRows,
      latex: "x^{3} \\ge 0",
    },
    proof: {
      verified: true,
      residualZero: true,
      identityLatex: "x^{3} = x^{3} \\ge 0",
      terms: [
        {
          id: "component-1",
          kind: "monomial",
          weight: rational("1"),
          expressionLatex: "x^{3}",
          weightedExpressionLatex: "x^{3}",
          contributionRows: targetRows,
        },
      ],
      steps: [
        {
          componentId: "component-1",
          accumulatedRows: targetRows,
          remainderRows: zeroRows(3),
        },
      ],
      groups: [
        {
          id: "group-1",
          label: "Nonnegative monomial",
          semanticKind: "monomial",
          termIds: ["component-1"],
        },
      ],
    },
    counterexample: null,
    diagnostics: [
      {
        code: "monomial.matched",
        message: "The positive monomial matched directly.",
      },
    ],
  };
}

export function combinedCauchyAmGmProof(): ProofResponse {
  const target = [
    [rational("3")],
    [rational("-4"), rational("-2")],
    [rational("3"), rational("-2"), rational("2")],
  ];
  const first = [
    [rational("1")],
    [rational("-2"), rational("0")],
    [rational("1"), rational("0"), rational("0")],
  ];
  const second = [
    [rational("1")],
    [rational("0"), rational("-2")],
    [rational("0"), rational("0"), rational("1")],
  ];
  const third = [
    [rational("0")],
    [rational("0"), rational("0")],
    [rational("1"), rational("-2"), rational("1")],
  ];
  const fourth = first;
  const afterFirst = first;
  const remainderFirst = [
    [rational("2")],
    [rational("-2"), rational("-2")],
    [rational("2"), rational("-2"), rational("2")],
  ];
  const afterSecond = [
    [rational("2")],
    [rational("-2"), rational("-2")],
    [rational("1"), rational("0"), rational("1")],
  ];
  const remainderSecond = [
    [rational("1")],
    [rational("-2"), rational("0")],
    [rational("2"), rational("-2"), rational("1")],
  ];
  const afterThird = [
    [rational("2")],
    [rational("-2"), rational("-2")],
    [rational("2"), rational("-2"), rational("2")],
  ];
  return {
    schema: "triangle_method.proof_response",
    schemaVersion: 1,
    outcome: "PROVED",
    method: "candidate_combination",
    target: {
      degree: 2,
      coefficientRows: target,
      latex: "3 x^{2} - 4 x y - 2 x z + 3 y^{2} - 2 y z + 2 z^{2} \\ge 0",
    },
    proof: {
      verified: true,
      residualZero: true,
      identityLatex:
        "3 x^{2} - 4 x y - 2 x z + 3 y^{2} - 2 y z + 2 z^{2} = (x-y)^2 + (x-z)^2 + (y-z)^2 + (x-y)^2 \\ge 0",
      terms: [
        {
          id: "component-1",
          kind: "square",
          weight: rational("1"),
          expressionLatex: "(x-y)^2",
          weightedExpressionLatex: "(x-y)^2",
          contributionRows: first,
        },
        {
          id: "component-2",
          kind: "square",
          weight: rational("1"),
          expressionLatex: "(x-z)^2",
          weightedExpressionLatex: "(x-z)^2",
          contributionRows: second,
        },
        {
          id: "component-3",
          kind: "square",
          weight: rational("1"),
          expressionLatex: "(y-z)^2",
          weightedExpressionLatex: "(y-z)^2",
          contributionRows: third,
        },
        {
          id: "component-4",
          kind: "square",
          weight: rational("1"),
          expressionLatex: "(x-y)^2",
          weightedExpressionLatex: "(x-y)^2",
          contributionRows: fourth,
        },
      ],
      steps: [
        {
          componentId: "component-1",
          accumulatedRows: afterFirst,
          remainderRows: remainderFirst,
        },
        {
          componentId: "component-2",
          accumulatedRows: afterSecond,
          remainderRows: remainderSecond,
        },
        {
          componentId: "component-3",
          accumulatedRows: afterThird,
          remainderRows: fourth,
        },
        {
          componentId: "component-4",
          accumulatedRows: target,
          remainderRows: zeroRows(2),
        },
      ],
      groups: [
        {
          id: "group-1",
          label: "Cauchy",
          semanticKind: "cauchy",
          termIds: ["component-1", "component-2", "component-3"],
        },
        {
          id: "group-2",
          label: "AM-GM",
          semanticKind: "am_gm",
          termIds: ["component-4"],
        },
      ],
    },
    counterexample: null,
    diagnostics: [
      {
        code: "verification.passed",
        message: "The independent exact verifier accepted the certificate.",
      },
    ],
  };
}

export function unknownProof(): ProofResponse {
  return {
    schema: "triangle_method.proof_response",
    schemaVersion: 1,
    outcome: "UNKNOWN",
    method: null,
    target: {
      degree: 2,
      coefficientRows: zeroRows(2),
      latex: "0 \\ge 0",
    },
    proof: null,
    counterexample: null,
    diagnostics: [
      {
        code: "counterexample.exhausted",
        message: "The bounded search was inconclusive.",
      },
    ],
  };
}

export function disprovedProof(): ProofResponse {
  return {
    schema: "triangle_method.proof_response",
    schemaVersion: 1,
    outcome: "DISPROVED",
    method: "rational_counterexample",
    target: {
      degree: 2,
      coefficientRows: [
        [rational("1")],
        [rational("-4"), rational("0")],
        [rational("1"), rational("0"), rational("1")],
      ],
      latex: "x^2 - 4xy + y^2 + z^2 \\ge 0",
    },
    proof: null,
    counterexample: {
      coordinates: [rational("1", "2"), rational("1", "2"), rational("0")],
      value: rational("-1", "2"),
      evaluationLatex:
        "F\\left(\\frac{1}{2},\\frac{1}{2},0\\right)=-\\frac{1}{2}<0",
    },
    diagnostics: [
      {
        code: "counterexample.found",
        message: "An exact rational counterexample was found.",
      },
    ],
  };
}

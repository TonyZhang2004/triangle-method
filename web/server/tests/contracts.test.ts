// @vitest-environment node

import { describe, expect, it } from "vitest";

import {
  ContractValidationError,
  parseProofRequest,
  parseProofResponse,
} from "../../contracts/index.js";
import {
  proofRequest,
  provedResponse,
  rational,
  rationalRows,
  unknownResponse,
} from "./test-helpers.js";

describe("proof request contract", () => {
  it("accepts and copies an exact triangular request", () => {
    const source = proofRequest(3);
    source.coefficientRows[1] = ["2/4", "-7"];

    const parsed = parseProofRequest(source);

    expect(parsed).toEqual(source);
    expect(parsed).not.toBe(source);
    expect(parsed.coefficientRows).not.toBe(source.coefficientRows);
  });

  it("accepts all 91 exact coefficients in a degree-12 request", () => {
    const source = proofRequest(12);
    source.coefficientRows[12][12] = "-123456789/100000000";

    const parsed = parseProofRequest(source);

    expect(parsed.degree).toBe(12);
    expect(parsed.coefficientRows.map((row) => row.length)).toEqual(
      Array.from({ length: 13 }, (_, row) => row + 1),
    );
    expect(parsed.coefficientRows.flat()).toHaveLength(91);
    expect(parsed.coefficientRows[12][12]).toBe("-123456789/100000000");
    expect(parsed.coefficientRows[12]).not.toBe(source.coefficientRows[12]);
  });

  it.each([
    ["wrong schema", { ...proofRequest(), schema: "wrong" }],
    ["extra field", { ...proofRequest(), unexpected: true }],
    [
      "degree above the API limit",
      { ...proofRequest(12), degree: 13 },
    ],
    [
      "wrong number of rows",
      { ...proofRequest(), coefficientRows: [["0"], ["0", "0"]] },
    ],
    [
      "wrong row width",
      { ...proofRequest(), coefficientRows: [["0"], ["0"], ["0", "0", "0"]] },
    ],
    [
      "decimal coefficient",
      { ...proofRequest(), coefficientRows: [["0.5"], ["0", "0"], ["0", "0", "0"]] },
    ],
    [
      "noncanonical zero",
      { ...proofRequest(), coefficientRows: [["-0"], ["0", "0"], ["0", "0", "0"]] },
    ],
    [
      "oversized coefficient",
      {
        ...proofRequest(),
        coefficientRows: [
          ["1".repeat(65)],
          ["0", "0"],
          ["0", "0", "0"],
        ],
      },
    ],
  ])("rejects %s", (_label, value) => {
    expect(() => parseProofRequest(value)).toThrow(ContractValidationError);
  });
});

describe("proof response contract", () => {
  it("accepts the three mathematical outcome shapes", () => {
    const disproved = {
      ...unknownResponse(),
      outcome: "DISPROVED",
      method: "rational_counterexample",
      counterexample: {
        coordinates: [rational("1", "2"), rational("1", "2"), rational("0")],
        value: rational("-1", "2"),
        evaluationLatex: "F(1/2,1/2,0)=-1/2<0",
      },
    };

    expect(parseProofResponse(provedResponse()).outcome).toBe("PROVED");
    expect(parseProofResponse(unknownResponse()).outcome).toBe("UNKNOWN");
    expect(parseProofResponse(disproved).outcome).toBe("DISPROVED");
  });

  it("accepts exact triangular data in a degree-12 response", () => {
    const response = unknownResponse(12);
    response.target.coefficientRows[12][12] = rational("-5", "7");
    response.target.latex = "-\\frac{5}{7}z^{12} \\ge 0";

    const parsed = parseProofResponse(response);

    expect(parsed.target.degree).toBe(12);
    expect(parsed.target.coefficientRows.map((row) => row.length)).toEqual(
      Array.from({ length: 13 }, (_, row) => row + 1),
    );
    expect(parsed.target.coefficientRows.flat()).toHaveLength(91);
    expect(parsed.target.coefficientRows[12][12]).toEqual(rational("-5", "7"));
    expect(parsed.target.coefficientRows[12]).not.toBe(
      response.target.coefficientRows[12],
    );
  });

  it("rejects a degree-13 response", () => {
    const response = {
      ...unknownResponse(12),
      target: {
        ...unknownResponse(12).target,
        degree: 13,
      },
    };

    expect(() => parseProofResponse(response)).toThrow(ContractValidationError);
  });

  it("validates term, step, group, and triangular contribution references", () => {
    const response = provedResponse();
    const rows = rationalRows(2);
    response.method = "candidate_combination";
    response.proof!.terms = [
      {
        id: "component-1",
        kind: "square",
        weight: rational("1", "2"),
        expressionLatex: "(x-y)^2",
        weightedExpressionLatex: "\\frac12(x-y)^2",
        contributionRows: rows,
      },
    ];
    response.proof!.steps = [
      {
        componentId: "component-1",
        accumulatedRows: rows,
        remainderRows: rows,
      },
    ];
    response.proof!.groups = [
      {
        id: "group-1",
        label: "AM-GM",
        semanticKind: "am_gm",
        termIds: ["component-1"],
      },
    ];

    expect(parseProofResponse(response)).toEqual(response);
  });

  it.each([
    ["proof on UNKNOWN", { ...unknownResponse(), proof: provedResponse().proof }],
    ["method on UNKNOWN", { ...unknownResponse(), method: "maybe" }],
    [
      "counterexample on PROVED",
      {
        ...provedResponse(),
        counterexample: {
          coordinates: [rational("1"), rational("0"), rational("0")],
          value: rational("-1"),
          evaluationLatex: "-1<0",
        },
      },
    ],
    [
      "unreduced rational",
      {
        ...unknownResponse(),
        target: {
          ...unknownResponse().target,
          coefficientRows: [
            [rational("2", "4")],
            [rational("0"), rational("0")],
            [rational("0"), rational("0"), rational("0")],
          ],
        },
      },
    ],
  ])("rejects %s", (_label, value) => {
    expect(() => parseProofResponse(value)).toThrow(ContractValidationError);
  });
});

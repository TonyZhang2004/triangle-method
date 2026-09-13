import { describe, expect, it } from "vitest";

import {
  coefficientRowsToLatex,
  exponentAt,
  normalizeCoefficientRows,
  parseExactRational,
} from "./exact";

describe("exact coefficient input", () => {
  it.each([
    ["", { numerator: "0", denominator: "1" }],
    ["−6/8", { numerator: "-3", denominator: "4" }],
    ["+42", { numerator: "42", denominator: "1" }],
    ["-0", { numerator: "0", denominator: "1" }],
    ["100000000000000000000000000001/3", { numerator: "100000000000000000000000000001", denominator: "3" }],
  ])("parses %s without floating-point coercion", (raw, expected) => {
    expect(parseExactRational(raw)).toEqual({ ok: true, value: expected });
  });

  it.each(["0.5", "1e3", "x", "1/0", "1/-2", "1/2/3"])(
    "rejects unsupported value %s",
    (raw) => {
      expect(parseExactRational(raw).ok).toBe(false);
    },
  );

  it("accepts 64 digits and rejects 65 in each coefficient part", () => {
    expect(parseExactRational("1".repeat(64)).ok).toBe(true);
    expect(parseExactRational(`1/${"2".repeat(64)}`).ok).toBe(true);
    expect(
      parseExactRational(`-${"1".repeat(64)}/${"2".repeat(64)}`).ok,
    ).toBe(true);
    expect(parseExactRational("1".repeat(65)).ok).toBe(false);
    expect(parseExactRational(`1/${"2".repeat(65)}`).ok).toBe(false);
  });

  it("normalizes blanks and reduced fractions for the API", () => {
    const normalized = normalizeCoefficientRows([
      [" 2/4 "],
      ["", "−3"],
    ]);
    expect(normalized.errors.size).toBe(0);
    expect(normalized.rows).toEqual([["1/2"], ["0", "-3"]]);
  });

  it("uses the backend's canonical cubic orientation", () => {
    expect(
      Array.from({ length: 4 }, (_, row) =>
        Array.from({ length: row + 1 }, (_, column) =>
          exponentAt(3, row, column),
        ),
      ),
    ).toEqual([
      [[3, 0, 0]],
      [
        [2, 1, 0],
        [2, 0, 1],
      ],
      [
        [1, 2, 0],
        [1, 1, 1],
        [1, 0, 2],
      ],
      [
        [0, 3, 0],
        [0, 2, 1],
        [0, 1, 2],
        [0, 0, 3],
      ],
    ]);
  });

  it("builds a normalized exact inequality preview", () => {
    expect(
      coefficientRowsToLatex(2, [["3"], ["-4", "-2"], ["3", "-2", "2"]]),
    ).toBe("3x^{2} - 4xy - 2xz + 3y^{2} - 2yz + 2z^{2}");
  });
});

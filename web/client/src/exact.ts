import type { RationalRecord } from "./types";

export type ExactParseResult =
  | { ok: true; value: RationalRecord }
  | { ok: false; message: string };

const INTEGER_PATTERN = /^[+-]?\d+$/;
const FRACTION_PATTERN = /^([+-]?\d+)\/([1-9]\d*)$/;
const MAX_DIGITS_PER_PART = 64;
const MAX_INPUT_LENGTH = 130;

/** Return the nonnegative greatest common divisor of two bigint values. */
function greatestCommonDivisor(left: bigint, right: bigint): bigint {
  let first = left < 0n ? -left : left;
  let second = right < 0n ? -right : right;
  while (second !== 0n) {
    [first, second] = [second, first % second];
  }
  return first;
}

/** Parse an integer or positive-denominator fraction into a reduced exact record. */
export function parseExactRational(rawValue: string): ExactParseResult {
  const value = rawValue.trim().replaceAll("−", "-");
  if (value === "") {
    return { ok: true, value: { numerator: "0", denominator: "1" } };
  }
  if (value.length > MAX_INPUT_LENGTH) {
    return {
      ok: false,
      message: `Use at most ${MAX_INPUT_LENGTH} characters.`,
    };
  }

  let numeratorText: string;
  let denominatorText: string;
  const fraction = FRACTION_PATTERN.exec(value);
  if (fraction) {
    numeratorText = fraction[1];
    denominatorText = fraction[2];
  } else if (INTEGER_PATTERN.test(value)) {
    numeratorText = value;
    denominatorText = "1";
  } else {
    return {
      ok: false,
      message: "Enter an integer or an exact fraction such as -3/4.",
    };
  }

  if (
    numeratorText.replace(/^[+-]/, "").length > MAX_DIGITS_PER_PART ||
    denominatorText.length > MAX_DIGITS_PER_PART
  ) {
    return {
      ok: false,
      message: `Use at most ${MAX_DIGITS_PER_PART} digits in each part.`,
    };
  }

  try {
    const numerator = BigInt(numeratorText);
    const denominator = BigInt(denominatorText);
    const divisor = greatestCommonDivisor(numerator, denominator);
    const reducedNumerator = numerator / divisor;
    const reducedDenominator = denominator / divisor;
    return {
      ok: true,
      value: {
        numerator: reducedNumerator.toString(),
        denominator: reducedDenominator.toString(),
      },
    };
  } catch {
    return {
      ok: false,
      message: "Enter an integer or an exact fraction such as -3/4.",
    };
  }
}

/** Format an exact rational record as compact plain text. */
export function formatRational(value: RationalRecord): string {
  if (value.denominator === "1") {
    return value.numerator;
  }
  return `${value.numerator}/${value.denominator}`;
}

/** Return whether an exact rational record represents zero. */
export function isZeroRational(value: RationalRecord): boolean {
  return BigInt(value.numerator) === 0n;
}

/** Build an empty triangular coefficient draft for one homogeneous degree. */
export function emptyCoefficientRows(degree: number): string[][] {
  return Array.from({ length: degree + 1 }, (_, row) =>
    Array.from({ length: row + 1 }, () => ""),
  );
}

/** Parse every draft entry and return normalized request strings plus field errors. */
export function normalizeCoefficientRows(rows: string[][]): {
  rows: string[][];
  errors: Map<string, string>;
} {
  const errors = new Map<string, string>();
  const normalized = rows.map((row, rowIndex) =>
    row.map((rawValue, columnIndex) => {
      const parsed = parseExactRational(rawValue);
      if (!parsed.ok) {
        errors.set(`${rowIndex}:${columnIndex}`, parsed.message);
        return "0";
      }
      return formatRational(parsed.value);
    }),
  );
  return { rows: normalized, errors };
}

/** Return the exponent at a canonical coefficient-triangle position. */
export function exponentAt(
  degree: number,
  row: number,
  column: number,
): [number, number, number] {
  return [degree - row, row - column, column];
}

/** Format an exponent triple as a compact KaTeX monomial. */
export function monomialLatex(exponent: readonly number[]): string {
  return ["x", "y", "z"]
    .map((variable, index) => {
      const power = exponent[index];
      if (power === 0) return "";
      if (power === 1) return variable;
      return `${variable}^{${power}}`;
    })
    .join("");
}

/** Describe an exponent triple for a coefficient input's accessible name. */
export function monomialPlainText(exponent: readonly number[]): string {
  const parts = ["x", "y", "z"]
    .map((variable, index) => {
      const power = exponent[index];
      if (power === 0) return "";
      if (power === 1) return variable;
      return `${variable} to the power ${power}`;
    })
    .filter(Boolean);
  return parts.join(" times ") || "one";
}

function rationalMagnitudeLatex(value: RationalRecord): string {
  const numerator = value.numerator.replace(/^-/, "");
  if (value.denominator === "1") return numerator;
  return `\\frac{${numerator}}{${value.denominator}}`;
}

/** Build a normalized polynomial LaTeX preview from exact triangular drafts. */
export function coefficientRowsToLatex(
  degree: number,
  rows: string[][],
): string | null {
  const parsedRows = rows.map((row) =>
    row.map((rawValue) => parseExactRational(rawValue)),
  );
  if (parsedRows.some((row) => row.some((result) => !result.ok))) {
    return null;
  }

  const terms: Array<{ negative: boolean; body: string }> = [];
  parsedRows.forEach((row, rowIndex) => {
    row.forEach((result, columnIndex) => {
      if (!result.ok || isZeroRational(result.value)) return;
      const exponent = exponentAt(degree, rowIndex, columnIndex);
      const monomial = monomialLatex(exponent);
      const magnitudeIsOne =
        result.value.numerator.replace(/^-/, "") === "1" &&
        result.value.denominator === "1";
      const coefficient =
        magnitudeIsOne && monomial !== ""
          ? ""
          : rationalMagnitudeLatex(result.value);
      terms.push({
        negative: result.value.numerator.startsWith("-"),
        body: `${coefficient}${monomial}`,
      });
    });
  });

  if (terms.length === 0) return "0";
  return terms
    .map((term, index) => {
      if (index === 0) return `${term.negative ? "-" : ""}${term.body}`;
      return `${term.negative ? " - " : " + "}${term.body}`;
    })
    .join("");
}

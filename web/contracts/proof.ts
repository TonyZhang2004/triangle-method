/** Shared, versioned transport contract for exact proof requests and results. */

export const PROOF_REQUEST_SCHEMA_NAME = "triangle_method.proof_request" as const;
export const PROOF_RESPONSE_SCHEMA_NAME = "triangle_method.proof_response" as const;
export const PROOF_SCHEMA_VERSION = 1 as const;
export const MINIMUM_SUPPORTED_DEGREE = 2 as const;
export const MAXIMUM_SUPPORTED_DEGREE = 12 as const;
export const SUPPORTED_DEGREES = [
  2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12,
] as const;

export type SupportedDegree = (typeof SUPPORTED_DEGREES)[number];
export type ProofOutcome = "PROVED" | "DISPROVED" | "UNKNOWN";
export type TermKind = "square" | "schur" | "monomial";
export type SemanticKind =
  | "cauchy"
  | "am_gm"
  | "schur"
  | "square"
  | "monomial";

export interface ProofRequest {
  schema: typeof PROOF_REQUEST_SCHEMA_NAME;
  schemaVersion: typeof PROOF_SCHEMA_VERSION;
  degree: SupportedDegree;
  coefficientRows: string[][];
}

export interface RationalRecord {
  numerator: string;
  denominator: string;
}

export interface PolynomialPayload {
  degree: SupportedDegree;
  coefficientRows: RationalRecord[][];
  latex: string;
}

export interface DiagnosticPayload {
  code: string;
  message: string;
}

export interface ProofTermPayload {
  id: string;
  kind: TermKind;
  weight: RationalRecord;
  expressionLatex: string;
  weightedExpressionLatex: string;
  contributionRows: RationalRecord[][];
}

export interface ProofStepPayload {
  componentId: string;
  accumulatedRows: RationalRecord[][];
  remainderRows: RationalRecord[][];
}

export interface ProofGroupPayload {
  id: string;
  label: string;
  semanticKind: SemanticKind;
  termIds: string[];
}

export interface ProofPayload {
  verified: true;
  residualZero: true;
  identityLatex: string;
  terms: ProofTermPayload[];
  steps: ProofStepPayload[];
  groups: ProofGroupPayload[];
}

export interface CounterexamplePayload {
  coordinates: [RationalRecord, RationalRecord, RationalRecord];
  value: RationalRecord;
  evaluationLatex: string;
}

export interface ProofResponse {
  schema: typeof PROOF_RESPONSE_SCHEMA_NAME;
  schemaVersion: typeof PROOF_SCHEMA_VERSION;
  outcome: ProofOutcome;
  method: string | null;
  target: PolynomialPayload;
  proof: ProofPayload | null;
  counterexample: CounterexamplePayload | null;
  diagnostics: DiagnosticPayload[];
}

const REQUEST_RATIONAL_PATTERN =
  "^-?(?:0|[1-9][0-9]{0,63})(?:/[1-9][0-9]{0,63})?$";
const REQUEST_RATIONAL = new RegExp(REQUEST_RATIONAL_PATTERN);
const INTEGER = /^(?:0|-?[1-9][0-9]*)$/;
const POSITIVE_INTEGER = /^[1-9][0-9]*$/;
const IDENTIFIER = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;

/** Fastify's structural request schema; dependent row lengths are checked in code. */
export const proofRequestJsonSchema = {
  $id: "triangle-method-proof-request-v1",
  type: "object",
  additionalProperties: false,
  required: ["schema", "schemaVersion", "degree", "coefficientRows"],
  properties: {
    schema: { const: PROOF_REQUEST_SCHEMA_NAME },
    schemaVersion: { const: PROOF_SCHEMA_VERSION },
    degree: {
      type: "integer",
      minimum: MINIMUM_SUPPORTED_DEGREE,
      maximum: MAXIMUM_SUPPORTED_DEGREE,
    },
    coefficientRows: {
      type: "array",
      minItems: MINIMUM_SUPPORTED_DEGREE + 1,
      maxItems: MAXIMUM_SUPPORTED_DEGREE + 1,
      items: {
        type: "array",
        minItems: 1,
        maxItems: MAXIMUM_SUPPORTED_DEGREE + 1,
        items: {
          type: "string",
          pattern: REQUEST_RATIONAL_PATTERN,
        },
      },
    },
  },
} as const;

export class ContractValidationError extends Error {
  readonly path: string;

  constructor(path: string, message: string) {
    super(`${path}: ${message}`);
    this.name = "ContractValidationError";
    this.path = path;
  }
}

function fail(path: string, message: string): never {
  throw new ContractValidationError(path, message);
}

function asRecord(value: unknown, path: string): Record<string, unknown> {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    fail(path, "must be an object");
  }
  return value as Record<string, unknown>;
}

function requireExactKeys(
  record: Record<string, unknown>,
  keys: readonly string[],
  path: string,
): void {
  const expected = new Set(keys);
  const actual = Object.keys(record);
  const missing = keys.filter((key) => !(key in record));
  const extra = actual.filter((key) => !expected.has(key));
  if (missing.length > 0 || extra.length > 0) {
    fail(
      path,
      `has invalid fields (missing: ${missing.join(", ") || "none"}; extra: ${extra.join(", ") || "none"})`,
    );
  }
}

function asArray(value: unknown, path: string): unknown[] {
  if (!Array.isArray(value)) {
    fail(path, "must be an array");
  }
  return value;
}

function asBoundedString(
  value: unknown,
  path: string,
  maximumLength: number,
): string {
  if (typeof value !== "string" || value.length === 0) {
    fail(path, "must be a nonempty string");
  }
  if (value.length > maximumLength) {
    fail(path, `must contain at most ${maximumLength} characters`);
  }
  return value;
}

function parseDegree(value: unknown, path: string): SupportedDegree {
  if (
    typeof value !== "number" ||
    !Number.isInteger(value) ||
    !SUPPORTED_DEGREES.includes(value as SupportedDegree)
  ) {
    fail(
      path,
      `must be an integer from ${MINIMUM_SUPPORTED_DEGREE} through ${MAXIMUM_SUPPORTED_DEGREE}`,
    );
  }
  return value as SupportedDegree;
}

function parseRequestCoefficient(value: unknown, path: string): string {
  if (typeof value !== "string" || !REQUEST_RATIONAL.test(value)) {
    fail(
      path,
      "must be an exact integer or fraction with at most 64 digits per part",
    );
  }
  if (value === "-0" || value.startsWith("-0/")) {
    fail(path, "must write zero canonically as 0");
  }
  return value;
}

function parseRequestRows(
  value: unknown,
  degree: SupportedDegree,
): string[][] {
  const rows = asArray(value, "coefficientRows");
  if (rows.length !== degree + 1) {
    fail("coefficientRows", `must contain exactly ${degree + 1} rows`);
  }
  return rows.map((rawRow, rowIndex) => {
    const row = asArray(rawRow, `coefficientRows[${rowIndex}]`);
    const expectedLength = rowIndex + 1;
    if (row.length !== expectedLength) {
      fail(
        `coefficientRows[${rowIndex}]`,
        `must contain exactly ${expectedLength} coefficients`,
      );
    }
    return row.map((coefficient, columnIndex) =>
      parseRequestCoefficient(
        coefficient,
        `coefficientRows[${rowIndex}][${columnIndex}]`,
      ),
    );
  });
}

/** Validate and copy an untrusted HTTP body into the exact proof-request model. */
export function parseProofRequest(value: unknown): ProofRequest {
  const record = asRecord(value, "request");
  requireExactKeys(
    record,
    ["schema", "schemaVersion", "degree", "coefficientRows"],
    "request",
  );
  if (record.schema !== PROOF_REQUEST_SCHEMA_NAME) {
    fail("request.schema", `must equal ${PROOF_REQUEST_SCHEMA_NAME}`);
  }
  if (record.schemaVersion !== PROOF_SCHEMA_VERSION) {
    fail("request.schemaVersion", `must equal ${PROOF_SCHEMA_VERSION}`);
  }
  const degree = parseDegree(record.degree, "request.degree");
  return {
    schema: PROOF_REQUEST_SCHEMA_NAME,
    schemaVersion: PROOF_SCHEMA_VERSION,
    degree,
    coefficientRows: parseRequestRows(record.coefficientRows, degree),
  };
}

function greatestCommonDivisor(left: bigint, right: bigint): bigint {
  let first = left < 0n ? -left : left;
  let second = right;
  while (second !== 0n) {
    [first, second] = [second, first % second];
  }
  return first;
}

function parseRationalRecord(value: unknown, path: string): RationalRecord {
  const record = asRecord(value, path);
  requireExactKeys(record, ["numerator", "denominator"], path);
  if (typeof record.numerator !== "string" || !INTEGER.test(record.numerator)) {
    fail(`${path}.numerator`, "must be a canonical decimal integer string");
  }
  if (
    typeof record.denominator !== "string" ||
    !POSITIVE_INTEGER.test(record.denominator)
  ) {
    fail(`${path}.denominator`, "must be a positive decimal integer string");
  }
  const numerator = BigInt(record.numerator);
  const denominator = BigInt(record.denominator);
  if (numerator === 0n && denominator !== 1n) {
    fail(path, "must encode zero with denominator 1");
  }
  if (greatestCommonDivisor(numerator, denominator) !== 1n) {
    fail(path, "must be reduced to lowest terms");
  }
  return { numerator: record.numerator, denominator: record.denominator };
}

function parseRationalRows(
  value: unknown,
  degree: SupportedDegree,
  path: string,
): RationalRecord[][] {
  const rows = asArray(value, path);
  if (rows.length !== degree + 1) {
    fail(path, `must contain exactly ${degree + 1} rows`);
  }
  return rows.map((rawRow, rowIndex) => {
    const rowPath = `${path}[${rowIndex}]`;
    const row = asArray(rawRow, rowPath);
    if (row.length !== rowIndex + 1) {
      fail(rowPath, `must contain exactly ${rowIndex + 1} coefficients`);
    }
    return row.map((coefficient, columnIndex) =>
      parseRationalRecord(coefficient, `${rowPath}[${columnIndex}]`),
    );
  });
}

function parseIdentifier(value: unknown, path: string): string {
  if (typeof value !== "string" || !IDENTIFIER.test(value)) {
    fail(path, "must be a nonempty stable identifier");
  }
  return value;
}

function parseDiagnostic(value: unknown, index: number): DiagnosticPayload {
  const path = `response.diagnostics[${index}]`;
  const record = asRecord(value, path);
  requireExactKeys(record, ["code", "message"], path);
  return {
    code: parseIdentifier(record.code, `${path}.code`),
    message: asBoundedString(record.message, `${path}.message`, 4096),
  };
}

function parsePolynomial(value: unknown): PolynomialPayload {
  const path = "response.target";
  const record = asRecord(value, path);
  requireExactKeys(record, ["degree", "coefficientRows", "latex"], path);
  const degree = parseDegree(record.degree, `${path}.degree`);
  return {
    degree,
    coefficientRows: parseRationalRows(
      record.coefficientRows,
      degree,
      `${path}.coefficientRows`,
    ),
    latex: asBoundedString(record.latex, `${path}.latex`, 100_000),
  };
}

function parseTerm(
  value: unknown,
  index: number,
  degree: SupportedDegree,
): ProofTermPayload {
  const path = `response.proof.terms[${index}]`;
  const record = asRecord(value, path);
  requireExactKeys(
    record,
    [
      "id",
      "kind",
      "weight",
      "expressionLatex",
      "weightedExpressionLatex",
      "contributionRows",
    ],
    path,
  );
  if (!(["square", "schur", "monomial"] as unknown[]).includes(record.kind)) {
    fail(`${path}.kind`, "must identify a supported primitive kind");
  }
  return {
    id: parseIdentifier(record.id, `${path}.id`),
    kind: record.kind as TermKind,
    weight: parseRationalRecord(record.weight, `${path}.weight`),
    expressionLatex: asBoundedString(
      record.expressionLatex,
      `${path}.expressionLatex`,
      100_000,
    ),
    weightedExpressionLatex: asBoundedString(
      record.weightedExpressionLatex,
      `${path}.weightedExpressionLatex`,
      100_000,
    ),
    contributionRows: parseRationalRows(
      record.contributionRows,
      degree,
      `${path}.contributionRows`,
    ),
  };
}

function parseStep(
  value: unknown,
  index: number,
  degree: SupportedDegree,
  termIds: ReadonlySet<string>,
): ProofStepPayload {
  const path = `response.proof.steps[${index}]`;
  const record = asRecord(value, path);
  requireExactKeys(
    record,
    ["componentId", "accumulatedRows", "remainderRows"],
    path,
  );
  const componentId = parseIdentifier(record.componentId, `${path}.componentId`);
  if (!termIds.has(componentId)) {
    fail(`${path}.componentId`, "must refer to a certificate term");
  }
  return {
    componentId,
    accumulatedRows: parseRationalRows(
      record.accumulatedRows,
      degree,
      `${path}.accumulatedRows`,
    ),
    remainderRows: parseRationalRows(
      record.remainderRows,
      degree,
      `${path}.remainderRows`,
    ),
  };
}

function parseGroup(
  value: unknown,
  index: number,
  termIds: ReadonlySet<string>,
): ProofGroupPayload {
  const path = `response.proof.groups[${index}]`;
  const record = asRecord(value, path);
  requireExactKeys(record, ["id", "label", "semanticKind", "termIds"], path);
  if (
    !(
      ["cauchy", "am_gm", "schur", "square", "monomial"] as unknown[]
    ).includes(record.semanticKind)
  ) {
    fail(`${path}.semanticKind`, "must identify a supported semantic group");
  }
  const rawTermIds = asArray(record.termIds, `${path}.termIds`);
  if (rawTermIds.length === 0) {
    fail(`${path}.termIds`, "must contain at least one term identifier");
  }
  const parsedTermIds = rawTermIds.map((termId, termIndex) => {
    const parsed = parseIdentifier(termId, `${path}.termIds[${termIndex}]`);
    if (!termIds.has(parsed)) {
      fail(`${path}.termIds[${termIndex}]`, "must refer to a certificate term");
    }
    return parsed;
  });
  if (new Set(parsedTermIds).size !== parsedTermIds.length) {
    fail(`${path}.termIds`, "cannot contain duplicate term identifiers");
  }
  return {
    id: parseIdentifier(record.id, `${path}.id`),
    label: asBoundedString(record.label, `${path}.label`, 256),
    semanticKind: record.semanticKind as SemanticKind,
    termIds: parsedTermIds,
  };
}

function parseProof(value: unknown, degree: SupportedDegree): ProofPayload {
  const path = "response.proof";
  const record = asRecord(value, path);
  requireExactKeys(
    record,
    [
      "verified",
      "residualZero",
      "identityLatex",
      "terms",
      "steps",
      "groups",
    ],
    path,
  );
  if (record.verified !== true || record.residualZero !== true) {
    fail(path, "must carry an exactly verified zero-residual certificate");
  }
  const terms = asArray(record.terms, `${path}.terms`).map((term, index) =>
    parseTerm(term, index, degree),
  );
  const termIds = new Set(terms.map((term) => term.id));
  if (termIds.size !== terms.length) {
    fail(`${path}.terms`, "must use unique term identifiers");
  }
  const steps = asArray(record.steps, `${path}.steps`).map((step, index) =>
    parseStep(step, index, degree, termIds),
  );
  const stepIds = steps.map((step) => step.componentId);
  if (
    stepIds.length !== terms.length ||
    new Set(stepIds).size !== stepIds.length ||
    stepIds.some((id) => !termIds.has(id))
  ) {
    fail(`${path}.steps`, "must contain exactly one step for each certificate term");
  }
  const groups = asArray(record.groups, `${path}.groups`).map((group, index) =>
    parseGroup(group, index, termIds),
  );
  if (new Set(groups.map((group) => group.id)).size !== groups.length) {
    fail(`${path}.groups`, "must use unique group identifiers");
  }
  const groupedTermIds = groups.flatMap((group) => group.termIds);
  if (
    groupedTermIds.length !== terms.length ||
    new Set(groupedTermIds).size !== groupedTermIds.length ||
    groupedTermIds.some((id) => !termIds.has(id))
  ) {
    fail(`${path}.groups`, "must place every certificate term in exactly one group");
  }
  return {
    verified: true,
    residualZero: true,
    identityLatex: asBoundedString(
      record.identityLatex,
      `${path}.identityLatex`,
      100_000,
    ),
    terms,
    steps,
    groups,
  };
}

function parseCounterexample(value: unknown): CounterexamplePayload {
  const path = "response.counterexample";
  const record = asRecord(value, path);
  requireExactKeys(record, ["coordinates", "value", "evaluationLatex"], path);
  const coordinates = asArray(record.coordinates, `${path}.coordinates`);
  if (coordinates.length !== 3) {
    fail(`${path}.coordinates`, "must contain exactly three coordinates");
  }
  const parsedCoordinates = coordinates.map((coordinate, index) =>
    parseRationalRecord(coordinate, `${path}.coordinates[${index}]`),
  ) as [RationalRecord, RationalRecord, RationalRecord];
  const evaluatedValue = parseRationalRecord(record.value, `${path}.value`);
  if (!evaluatedValue.numerator.startsWith("-")) {
    fail(`${path}.value`, "must be strictly negative");
  }
  return {
    coordinates: parsedCoordinates,
    value: evaluatedValue,
    evaluationLatex: asBoundedString(
      record.evaluationLatex,
      `${path}.evaluationLatex`,
      100_000,
    ),
  };
}

/** Validate and copy an untrusted Python result before it reaches Fastify. */
export function parseProofResponse(value: unknown): ProofResponse {
  const record = asRecord(value, "response");
  requireExactKeys(
    record,
    [
      "schema",
      "schemaVersion",
      "outcome",
      "method",
      "target",
      "proof",
      "counterexample",
      "diagnostics",
    ],
    "response",
  );
  if (record.schema !== PROOF_RESPONSE_SCHEMA_NAME) {
    fail("response.schema", `must equal ${PROOF_RESPONSE_SCHEMA_NAME}`);
  }
  if (record.schemaVersion !== PROOF_SCHEMA_VERSION) {
    fail("response.schemaVersion", `must equal ${PROOF_SCHEMA_VERSION}`);
  }
  if (!(["PROVED", "DISPROVED", "UNKNOWN"] as unknown[]).includes(record.outcome)) {
    fail("response.outcome", "must be PROVED, DISPROVED, or UNKNOWN");
  }
  if (
    record.method !== null &&
    (typeof record.method !== "string" || record.method.length === 0)
  ) {
    fail("response.method", "must be null or a nonempty string");
  }

  const target = parsePolynomial(record.target);
  const diagnostics = asArray(record.diagnostics, "response.diagnostics").map(
    parseDiagnostic,
  );
  const outcome = record.outcome as ProofOutcome;
  let proof: ProofPayload | null = null;
  let counterexample: CounterexamplePayload | null = null;

  if (outcome === "PROVED") {
    if (record.method === null || record.proof === null || record.counterexample !== null) {
      fail(
        "response",
        "a PROVED outcome requires a method and proof, with no counterexample",
      );
    }
    proof = parseProof(record.proof, target.degree);
  } else if (outcome === "DISPROVED") {
    if (record.method === null || record.proof !== null || record.counterexample === null) {
      fail(
        "response",
        "a DISPROVED outcome requires a method and counterexample, with no proof",
      );
    }
    counterexample = parseCounterexample(record.counterexample);
  } else {
    if (
      record.method !== null ||
      record.proof !== null ||
      record.counterexample !== null
    ) {
      fail("response", "an UNKNOWN outcome cannot contain mathematical evidence");
    }
    if (diagnostics.length === 0) {
      fail("response.diagnostics", "must explain an UNKNOWN outcome");
    }
  }

  return {
    schema: PROOF_RESPONSE_SCHEMA_NAME,
    schemaVersion: PROOF_SCHEMA_VERSION,
    outcome,
    method: record.method as string | null,
    target,
    proof,
    counterexample,
    diagnostics,
  };
}

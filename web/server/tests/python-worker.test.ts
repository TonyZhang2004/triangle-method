// @vitest-environment node

import path from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import {
  PythonWorkerExitError,
  PythonWorkerOutputLimitError,
  PythonWorkerProtocolError,
  PythonWorkerTimeoutError,
  PythonWorkerUnavailableError,
  RequestAbortedError,
} from "../src/errors.js";
import { createPythonProofExecutor } from "../src/python-worker.js";
import { proofRequest } from "./test-helpers.js";

const fixture = path.join(
  path.dirname(fileURLToPath(import.meta.url)),
  "fixtures",
  "fake-worker.mjs",
);
const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");

function fakeExecutor(
  mode: string,
  options: { timeoutMilliseconds?: number; stdoutLimitBytes?: number; stderrLimitBytes?: number } = {},
) {
  return createPythonProofExecutor({
    projectRoot,
    command: { executable: process.execPath, arguments: [fixture, mode] },
    ...options,
  });
}

describe("Python proof worker", () => {
  it("writes one request and validates one exact response", async () => {
    const request = proofRequest();
    request.coefficientRows[0][0] = "2/4";

    const response = await fakeExecutor("success")(
      request,
      new AbortController().signal,
    );

    expect(response.outcome).toBe("PROVED");
    expect(response.target.coefficientRows[0][0]).toEqual({
      numerator: "1",
      denominator: "2",
    });
  });

  it("enforces the wall-clock timeout", async () => {
    const result = fakeExecutor("hang", { timeoutMilliseconds: 25 })(
      proofRequest(),
      new AbortController().signal,
    );

    await expect(result).rejects.toBeInstanceOf(PythonWorkerTimeoutError);
  });

  it.each([
    ["stdout-limit", "stdoutLimitBytes"],
    ["stderr-limit", "stderrLimitBytes"],
  ] as const)("caps %s", async (mode, limitName) => {
    const executor = fakeExecutor(mode, { [limitName]: 128 });

    await expect(
      executor(proofRequest(), new AbortController().signal),
    ).rejects.toBeInstanceOf(PythonWorkerOutputLimitError);
  });

  it.each(["bad-json", "invalid-contract", "mismatch"])(
    "rejects the %s worker response",
    async (mode) => {
      await expect(
        fakeExecutor(mode)(proofRequest(), new AbortController().signal),
      ).rejects.toBeInstanceOf(PythonWorkerProtocolError);
    },
  );

  it("reports nonzero worker exits without exposing them as math outcomes", async () => {
    await expect(
      fakeExecutor("failure")(proofRequest(), new AbortController().signal),
    ).rejects.toBeInstanceOf(PythonWorkerExitError);
  });

  it("reports an unavailable executable as a service failure", async () => {
    const executor = createPythonProofExecutor({
      projectRoot,
      command: {
        executable: path.join(projectRoot, ".missing-python"),
        arguments: [],
      },
    });

    await expect(
      executor(proofRequest(), new AbortController().signal),
    ).rejects.toBeInstanceOf(PythonWorkerUnavailableError);
  });

  it("kills a worker when the caller disconnects", async () => {
    const controller = new AbortController();
    const result = fakeExecutor("hang")(
      proofRequest(),
      controller.signal,
    );

    controller.abort();

    await expect(result).rejects.toBeInstanceOf(RequestAbortedError);
  });

  it("runs the real Python adapter through the fixed production command", async () => {
    const request = proofRequest();
    request.coefficientRows = [["1"], ["-1", "-1"], ["1", "-1", "1"]];

    const response = await createPythonProofExecutor({ projectRoot })(
      request,
      new AbortController().signal,
    );

    expect(response.outcome).toBe("PROVED");
    expect(response.proof?.verified).toBe(true);
    expect(response.proof?.terms).toHaveLength(3);
  });

  it(
    "proves a degree-12 lifted Cauchy inequality through the production worker",
    async () => {
      const request = proofRequest(12);
      request.coefficientRows[0] = ["1"];
      request.coefficientRows[1] = ["-1", "-1"];
      request.coefficientRows[2] = ["1", "-1", "1"];

      const response = await createPythonProofExecutor({ projectRoot })(
        request,
        new AbortController().signal,
      );

      expect(response.outcome).toBe("PROVED");
      expect(response.method).toBe("candidate_combination");
      expect(response.target.degree).toBe(12);
      expect(response.target.coefficientRows.flat()).toHaveLength(91);
      expect(response.proof?.terms).toHaveLength(3);
      expect(response.proof?.groups).toEqual([
        {
          id: "group-1",
          label: "Cauchy",
          semanticKind: "cauchy",
          termIds: ["component-1", "component-2", "component-3"],
        },
      ]);
      expect(
        response.proof?.steps.at(-1)?.remainderRows
          .flat()
          .every((coefficient) => coefficient.numerator === "0"),
      ).toBe(true);
    },
    15_000,
  );

  it(
    "transports a dense degree-12 certificate with long exact coefficients",
    async () => {
      const request = proofRequest(12);
      const coefficient = `${"9".repeat(64)}/${"8".repeat(63)}7`;
      request.coefficientRows = request.coefficientRows.map((row) =>
        row.map(() => coefficient),
      );

      const response = await createPythonProofExecutor({ projectRoot })(
        request,
        new AbortController().signal,
      );

      expect(response.outcome).toBe("PROVED");
      expect(response.target.degree).toBe(12);
      expect(response.target.coefficientRows.flat()).toHaveLength(91);
      expect(response.proof?.verified).toBe(true);
      expect(response.proof?.terms).toHaveLength(91);
    },
    15_000,
  );

  it.each([
    {
      outcome: "DISPROVED",
      rows: [["1"], ["-4", "0"], ["1", "0", "1"]],
    },
    {
      outcome: "UNKNOWN",
      rows: [["1"], ["-10", "0"], ["100", "0", "0"]],
    },
  ] as const)(
    "preserves the Python backend's $outcome mathematical outcome",
    async ({ outcome, rows }) => {
      const request = proofRequest();
      request.coefficientRows = rows.map((row) => [...row]);

      const response = await createPythonProofExecutor({ projectRoot })(
        request,
        new AbortController().signal,
      );

      expect(response.outcome).toBe(outcome);
      expect(response.proof === null).toBe(outcome !== "PROVED");
      expect(response.counterexample === null).toBe(outcome !== "DISPROVED");
    },
  );
});

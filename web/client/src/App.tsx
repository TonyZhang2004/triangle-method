import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";

import { requestProof } from "./api";
import { CoefficientTriangleEditor } from "./components/CoefficientTriangleEditor";
import { MathFormula } from "./components/MathFormula";
import { ProofResultView } from "./components/ProofResultView";
import {
  coefficientRowsToLatex,
  emptyCoefficientRows,
  normalizeCoefficientRows,
  parseExactRational,
} from "./exact";
import type { ProofResponse, SupportedDegree } from "./types";

type RequestState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "result"; result: ProofResponse }
  | { kind: "error"; message: string };

const DEGREES = [2, 3, 4, 5] as const;

function initialDrafts(): Record<number, string[][]> {
  return Object.fromEntries(
    DEGREES.map((degree) => [degree, emptyCoefficientRows(degree)]),
  );
}

/** Provide the complete titleless coefficient-entry and exact-proof workflow. */
export default function App() {
  const [degree, setDegree] = useState<SupportedDegree>(3);
  const [drafts, setDrafts] = useState<Record<number, string[][]>>(initialDrafts);
  const [visibleErrors, setVisibleErrors] = useState<Map<string, string>>(new Map());
  const [validationActive, setValidationActive] = useState(false);
  const [requestState, setRequestState] = useState<RequestState>({ kind: "idle" });
  const requestController = useRef<AbortController | null>(null);
  const form = useRef<HTMLFormElement>(null);
  const currentRows = drafts[degree];
  const validation = useMemo(
    () => normalizeCoefficientRows(currentRows),
    [currentRows],
  );
  const previewLatex = useMemo(
    () => coefficientRowsToLatex(degree, currentRows),
    [currentRows, degree],
  );

  useEffect(
    () => () => {
      requestController.current?.abort();
    },
    [],
  );

  function clearStaleResult() {
    requestController.current?.abort();
    requestController.current = null;
    setRequestState({ kind: "idle" });
  }

  function changeDegree(nextDegree: SupportedDegree) {
    setDegree(nextDegree);
    setVisibleErrors(new Map());
    setValidationActive(false);
    clearStaleResult();
  }

  function changeCoefficient(row: number, column: number, value: string) {
    setDrafts((current) => ({
      ...current,
      [degree]: current[degree].map((values, rowIndex) =>
        rowIndex === row
          ? values.map((coefficient, columnIndex) =>
              columnIndex === column ? value : coefficient,
            )
          : values,
      ),
    }));
    if (validationActive) {
      setVisibleErrors((current) => {
        const next = new Map(current);
        const parsed = parseExactRational(value);
        if (parsed.ok) {
          next.delete(`${row}:${column}`);
        } else {
          next.set(`${row}:${column}`, parsed.message);
        }
        return next;
      });
    }
    clearStaleResult();
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (validation.errors.size) {
      setValidationActive(true);
      setVisibleErrors(validation.errors);
      const [firstKey] = validation.errors.keys();
      const [row, column] = firstKey.split(":");
      requestAnimationFrame(() => {
        document.getElementById(`coefficient-${degree}-${row}-${column}`)?.focus();
      });
      return;
    }

    requestController.current?.abort();
    const controller = new AbortController();
    requestController.current = controller;
    setVisibleErrors(new Map());
    setValidationActive(false);
    setRequestState({ kind: "loading" });
    try {
      const result = await requestProof(
        {
          schema: "triangle_method.proof_request",
          schemaVersion: 1,
          degree,
          coefficientRows: validation.rows,
        },
        controller.signal,
      );
      if (requestController.current !== controller) return;
      requestController.current = null;
      setRequestState({ kind: "result", result });
    } catch (error) {
      if (controller.signal.aborted) return;
      requestController.current = null;
      setRequestState({
        kind: "error",
        message:
          error instanceof Error
            ? error.message
            : "The proof service returned an unexpected error.",
      });
    }
  }

  return (
    <main className="app-shell">
      <form className="proof-form" onSubmit={submit} noValidate ref={form}>
        <div className="degree-control">
          <label htmlFor="degree">Degree</label>
          <select
            id="degree"
            value={degree}
            onChange={(event) =>
              changeDegree(Number(event.currentTarget.value) as SupportedDegree)
            }
          >
            {DEGREES.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </div>

        <p className="input-instruction">
          Enter the coefficients of <i>F</i> in <i>F</i>(x,y,z) ≥ 0.
        </p>

        <CoefficientTriangleEditor
          degree={degree}
          rows={currentRows}
          errors={visibleErrors}
          onChange={changeCoefficient}
        />

        {visibleErrors.size ? (
          <div className="validation-summary" role="alert">
            Fix {visibleErrors.size} invalid {visibleErrors.size === 1 ? "coefficient" : "coefficients"}.
            Use integers or exact fractions such as -3/4.
          </div>
        ) : null}

        <div className="inequality-preview formula-scroll" aria-live="polite">
          {previewLatex === null ? (
            <span>Enter a valid coefficient to preview the inequality.</span>
          ) : (
            <MathFormula
              latex={`${previewLatex} \\ge 0`}
              accessibleLabel="Current inequality preview"
              display
            />
          )}
        </div>

        <button
          className="prove-button"
          type="submit"
          disabled={requestState.kind === "loading"}
        >
          {requestState.kind === "loading" ? "Searching…" : "Prove"}
        </button>
        <span className="sr-only" role="status" aria-live="polite">
          {requestState.kind === "loading"
            ? "Searching for an exact proof certificate."
            : ""}
        </span>
      </form>

      {requestState.kind === "error" ? (
        <div className="service-error" role="alert">
          <p>{requestState.message}</p>
          <button type="button" onClick={() => form.current?.requestSubmit()}>
            Retry
          </button>
        </div>
      ) : null}

      {requestState.kind === "result" ? (
        <ProofResultView result={requestState.result} />
      ) : null}
    </main>
  );
}

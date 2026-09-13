import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type FormEvent,
} from "react";

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
import { useVisibleViewportHeight } from "./responsive";
import type { ProofResponse, SupportedDegree } from "./types";

type RequestState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "result"; result: ProofResponse }
  | { kind: "error"; message: string };

const DEGREES = [
  2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12,
] as const satisfies readonly SupportedDegree[];
type EditorDegree = (typeof DEGREES)[number];
type AppView = "editor" | "proof";

const PROOF_FRAGMENT = "#proof";

/** Return the current address without the in-memory proof-page fragment. */
function editorUrl(): string {
  return `${window.location.pathname}${window.location.search}`;
}

/** Create one independent empty coefficient draft for every selectable degree. */
function initialDrafts(): Record<EditorDegree, string[][]> {
  return Object.fromEntries(
    DEGREES.map((degree) => [degree, emptyCoefficientRows(degree)]),
  ) as Record<EditorDegree, string[][]>;
}

/** Narrow a numeric select value to the degrees exposed by this editor. */
function isEditorDegree(value: number): value is EditorDegree {
  return (DEGREES as readonly number[]).includes(value);
}

/** Provide the complete titleless coefficient-entry and exact-proof workflow. */
export default function App() {
  const [view, setView] = useState<AppView>("editor");
  const [degree, setDegree] = useState<EditorDegree>(3);
  const [drafts, setDrafts] = useState<Record<EditorDegree, string[][]>>(
    initialDrafts,
  );
  const [visibleErrors, setVisibleErrors] = useState<Map<string, string>>(new Map());
  const [validationActive, setValidationActive] = useState(false);
  const [requestState, setRequestState] = useState<RequestState>({ kind: "idle" });
  const requestController = useRef<AbortController | null>(null);
  const form = useRef<HTMLFormElement>(null);
  const loadingStatus = useRef<HTMLDivElement>(null);
  const resultHeading = useRef<HTMLHeadingElement>(null);
  const restoreEditorFocus = useRef(false);
  const historyReturnPending = useRef(false);
  const visibleViewportHeight = useVisibleViewportHeight();
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

  useEffect(() => {
    const synchronizeView = () => {
      if (
        window.location.hash === PROOF_FRAGMENT &&
        (requestState.kind === "loading" || requestState.kind === "result")
      ) {
        setView("proof");
        return;
      }
      if (window.location.hash === PROOF_FRAGMENT) {
        if (window.history.state?.triangleMethodView === "proof") {
          if (!historyReturnPending.current) {
            historyReturnPending.current = true;
            window.history.back();
          }
          setView("editor");
          return;
        }
        window.history.replaceState(null, "", editorUrl());
      } else {
        historyReturnPending.current = false;
      }
      if (requestState.kind !== "idle") {
        restoreEditorFocus.current = true;
        requestAnimationFrame(() => document.getElementById("degree")?.focus());
      }
      if (requestState.kind === "loading") {
        requestController.current?.abort();
        requestController.current = null;
        setRequestState({ kind: "idle" });
      }
      setView("editor");
    };

    window.addEventListener("popstate", synchronizeView);
    window.addEventListener("hashchange", synchronizeView);
    synchronizeView();
    return () => {
      window.removeEventListener("popstate", synchronizeView);
      window.removeEventListener("hashchange", synchronizeView);
    };
  }, [requestState.kind]);

  useEffect(() => {
    if (view === "proof" && requestState.kind === "loading") {
      requestAnimationFrame(() => loadingStatus.current?.focus());
    } else if (view === "proof" && requestState.kind === "result") {
      requestAnimationFrame(() => resultHeading.current?.focus());
    } else if (restoreEditorFocus.current) {
      restoreEditorFocus.current = false;
      requestAnimationFrame(() => document.getElementById("degree")?.focus());
    }
  }, [requestState.kind, view]);

  function clearStaleResult() {
    requestController.current?.abort();
    requestController.current = null;
    setRequestState({ kind: "idle" });
    setView("editor");
  }

  /** Return to the preserved coefficient draft and restore keyboard focus. */
  function returnToEditor() {
    restoreEditorFocus.current = true;
    if (requestState.kind === "loading") {
      requestController.current?.abort();
      requestController.current = null;
      setRequestState({ kind: "idle" });
    }
    if (
      window.location.hash === PROOF_FRAGMENT &&
      window.history.state?.triangleMethodView === "proof"
    ) {
      historyReturnPending.current = true;
      setView("editor");
      window.history.back();
      return;
    }
    if (window.location.hash === PROOF_FRAGMENT) {
      window.history.replaceState(null, "", editorUrl());
    }
    setView("editor");
  }

  function changeDegree(nextDegree: EditorDegree) {
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

  /** Replace one complete coefficient row after a structured row-paste action. */
  function changeCoefficientRow(row: number, values: string[]) {
    setDrafts((current) => ({
      ...current,
      [degree]: current[degree].map((currentValues, rowIndex) =>
        rowIndex === row ? [...values] : currentValues,
      ),
    }));
    if (validationActive) {
      setVisibleErrors((current) => {
        const next = new Map(current);
        values.forEach((value, column) => {
          const key = `${row}:${column}`;
          const parsed = parseExactRational(value);
          if (parsed.ok) next.delete(key);
          else next.set(key, parsed.message);
        });
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
    if (window.location.hash !== PROOF_FRAGMENT) {
      window.history.pushState(
        { triangleMethodView: "proof" },
        "",
        `${editorUrl()}${PROOF_FRAGMENT}`,
      );
    }
    setView("proof");
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

  const shellStyle = visibleViewportHeight
    ? ({ "--app-height": `${visibleViewportHeight}px` } as CSSProperties)
    : undefined;
  const compactHeight =
    visibleViewportHeight > 0 && visibleViewportHeight < 480;

  if (
    view === "proof" &&
    (requestState.kind === "loading" || requestState.kind === "result")
  ) {
    return (
      <main
        className="app-shell result-page-shell"
        data-testid="proof-page"
        style={shellStyle}
      >
        <header className="result-page-header">
          <button
            className="back-to-editor-button"
            type="button"
            onClick={returnToEditor}
          >
            <span aria-hidden="true">←</span> Back to inequality
          </button>
        </header>
        <div className="result-page-scroll" data-testid="result-page-scroll">
          {requestState.kind === "loading" ? (
            <div
              className="proof-loading"
              role="status"
              aria-live="polite"
              tabIndex={-1}
              ref={loadingStatus}
            >
              <span className="proof-loading-mark" aria-hidden="true" />
              <p>Searching for an exact proof certificate…</p>
            </div>
          ) : (
            <ProofResultView
              result={requestState.result}
              headingRef={resultHeading}
            />
          )}
        </div>
      </main>
    );
  }

  return (
    <main
      className={`app-shell input-page-shell${
        compactHeight ? " compact-height" : ""
      }`}
      data-testid="editor-page"
      style={shellStyle}
    >
      <form className="proof-form" onSubmit={submit} noValidate ref={form}>
        <div className="degree-control">
          <label htmlFor="degree">Degree</label>
          <select
            id="degree"
            value={degree}
            onChange={(event) => {
              const nextDegree = Number(event.currentTarget.value);
              if (isEditorDegree(nextDegree)) changeDegree(nextDegree);
            }}
          >
            {DEGREES.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </div>

        <p className="input-instruction">
          <MathFormula
            latex={String.raw`\text{Enter the coefficients of } F \text{ in } F(x,y,z) \ge 0.`}
            accessibleLabel="Enter the coefficients of F in F of x, y, z greater than or equal to zero."
          />
        </p>

        <CoefficientTriangleEditor
          degree={degree}
          rows={currentRows}
          errors={visibleErrors}
          onChange={changeCoefficient}
          onChangeRow={changeCoefficientRow}
        />

        {visibleErrors.size ? (
          <div className="validation-summary" role="alert">
            Fix {visibleErrors.size} invalid {visibleErrors.size === 1 ? "coefficient" : "coefficients"}.
            Use integers or exact fractions such as -3/4.
          </div>
        ) : null}

        {requestState.kind === "error" ? (
          <div className="service-error" role="alert">
            <p>{requestState.message}</p>
            <button type="button" onClick={() => form.current?.requestSubmit()}>
              Retry
            </button>
          </div>
        ) : null}

        <div className="proof-action-dock">
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
          <div className="proof-button-bar">
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
          </div>
        </div>
      </form>
    </main>
  );
}

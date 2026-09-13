import { useEffect, useMemo, useState, type Ref } from "react";

import { termColorClasses } from "../colors";
import type {
  PresentationGroup,
  ProofPresentation,
  ProofResponse,
  ProofTerm,
  RationalRecord,
} from "../types";
import { CoefficientTriangle } from "./CoefficientTriangle";
import { MathFormula } from "./MathFormula";

type TriangleMode = "target" | "component" | "accumulated" | "remainder";

type ProofResultViewProps = {
  result: ProofResponse;
  headingRef?: Ref<HTMLHeadingElement>;
};

function inequalityLatex(targetLatex: string): string {
  return /\\(?:ge|geq|gt|le|leq)\b/.test(targetLatex)
    ? targetLatex
    : `${targetLatex} \\ge 0`;
}

function primitiveLabel(term: ProofTerm): string {
  if (term.kind === "square") return "Completed square";
  if (term.kind === "schur") return "Schur component";
  return "Nonnegative monomial";
}

function shortIdentifier(identifier: string, prefix: string): string {
  const suffix = /(\d+)$/.exec(identifier)?.[1];
  return suffix ? `${prefix}${suffix}` : identifier;
}

function groupForTerm(
  groups: PresentationGroup[],
  termId: string,
): PresentationGroup | undefined {
  return groups.find((group) => group.termIds.includes(termId));
}

function proofHeading(proof: ProofPresentation): string {
  return proof.terms.length > 0 &&
    proof.terms.every((term) => term.kind === "square")
    ? "Squares completed"
    : "Nonnegative decomposition";
}

function targetExpressionLatex(targetLatex: string): string {
  return targetLatex.replace(/\s*\\geq?\s*0\s*$/, "");
}

function ColoredProofIdentity({
  proof,
  targetLatex,
  colors,
}: {
  proof: ProofPresentation;
  targetLatex: string;
  colors: Map<string, string>;
}) {
  return (
    <div className="identity-formula formula-scroll">
      <div
        className="structured-proof-identity"
        role="math"
        aria-label={proof.identityLatex}
      >
        <MathFormula latex={targetExpressionLatex(targetLatex)} ariaHidden />
        <span className="identity-operator" aria-hidden="true">
          =
        </span>
        {proof.terms.length ? (
          proof.terms.map((term, index) => (
            <span className="identity-term-wrapper" key={term.id}>
              {index > 0 ? (
                <span className="identity-operator" aria-hidden="true">
                  +
                </span>
              ) : null}
              <span
                className={`identity-term ${colors.get(term.id) ?? "component-color-0"}`}
              >
                <MathFormula latex={term.weightedExpressionLatex} ariaHidden />
              </span>
            </span>
          ))
        ) : (
          <MathFormula latex="0" ariaHidden />
        )}
        <MathFormula latex={"\\ge 0"} ariaHidden className="identity-nonnegative" />
      </div>
    </div>
  );
}

function modeLabel(mode: TriangleMode, componentId: string): string {
  if (mode === "target") return "Target coefficient triangle";
  if (mode === "component") return `Component ${componentId}`;
  if (mode === "accumulated") return `Accumulated through ${componentId}`;
  return `Remainder after ${componentId}`;
}

function ProofCertificate({
  proof,
  targetRows,
  targetLatex,
}: {
  proof: ProofPresentation;
  targetRows: RationalRecord[][];
  targetLatex: string;
}) {
  const [mode, setMode] = useState<TriangleMode>("target");
  const [stepIndex, setStepIndex] = useState(0);
  const colors = useMemo(
    () => termColorClasses(proof.terms, proof.groups),
    [proof.groups, proof.terms],
  );

  useEffect(() => {
    setMode("target");
    setStepIndex(0);
  }, [proof]);

  const activeTerm = proof.terms[stepIndex];
  const activeStep = activeTerm
    ? proof.steps.find((step) => step.componentId === activeTerm.id)
    : undefined;
  let shownRows = targetRows;
  if (mode === "component" && activeTerm) {
    shownRows = activeTerm.contributionRows;
  } else if (mode === "accumulated" && activeStep) {
    shownRows = activeStep.accumulatedRows;
  } else if (mode === "remainder" && activeStep) {
    shownRows = activeStep.remainderRows;
  }
  const activeColor = activeTerm
    ? (colors.get(activeTerm.id) ?? "component-color-0")
    : "";
  const triangleLabel = modeLabel(mode, activeTerm?.id ?? "");
  const isLastStep =
    proof.terms.length > 0 && stepIndex === proof.terms.length - 1;

  return (
    <div className="proof-certificate">
      <h3>{proofHeading(proof)}</h3>
      <ColoredProofIdentity proof={proof} targetLatex={targetLatex} colors={colors} />

      {proof.groups.length ? (
        <ul className="component-groups" aria-label="Proof component groups">
          {proof.groups.map((group, index) => (
            <li className={`component-group component-color-${index % 8}`} key={group.id}>
              <span className="group-swatch" aria-hidden="true" />
              <span className="group-id">{shortIdentifier(group.id, "G")}</span>
              <span>{group.label}</span>
            </li>
          ))}
        </ul>
      ) : null}

      {proof.terms.length ? (
        <ol className="component-list" aria-label="Certificate components">
          {proof.terms.map((term, index) => {
            const group = groupForTerm(proof.groups, term.id);
            const selected = index === stepIndex;
            return (
              <li key={term.id}>
                <button
                  type="button"
                  className={`component-button ${colors.get(term.id) ?? "component-color-0"}`}
                  aria-pressed={selected}
                  aria-label={`${term.id}: ${group?.label ?? primitiveLabel(term)}, ${term.weightedExpressionLatex}`}
                  onClick={() => {
                    setStepIndex(index);
                    setMode("component");
                  }}
                >
                  <span className="component-id">{shortIdentifier(term.id, "C")}</span>
                  <MathFormula
                    latex={term.weightedExpressionLatex}
                    accessibleLabel={group?.label ?? primitiveLabel(term)}
                    ariaHidden
                  />
                </button>
              </li>
            );
          })}
        </ol>
      ) : (
        <p className="quiet-note">The zero polynomial needs no components.</p>
      )}

      <div
        className="triangle-mode-controls"
        role="group"
        aria-label="Coefficient triangle view"
      >
        {(["target", "component", "accumulated", "remainder"] as const).map(
          (candidateMode) => (
            <button
              type="button"
              key={candidateMode}
              aria-pressed={mode === candidateMode}
              disabled={candidateMode !== "target" && !activeStep}
              onClick={() => setMode(candidateMode)}
            >
              {candidateMode[0].toUpperCase() + candidateMode.slice(1)}
            </button>
          ),
        )}
      </div>

      <CoefficientTriangle
        rows={shownRows}
        label={triangleLabel}
        toneClass={mode === "component" ? activeColor : ""}
      />

      {proof.terms.length ? (
        <div className="step-controls">
          <button
            type="button"
            disabled={stepIndex === 0}
            onClick={() => setStepIndex((index) => Math.max(0, index - 1))}
          >
            Previous
          </button>
          <span aria-live="polite">
            Step {stepIndex + 1} of {proof.terms.length}
          </span>
          <button
            type="button"
            disabled={isLastStep}
            onClick={() =>
              setStepIndex((index) => Math.min(proof.terms.length - 1, index + 1))
            }
          >
            Next
          </button>
        </div>
      ) : null}

      <p className="verification-note">
        <span aria-hidden="true">✓</span> Exact certificate verified; final remainder is
        zero.
      </p>
    </div>
  );
}

function Diagnostics({ result }: { result: ProofResponse }) {
  if (!result.diagnostics.length) return null;
  return (
    <details className="diagnostics">
      <summary>Search details</summary>
      <ul>
        {result.diagnostics.map((item, index) => (
          <li key={`${item.code}:${index}`}>
            <span className="diagnostic-code">{item.code}</span> {item.message}
          </li>
        ))}
      </ul>
    </details>
  );
}

/** Render proved, disproved, and inconclusive outcomes with their exact evidence. */
export function ProofResultView({ result, headingRef }: ProofResultViewProps) {
  return (
    <section className="result-panel" aria-labelledby="result-status">
      <div className={`result-status result-status-${result.outcome.toLowerCase()}`}>
        <h2 id="result-status" ref={headingRef} tabIndex={-1}>
          {result.outcome === "PROVED"
            ? "Proved"
            : result.outcome === "DISPROVED"
              ? "Counterexample found"
              : "Search inconclusive"}
        </h2>
        {result.method ? (
          <span className="method-label">{result.method.replaceAll("_", " ")}</span>
        ) : null}
      </div>

      <div className="result-inequality formula-scroll">
        <MathFormula
          latex={inequalityLatex(result.target.latex)}
          accessibleLabel="Submitted inequality"
          display
        />
      </div>

      {result.outcome !== "PROVED" ? (
        <CoefficientTriangle
          rows={result.target.coefficientRows}
          label="Target coefficient triangle"
        />
      ) : null}

      {result.outcome === "PROVED" && result.proof ? (
        <ProofCertificate
          proof={result.proof}
          targetRows={result.target.coefficientRows}
          targetLatex={result.target.latex}
        />
      ) : null}

      {result.outcome === "DISPROVED" && result.counterexample ? (
        <div className="counterexample-evidence">
          <p>This exact nonnegative point makes the polynomial negative.</p>
          <div className="formula-scroll">
            <MathFormula
              latex={result.counterexample.evaluationLatex}
              accessibleLabel="Exact rational counterexample"
              display
            />
          </div>
        </div>
      ) : null}

      {result.outcome === "UNKNOWN" ? (
        <p className="unknown-explanation">
          No proof or counterexample was found within the current search limits. This
          does not decide whether the inequality is true.
        </p>
      ) : null}

      <Diagnostics result={result} />
    </section>
  );
}

import katex from "katex";
import { useMemo } from "react";

type MathFormulaProps = {
  latex: string;
  accessibleLabel?: string;
  display?: boolean;
  ariaHidden?: boolean;
  className?: string;
};

/** Render generated LaTeX with KaTeX while keeping trust-dependent commands disabled. */
export function MathFormula({
  latex,
  accessibleLabel,
  display = false,
  ariaHidden = false,
  className = "",
}: MathFormulaProps) {
  const html = useMemo(
    () =>
      katex.renderToString(latex, {
        displayMode: display,
        throwOnError: false,
        trust: false,
        strict: "warn",
        output: "html",
      }),
    [display, latex],
  );

  return (
    <span
      className={`math-formula ${display ? "math-formula-display" : ""} ${className}`.trim()}
      role={ariaHidden ? undefined : "math"}
      aria-label={ariaHidden ? undefined : (accessibleLabel ?? latex)}
      aria-hidden={ariaHidden || undefined}
    >
      <span dangerouslySetInnerHTML={{ __html: html }} />
    </span>
  );
}

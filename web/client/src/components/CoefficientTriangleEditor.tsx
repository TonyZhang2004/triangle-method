import { useLayoutEffect, useRef, type CSSProperties } from "react";

import {
  exponentAt,
  monomialLatex,
  monomialPlainText,
} from "../exact";
import { coordinateText, EQUILATERAL_ALTITUDE, trianglePoints } from "../geometry";
import { MathFormula } from "./MathFormula";

const INPUT_LATTICE_STEP = 156;
const INPUT_SIDE_PADDING = 76;
const INPUT_TOP_PADDING = 42;
const INPUT_BOTTOM_PADDING = 58;

type CoefficientTriangleEditorProps = {
  degree: number;
  rows: string[][];
  errors: Map<string, string>;
  onChange: (row: number, column: number, value: string) => void;
};

/** Render exact coefficient inputs on the canonical centered equilateral lattice. */
export function CoefficientTriangleEditor({
  degree,
  rows,
  errors,
  onChange,
}: CoefficientTriangleEditorProps) {
  const scrollContainer = useRef<HTMLDivElement>(null);
  const points = trianglePoints(degree, INPUT_LATTICE_STEP);
  const width = degree * INPUT_LATTICE_STEP + 2 * INPUT_SIDE_PADDING;
  const height =
    degree * INPUT_LATTICE_STEP * EQUILATERAL_ALTITUDE +
    INPUT_TOP_PADDING +
    INPUT_BOTTOM_PADDING;

  useLayoutEffect(() => {
    const element = scrollContainer.current;
    if (element) {
      element.scrollLeft = Math.max(0, (element.scrollWidth - element.clientWidth) / 2);
    }
  }, [degree]);

  return (
    <fieldset className="coefficient-fieldset">
      <legend className="sr-only">
        Coefficients of the homogeneous polynomial in canonical triangle order
      </legend>
      <div
        className="triangle-scroll"
        data-testid="coefficient-editor-scroll"
        ref={scrollContainer}
      >
        <div
          className="triangle-canvas input-triangle"
          style={{ width, height }}
          data-degree={degree}
        >
          {points.map((point) => {
            const exponent = exponentAt(degree, point.row, point.column);
            const fieldKey = `${point.row}:${point.column}`;
            const inputId = `coefficient-${degree}-${point.row}-${point.column}`;
            const errorId = `${inputId}-error`;
            const error = errors.get(fieldKey);
            const style = {
              left: `calc(50% + ${coordinateText(point.x)}px)`,
              top: `${coordinateText(INPUT_TOP_PADDING + point.y)}px`,
            } satisfies CSSProperties;

            return (
              <label
                className="coefficient-input-slot"
                htmlFor={inputId}
                key={fieldKey}
                style={style}
                data-row={point.row}
                data-column={point.column}
                data-x={coordinateText(point.x)}
                data-y={coordinateText(point.y)}
              >
                <MathFormula
                  latex={monomialLatex(exponent)}
                  ariaHidden
                  className="monomial-label"
                />
                <input
                  id={inputId}
                  className="coefficient-input"
                  type="text"
                  inputMode="text"
                  autoComplete="off"
                  spellCheck={false}
                  maxLength={130}
                  value={rows[point.row]?.[point.column] ?? ""}
                  placeholder="0"
                  aria-label={`Coefficient of ${monomialPlainText(exponent)}`}
                  aria-invalid={error ? true : undefined}
                  aria-describedby={error ? errorId : undefined}
                  onChange={(event) =>
                    onChange(point.row, point.column, event.currentTarget.value)
                  }
                  onFocus={(event) => event.currentTarget.select()}
                />
                {error ? (
                  <span className="sr-only" id={errorId}>
                    {error}
                  </span>
                ) : null}
              </label>
            );
          })}
        </div>
      </div>
    </fieldset>
  );
}

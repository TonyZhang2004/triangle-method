import {
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type ClipboardEvent,
  type CSSProperties,
} from "react";

import {
  exponentAt,
  monomialLatex,
  monomialPlainText,
} from "../exact";
import {
  coordinateText,
  EQUILATERAL_ALTITUDE,
  fittedTriangleStep,
  trianglePoints,
} from "../geometry";
import { useResponsiveSpace, type ResponsiveSpace } from "../responsive";
import { MathFormula } from "./MathFormula";

const DEFAULT_INPUT_LATTICE_STEP = 156;
const DEFAULT_INPUT_SIDE_PADDING = 76;
const INPUT_TOP_PADDING = 42;
const INPUT_BOTTOM_PADDING = 58;
const LARGE_TRIANGLE_DEGREE = 6;

type CoefficientTriangleEditorProps = {
  degree: number;
  rows: string[][];
  errors: Map<string, string>;
  onChange: (row: number, column: number, value: string) => void;
  onChangeRow: (row: number, values: string[]) => void;
};

type InputTriangleGeometry = {
  latticeStep: number;
  sidePadding: number;
};

/** Choose readable input spacing that fits the current device whenever possible. */
function inputTriangleGeometry(
  degree: number,
  space: ResponsiveSpace,
): InputTriangleGeometry {
  if (space.containerWidth <= 0 || space.containerHeight <= 0) {
    return {
      latticeStep: DEFAULT_INPUT_LATTICE_STEP,
      sidePadding: DEFAULT_INPUT_SIDE_PADDING,
    };
  }

  const compact = space.viewportWidth <= 480;
  const medium = space.viewportWidth <= 800;
  const sidePadding = compact ? 46 : medium ? 54 : 64;
  const minimumStep = compact ? 80 : medium ? 96 : 116;
  const maximumStep = compact ? 128 : medium ? 200 : 320;

  return {
    latticeStep: fittedTriangleStep({
      degree,
      availableWidth: space.containerWidth,
      availableHeight: space.containerHeight,
      horizontalPadding: 2 * sidePadding,
      verticalPadding: INPUT_TOP_PADDING + INPUT_BOTTOM_PADDING,
      minimumStep,
      maximumStep:
        degree < LARGE_TRIANGLE_DEGREE && !compact ? 420 : maximumStep,
    }),
    sidePadding,
  };
}

/** Split a spreadsheet-style pasted row into coefficient strings. */
function pastedRowValues(text: string): string[] {
  return text.trim().split(/[\s,;]+/).filter(Boolean);
}

/** Scroll one coefficient to the visual center of the bounded editor workspace. */
function centerCoefficient(
  container: HTMLDivElement,
  input: HTMLInputElement,
  behavior: ScrollBehavior,
): void {
  const slot = input.closest<HTMLElement>(".coefficient-input-slot");
  if (!slot) return;
  const left = Math.max(
    0,
    Math.min(
      container.scrollWidth - container.clientWidth,
      slot.offsetLeft - container.clientWidth / 2,
    ),
  );
  const top = Math.max(
    0,
    Math.min(
      container.scrollHeight - container.clientHeight,
      slot.offsetTop - container.clientHeight / 2,
    ),
  );
  if (typeof container.scrollTo === "function") {
    container.scrollTo({ left, top, behavior });
  } else {
    container.scrollLeft = left;
    container.scrollTop = top;
  }
}

/** Render exact coefficient inputs on the canonical centered equilateral lattice. */
export function CoefficientTriangleEditor({
  degree,
  rows,
  errors,
  onChange,
  onChangeRow,
}: CoefficientTriangleEditorProps) {
  const scrollContainer = useRef<HTMLDivElement>(null);
  const responsiveSpace = useResponsiveSpace(scrollContainer);
  const [activeRow, setActiveRow] = useState(0);
  const [pasteMessage, setPasteMessage] = useState("");
  const geometry = inputTriangleGeometry(degree, responsiveSpace);
  const points = trianglePoints(degree, geometry.latticeStep);
  const isLargeTriangle = degree >= LARGE_TRIANGLE_DEGREE;
  const totalCoefficients = points.length;
  const enteredCoefficients = useMemo(
    () =>
      rows.reduce(
        (total, row) =>
          total + row.filter((value) => value.trim() !== "").length,
        0,
      ),
    [rows],
  );
  const width = degree * geometry.latticeStep + 2 * geometry.sidePadding;
  const height =
    degree * geometry.latticeStep * EQUILATERAL_ALTITUDE +
    INPUT_TOP_PADDING +
    INPUT_BOTTOM_PADDING;

  useLayoutEffect(() => {
    const element = scrollContainer.current;
    if (element) {
      element.scrollTop = 0;
    }
    setActiveRow(0);
    setPasteMessage("");
  }, [degree]);

  useLayoutEffect(() => {
    const element = scrollContainer.current;
    if (!element) return;
    const focusedInput = element.contains(document.activeElement)
      ? (document.activeElement as HTMLInputElement)
      : null;
    if (focusedInput?.matches(".coefficient-input")) {
      centerCoefficient(element, focusedInput, "auto");
      return;
    }
    element.scrollLeft = Math.max(
      0,
      (element.scrollWidth - element.clientWidth) / 2,
    );
  }, [
    degree,
    geometry.latticeStep,
    responsiveSpace.containerWidth,
    responsiveSpace.containerHeight,
    responsiveSpace.viewportHeight,
  ]);

  /** Focus a row's first coefficient and center it along both scroll axes. */
  function jumpToRow(row: number) {
    setActiveRow(row);
    const input = document.getElementById(
      `coefficient-${degree}-${row}-0`,
    ) as HTMLInputElement | null;
    const container = scrollContainer.current;
    if (!input || !container) return;
    input.focus({ preventScroll: true });
    centerCoefficient(container, input, "smooth");
  }

  /** Fill a complete row when its first field receives multiple pasted values. */
  function pasteRow(
    event: ClipboardEvent<HTMLInputElement>,
    row: number,
    column: number,
  ) {
    if (column !== 0) return;
    const values = pastedRowValues(event.clipboardData.getData("text"));
    if (values.length <= 1) return;
    event.preventDefault();
    const expected = row + 1;
    if (values.length !== expected) {
      setPasteMessage(
        `Row ${row + 1} needs ${expected} coefficients; ${values.length} were pasted.`,
      );
      return;
    }
    onChangeRow(row, values);
    setPasteMessage(`Filled all ${expected} coefficients in row ${row + 1}.`);
    requestAnimationFrame(() => {
      const lastInput = document.getElementById(
        `coefficient-${degree}-${row}-${row}`,
      ) as HTMLInputElement | null;
      const container = scrollContainer.current;
      if (lastInput && container) {
        lastInput.focus({ preventScroll: true });
        centerCoefficient(container, lastInput, "smooth");
      }
    });
  }

  return (
    <fieldset
      className="coefficient-fieldset"
      aria-describedby={isLargeTriangle ? `coefficient-help-${degree}` : undefined}
    >
      <legend className="sr-only">
        Degree {degree} coefficients of the homogeneous polynomial in canonical
        triangle order
      </legend>
      {isLargeTriangle ? (
        <>
          <div className="coefficient-editor-tools">
            <label className="row-jump-control" htmlFor={`row-jump-${degree}`}>
              <span>Jump to row</span>
              <select
                id={`row-jump-${degree}`}
                value={activeRow}
                onChange={(event) => jumpToRow(Number(event.currentTarget.value))}
              >
                {rows.map((_row, row) => (
                  <option value={row} key={row}>
                    {row + 1} of {degree + 1}
                    {row === 0 ? " (apex)" : row === degree ? " (base)" : ""}
                  </option>
                ))}
              </select>
            </label>
            <span className="coefficient-entry-count" aria-live="polite">
              {enteredCoefficients} of {totalCoefficients} entered
            </span>
          </div>
          <p className="row-paste-help" id={`coefficient-help-${degree}`}>
            Scroll to explore the triangle. Blanks are zero. Paste a full space,
            comma, or tab-separated row into that row&apos;s first coefficient.
          </p>
          {pasteMessage ? (
            <p className="row-paste-status" role="status" aria-live="polite">
              {pasteMessage}
            </p>
          ) : null}
        </>
      ) : null}
      <div
        className={`triangle-scroll input-triangle-scroll${
          isLargeTriangle ? " input-triangle-scroll-large" : ""
        }`}
        data-testid="coefficient-editor-scroll"
        ref={scrollContainer}
        role="region"
        aria-label="Coefficient triangle editor"
        tabIndex={0}
      >
        <div
          className="triangle-canvas input-triangle"
          style={{ width, height }}
          data-degree={degree}
          data-lattice-step={coordinateText(geometry.latticeStep)}
          data-side-padding={geometry.sidePadding}
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
                  onPaste={(event) => pasteRow(event, point.row, point.column)}
                  onFocus={(event) => {
                    setActiveRow(point.row);
                    event.currentTarget.select();
                    const container = scrollContainer.current;
                    if (container) {
                      centerCoefficient(container, event.currentTarget, "auto");
                    }
                  }}
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

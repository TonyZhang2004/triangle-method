import type { CSSProperties } from "react";

import { formatRational, isZeroRational } from "../exact";
import { coordinateText, EQUILATERAL_ALTITUDE, trianglePoints } from "../geometry";
import type { RationalRecord } from "../types";

type CoefficientTriangleProps = {
  rows: RationalRecord[][];
  label: string;
  toneClass?: string;
};

const OUTPUT_SIDE_PADDING = 34;
const OUTPUT_VERTICAL_PADDING = 28;

function outputStep(rows: RationalRecord[][]): number {
  const longest = Math.max(
    ...rows.flatMap((row) => row.map((value) => formatRational(value).length)),
  );
  return Math.max(76, longest * 11 + 34);
}

function spokenRational(value: RationalRecord): string {
  const numerator = BigInt(value.numerator);
  const sign = numerator < 0n ? "negative " : "";
  const magnitude = numerator < 0n ? -numerator : numerator;
  if (value.denominator === "1") return `${sign}${magnitude}`;
  return `${sign}${magnitude} over ${value.denominator}`;
}

function triangleDescription(
  label: string,
  rows: RationalRecord[][],
): string {
  const rowDescriptions = rows.map((row, rowIndex) => {
    const entries = row.map(spokenRational);
    return `row ${rowIndex + 1}: ${entries.join(", ")}`;
  });
  return `${label}. ${rowDescriptions.join(". ")}.`;
}

/** Render exact coefficient rows alone on the canonical equilateral lattice. */
export function CoefficientTriangle({
  rows,
  label,
  toneClass = "",
}: CoefficientTriangleProps) {
  const degree = rows.length - 1;
  const step = outputStep(rows);
  const points = trianglePoints(degree, step);
  const width = degree * step + 2 * OUTPUT_SIDE_PADDING;
  const height =
    degree * step * EQUILATERAL_ALTITUDE + 2 * OUTPUT_VERTICAL_PADDING + 18;
  const description = triangleDescription(label, rows);

  return (
    <figure className={`output-triangle-figure ${toneClass}`.trim()}>
      <figcaption className="triangle-caption">{label}</figcaption>
      <div className="triangle-scroll">
        <div
          className="triangle-canvas output-triangle"
          role="img"
          aria-label={description}
          style={{ width, height }}
          data-degree={degree}
        >
          {points.map((point) => {
            const key = `${point.row}:${point.column}`;
            const value = rows[point.row][point.column];
            const style = {
              left: `calc(50% + ${coordinateText(point.x)}px)`,
              top: `${coordinateText(OUTPUT_VERTICAL_PADDING + point.y)}px`,
            } satisfies CSSProperties;
            return (
              <div
                className="coefficient-mark"
                key={key}
                style={style}
                data-row={point.row}
                data-column={point.column}
                data-x={coordinateText(point.x)}
                data-y={coordinateText(point.y)}
                data-coefficient={formatRational(value)}
                data-zero={isZeroRational(value) || undefined}
              >
                <span className="coefficient-value">{formatRational(value)}</span>
              </div>
            );
          })}
        </div>
      </div>
    </figure>
  );
}

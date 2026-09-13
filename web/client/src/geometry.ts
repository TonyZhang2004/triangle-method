export const EQUILATERAL_ALTITUDE = Math.sqrt(3) / 2;

export type TrianglePoint = {
  row: number;
  column: number;
  x: number;
  y: number;
};

export type TriangleFitOptions = {
  degree: number;
  availableWidth: number;
  availableHeight: number;
  horizontalPadding: number;
  verticalPadding: number;
  minimumStep: number;
  maximumStep: number;
};

/** Place all degree-n slots on one centered equilateral lattice step. */
export function trianglePoints(degree: number, step: number): TrianglePoint[] {
  const points: TrianglePoint[] = [];
  for (let row = 0; row <= degree; row += 1) {
    for (let column = 0; column <= row; column += 1) {
      points.push({
        row,
        column,
        x: (column - row / 2) * step,
        y: row * EQUILATERAL_ALTITUDE * step,
      });
    }
  }
  return points;
}

/** Fit one equilateral lattice into a measured area and return its scalar step. */
export function fittedTriangleStep({
  degree,
  availableWidth,
  availableHeight,
  horizontalPadding,
  verticalPadding,
  minimumStep,
  maximumStep,
}: TriangleFitOptions): number {
  if (degree <= 0 || availableWidth <= 0 || availableHeight <= 0) {
    return minimumStep;
  }

  const widthStep = Math.max(0, availableWidth - horizontalPadding) / degree;
  const heightStep =
    Math.max(0, availableHeight - verticalPadding) /
    (degree * EQUILATERAL_ALTITUDE);
  const fittedStep = Math.min(widthStep, heightStep, maximumStep);
  return Math.max(minimumStep, fittedStep);
}

/** Serialize a presentation coordinate with stable, testable precision. */
export function coordinateText(value: number): string {
  return value.toFixed(6).replace(/\.?0+$/, "") || "0";
}

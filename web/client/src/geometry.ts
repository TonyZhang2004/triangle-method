export const EQUILATERAL_ALTITUDE = Math.sqrt(3) / 2;

export type TrianglePoint = {
  row: number;
  column: number;
  x: number;
  y: number;
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

/** Serialize a presentation coordinate with stable, testable precision. */
export function coordinateText(value: number): string {
  return value.toFixed(6).replace(/\.?0+$/, "") || "0";
}


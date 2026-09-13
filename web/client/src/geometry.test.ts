import { describe, expect, it } from "vitest";

import { EQUILATERAL_ALTITUDE, trianglePoints } from "./geometry";

describe("equilateral coefficient geometry", () => {
  it("derives every coordinate from one lattice step", () => {
    const step = 156;
    const points = trianglePoints(3, step);
    const at = (row: number, column: number) =>
      points.find((point) => point.row === row && point.column === column)!;

    expect(at(0, 0)).toMatchObject({ x: 0, y: 0 });
    expect(at(1, 0).x).toBe(-step / 2);
    expect(at(1, 1).x).toBe(step / 2);
    expect(at(3, 3).x - at(3, 2).x).toBe(step);
    expect(at(2, 1).y - at(1, 0).y).toBeCloseTo(
      EQUILATERAL_ALTITUDE * step,
      12,
    );
    expect((at(1, 1).x + at(1, 0).x) / 2).toBe(0);
  });
});


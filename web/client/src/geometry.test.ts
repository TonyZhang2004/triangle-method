import { describe, expect, it } from "vitest";

import {
  EQUILATERAL_ALTITUDE,
  fittedTriangleStep,
  trianglePoints,
} from "./geometry";

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

  it("fits with one scalar step while respecting readable limits", () => {
    const heightLimited = fittedTriangleStep({
      degree: 3,
      availableWidth: 1_000,
      availableHeight: 600,
      horizontalPadding: 100,
      verticalPadding: 80,
      minimumStep: 80,
      maximumStep: 320,
    });
    expect(heightLimited).toBeCloseTo(
      520 / (3 * EQUILATERAL_ALTITUDE),
      12,
    );

    expect(
      fittedTriangleStep({
        degree: 12,
        availableWidth: 320,
        availableHeight: 480,
        horizontalPadding: 92,
        verticalPadding: 100,
        minimumStep: 80,
        maximumStep: 128,
      }),
    ).toBe(80);
    expect(
      fittedTriangleStep({
        degree: 2,
        availableWidth: 2_000,
        availableHeight: 2_000,
        horizontalPadding: 128,
        verticalPadding: 100,
        minimumStep: 116,
        maximumStep: 320,
      }),
    ).toBe(320);
  });
});

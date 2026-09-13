import { expect, test, type Page } from "@playwright/test";

type Point = {
  row: number;
  column: number;
  x: number;
  y: number;
};

async function chooseDegree(page: Page, degree: number): Promise<void> {
  await page.getByLabel("Degree").selectOption(String(degree));
}

async function enterRows(page: Page, rows: string[][]): Promise<void> {
  for (let row = 0; row < rows.length; row += 1) {
    for (let column = 0; column < rows[row].length; column += 1) {
      await page
        .locator(`#coefficient-${rows.length - 1}-${row}-${column}`)
        .fill(rows[row][column]);
    }
  }
}

function distance(left: Point, right: Point): number {
  return Math.hypot(left.x - right.x, left.y - right.y);
}

test("the cubic inputs form a centered, perfect equilateral triangle", async ({
  page,
}) => {
  await page.goto("/");
  await expect(page.locator("h1")).toHaveCount(0);
  await expect(page.locator(".coefficient-input-slot")).toHaveCount(10);

  const points = await page.locator(".coefficient-input-slot").evaluateAll((slots) =>
    slots.map((slot) => {
      const bounds = slot.getBoundingClientRect();
      return {
        row: Number((slot as HTMLElement).dataset.row),
        column: Number((slot as HTMLElement).dataset.column),
        x: bounds.left + bounds.width / 2,
        y: bounds.top + bounds.height / 2,
      };
    }),
  );

  const apex = points.find((point) => point.row === 0)!;
  const base = points.filter((point) => point.row === 3);
  const baseLeft = base[0];
  const baseRight = base[base.length - 1];
  const baseLength = distance(baseLeft, baseRight);

  expect(Math.abs((baseLeft.x + baseRight.x) / 2 - apex.x)).toBeLessThan(0.25);
  expect(Math.abs(distance(apex, baseLeft) - baseLength)).toBeLessThan(0.25);
  expect(Math.abs(distance(apex, baseRight) - baseLength)).toBeLessThan(0.25);

  for (let row = 0; row <= 3; row += 1) {
    const rowPoints = points.filter((point) => point.row === row);
    const center =
      rowPoints.reduce((total, point) => total + point.x, 0) / rowPoints.length;
    expect(Math.abs(center - apex.x)).toBeLessThan(0.25);
  }

  const latticeStep = distance(
    points.find((point) => point.row === 1 && point.column === 0)!,
    points.find((point) => point.row === 1 && point.column === 1)!,
  );
  for (const point of points.filter((candidate) => candidate.row < 3)) {
    const leftChild = points.find(
      (candidate) =>
        candidate.row === point.row + 1 && candidate.column === point.column,
    )!;
    const rightChild = points.find(
      (candidate) =>
        candidate.row === point.row + 1 &&
        candidate.column === point.column + 1,
    )!;
    expect(Math.abs(distance(point, leftChild) - latticeStep)).toBeLessThan(0.25);
    expect(Math.abs(distance(point, rightChild) - latticeStep)).toBeLessThan(0.25);
  }
});

test("a combined Cauchy and AM-GM input returns a colored exact certificate", async ({
  page,
}) => {
  await page.goto("/");
  await chooseDegree(page, 2);
  await enterRows(page, [["3"], ["-4", "-2"], ["3", "-2", "2"]]);
  await page.getByRole("button", { name: "Prove" }).click();

  await expect(page.getByRole("heading", { name: "Proved" })).toBeVisible();
  await expect(page.getByText("Cauchy", { exact: true })).toBeVisible();
  await expect(page.getByText("AM-GM", { exact: true })).toBeVisible();
  await expect(page.locator(".component-button")).toHaveCount(4);

  await page.getByRole("button", { name: "Remainder" }).click();
  for (let step = 1; step < 4; step += 1) {
    await page.getByRole("button", { name: "Next" }).click();
  }
  await expect(page.getByText("Step 4 of 4")).toBeVisible();
  const finalRemainder = await page
    .locator(".output-triangle .coefficient-mark")
    .evaluateAll((entries) =>
      entries.map((entry) => (entry as HTMLElement).dataset.coefficient),
    );
  expect(finalRemainder).toEqual(["0", "0", "0", "0", "0", "0"]);
});

test("a false inequality returns its exact negative witness", async ({ page }) => {
  await page.goto("/");
  await chooseDegree(page, 2);
  await enterRows(page, [["1"], ["-4", "0"], ["1", "0", "1"]]);
  await page.getByRole("button", { name: "Prove" }).click();

  await expect(
    page.getByRole("heading", { name: "Counterexample found" }),
  ).toBeVisible();
  await expect(
    page.getByText("This exact nonnegative point makes the polynomial negative."),
  ).toBeVisible();
});

test("the quintic Schur triangle returns a named exact proof", async ({ page }) => {
  await page.goto("/");
  await chooseDegree(page, 5);
  await enterRows(page, [
    ["1"],
    ["-1", "-1"],
    ["0", "1", "0"],
    ["0", "0", "0", "0"],
    ["-1", "1", "0", "1", "-1"],
    ["1", "-1", "0", "0", "-1", "1"],
  ]);
  await page.getByRole("button", { name: "Prove" }).click();

  await expect(page.getByRole("heading", { name: "Proved" })).toBeVisible();
  await expect(page.getByText("Schur", { exact: true })).toBeVisible();
  await expect(page.locator(".component-button")).toHaveCount(1);
});

test("the degree-five editor stays usable on a narrow screen", async ({
  page,
  isMobile,
}) => {
  test.skip(!isMobile, "This assertion exercises the narrow mobile viewport.");
  await page.goto("/");
  await chooseDegree(page, 5);
  await expect(page.locator(".coefficient-input-slot")).toHaveCount(21);

  const measurements = await page.evaluate(() => {
    const scroll = document.querySelector<HTMLElement>(
      '[data-testid="coefficient-editor-scroll"]',
    )!;
    return {
      bodyWidth: document.body.scrollWidth,
      viewportWidth: document.documentElement.clientWidth,
      scrollWidth: scroll.scrollWidth,
      clientWidth: scroll.clientWidth,
    };
  });
  expect(measurements.bodyWidth).toBeLessThanOrEqual(measurements.viewportWidth + 1);
  expect(measurements.scrollWidth).toBeGreaterThan(measurements.clientWidth);
});

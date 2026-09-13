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

test("the degree-12 inputs form a centered, perfect equilateral triangle", async ({
  page,
}) => {
  await page.goto("/");
  await expect(page.locator("h1")).toHaveCount(0);
  await chooseDegree(page, 12);
  await expect(page.getByLabel("Degree")).toHaveValue("12");
  await expect(page.locator(".coefficient-input-slot")).toHaveCount(91);
  await expect(page.getByRole("textbox")).toHaveCount(91);

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
  const base = points.filter((point) => point.row === 12);
  const baseLeft = base[0];
  const baseRight = base[base.length - 1];
  const baseLength = distance(baseLeft, baseRight);

  expect(Math.abs((baseLeft.x + baseRight.x) / 2 - apex.x)).toBeLessThan(0.25);
  expect(Math.abs(distance(apex, baseLeft) - baseLength)).toBeLessThan(0.25);
  expect(Math.abs(distance(apex, baseRight) - baseLength)).toBeLessThan(0.25);

  for (let row = 0; row <= 12; row += 1) {
    const rowPoints = points.filter((point) => point.row === row);
    const center =
      rowPoints.reduce((total, point) => total + point.x, 0) / rowPoints.length;
    expect(Math.abs(center - apex.x)).toBeLessThan(0.25);
  }

  const latticeStep = distance(
    points.find((point) => point.row === 1 && point.column === 0)!,
    points.find((point) => point.row === 1 && point.column === 1)!,
  );
  for (const point of points.filter((candidate) => candidate.row < 12)) {
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

test("the workspace fills the device and refits after live resizing", async ({
  page,
  isMobile,
}) => {
  test.skip(isMobile, "Desktop resizing supplies the viewport transitions.");
  await page.setViewportSize({ width: 1020, height: 705 });
  await page.goto("/");

  const layout = () =>
    page.evaluate(() => {
      const shell = document.querySelector<HTMLElement>(".app-shell")!;
      const workspace = document.querySelector<HTMLElement>(
        '[data-testid="coefficient-editor-scroll"]',
      )!;
      const canvas = workspace.querySelector<HTMLElement>(".input-triangle")!;
      const proveButton = document.querySelector<HTMLElement>(".prove-button")!;
      const actionBar = document.querySelector<HTMLElement>(".proof-button-bar")!;
      const workspaceBounds = workspace.getBoundingClientRect();
      const canvasBounds = canvas.getBoundingClientRect();
      const buttonBounds = proveButton.getBoundingClientRect();
      return {
        viewportWidth: document.documentElement.clientWidth,
        viewportHeight: window.innerHeight,
        visibleViewportTop: window.visualViewport?.offsetTop ?? 0,
        visibleViewportHeight: window.visualViewport?.height ?? window.innerHeight,
        documentWidth: document.documentElement.scrollWidth,
        documentHeight: document.documentElement.scrollHeight,
        documentClientHeight: document.documentElement.clientHeight,
        pageScrollY: window.scrollY,
        shellWidth: shell.getBoundingClientRect().width,
        shellHeight: shell.getBoundingClientRect().height,
        workspaceWidth: workspace.getBoundingClientRect().width,
        workspaceHeight: workspace.clientHeight,
        workspaceScrollTop: workspace.scrollTop,
        workspaceScrollHeight: workspace.scrollHeight,
        canvasWidth: canvasBounds.width,
        latticeStep: Number(canvas.dataset.latticeStep),
        buttonTop: buttonBounds.top,
        buttonBottom: buttonBounds.bottom,
        actionBarPosition: getComputedStyle(actionBar).position,
        centerError: Math.abs(
          workspaceBounds.left + workspaceBounds.width / 2 -
            (canvasBounds.left + canvasBounds.width / 2),
        ),
      };
    });
  const adjacentQuinticBaseGap = () =>
    page.evaluate(() => {
      const left = document
        .querySelector<HTMLElement>("#coefficient-5-5-0")!
        .getBoundingClientRect();
      const right = document
        .querySelector<HTMLElement>("#coefficient-5-5-1")!
        .getBoundingClientRect();
      return right.left - left.right;
    });

  const laptop = await layout();
  expect(laptop.shellWidth).toBeGreaterThanOrEqual(laptop.viewportWidth * 0.99);
  expect(laptop.workspaceWidth).toBeGreaterThanOrEqual(
    laptop.viewportWidth * 0.94,
  );
  expect(laptop.documentWidth).toBeLessThanOrEqual(laptop.viewportWidth + 1);
  expect(laptop.documentHeight).toBeLessThanOrEqual(
    laptop.documentClientHeight + 1,
  );
  expect(laptop.shellHeight).toBeCloseTo(laptop.viewportHeight, 0);
  expect(laptop.pageScrollY).toBe(0);
  expect(laptop.actionBarPosition).toBe("absolute");
  expect(laptop.buttonTop).toBeGreaterThanOrEqual(0);
  expect(laptop.buttonBottom).toBeLessThanOrEqual(laptop.viewportHeight);

  await chooseDegree(page, 5);
  const laptopQuintic = await layout();
  expect(laptopQuintic.workspaceScrollHeight).toBeGreaterThan(
    laptopQuintic.workspaceHeight,
  );
  await page.getByTestId("coefficient-editor-scroll").evaluate((workspace) => {
    workspace.scrollTop = 80;
  });
  await expect
    .poll(async () => (await layout()).workspaceScrollTop)
    .toBeGreaterThan(0);
  const scrolledQuintic = await layout();
  expect(scrolledQuintic.pageScrollY).toBe(0);
  expect(scrolledQuintic.buttonTop).toBeCloseTo(laptopQuintic.buttonTop, 0);

  await page.setViewportSize({ width: 820, height: 705 });
  await expect.poll(async () => (await layout()).viewportWidth).toBe(820);
  const breakpointGap = await adjacentQuinticBaseGap();
  expect(breakpointGap).toBeGreaterThanOrEqual(-0.5);

  const devtools = await page.context().newCDPSession(page);
  await devtools.send("Emulation.setPageScaleFactor", { pageScaleFactor: 2 });
  await expect
    .poll(() => page.evaluate(() => window.visualViewport?.scale ?? 1))
    .toBeGreaterThan(1);
  expect(await adjacentQuinticBaseGap()).toBeGreaterThanOrEqual(-0.5);
  await expect.poll(async () => (await layout()).shellHeight).toBeLessThan(480);
  const zoomed = await layout();
  expect(zoomed.buttonTop).toBeGreaterThanOrEqual(zoomed.visibleViewportTop - 1);
  expect(zoomed.buttonBottom).toBeLessThanOrEqual(
    zoomed.visibleViewportTop + zoomed.visibleViewportHeight + 1,
  );
  await devtools.send("Emulation.setPageScaleFactor", { pageScaleFactor: 1 });
  await expect
    .poll(() => page.evaluate(() => window.visualViewport?.scale ?? 1))
    .toBe(1);

  await page.setViewportSize({ width: 320, height: 568 });
  await expect.poll(async () => (await layout()).viewportWidth).toBe(320);
  await expect
    .poll(async () => {
      const current = await layout();
      return Math.abs(current.shellHeight - current.visibleViewportHeight);
    })
    .toBeLessThanOrEqual(1);
  const compactQuintic = await layout();
  expect(compactQuintic.documentWidth).toBeLessThanOrEqual(321);
  expect(compactQuintic.canvasWidth).toBeGreaterThan(
    compactQuintic.workspaceWidth,
  );
  expect(compactQuintic.workspaceScrollHeight).toBeGreaterThan(
    compactQuintic.workspaceHeight,
  );
  expect(compactQuintic.documentHeight).toBeLessThanOrEqual(
    compactQuintic.documentClientHeight + 1,
  );
  expect(compactQuintic.actionBarPosition).toBe("absolute");
  expect(compactQuintic.buttonBottom).toBeLessThanOrEqual(
    compactQuintic.viewportHeight,
  );
  const compactGap = await adjacentQuinticBaseGap();
  expect(compactGap).toBeGreaterThanOrEqual(-0.5);

  await chooseDegree(page, 12);
  await page.setViewportSize({ width: 320, height: 360 });
  await expect
    .poll(async () => (await layout()).workspaceHeight)
    .toBeGreaterThanOrEqual(100);
  await expect
    .poll(async () => {
      const current = await layout();
      return Math.abs(current.shellHeight - current.visibleViewportHeight);
    })
    .toBeLessThanOrEqual(1);
  const shortViewport = await layout();
  expect(shortViewport.documentHeight).toBeLessThanOrEqual(
    shortViewport.documentClientHeight + 1,
  );
  expect(shortViewport.buttonBottom).toBeLessThanOrEqual(
    shortViewport.visibleViewportTop + shortViewport.visibleViewportHeight + 1,
  );
  await expect(page.locator(".input-instruction")).toBeHidden();

  await chooseDegree(page, 3);
  await page.setViewportSize({ width: 1920, height: 1080 });
  await expect
    .poll(async () => (await layout()).workspaceWidth)
    .toBeGreaterThan(laptop.workspaceWidth * 1.75);
  await expect
    .poll(async () => (await layout()).latticeStep)
    .toBeGreaterThan(laptop.latticeStep * 1.4);
  const wide = await layout();
  expect(wide.centerError).toBeLessThanOrEqual(1);
  expect(wide.documentWidth).toBeLessThanOrEqual(wide.viewportWidth + 1);
  expect(wide.documentHeight).toBeLessThanOrEqual(wide.documentClientHeight + 1);
  expect(wide.buttonBottom).toBeLessThanOrEqual(wide.viewportHeight);

  await chooseDegree(page, 12);
  await page.setViewportSize({ width: 393, height: 851 });
  await expect
    .poll(async () => (await layout()).latticeStep)
    .toBeLessThanOrEqual(80);
  const narrow = await layout();
  expect(narrow.workspaceWidth).toBeGreaterThanOrEqual(
    narrow.viewportWidth * 0.9,
  );
  expect(narrow.centerError).toBeLessThanOrEqual(1);
  expect(narrow.documentWidth).toBeLessThanOrEqual(narrow.viewportWidth + 1);
  expect(narrow.documentHeight).toBeLessThanOrEqual(
    narrow.documentClientHeight + 1,
  );
  expect(narrow.buttonBottom).toBeLessThanOrEqual(narrow.viewportHeight);
});

test("a degree-12 zero input returns a verified production proof", async ({
  page,
}) => {
  await page.goto("/");
  await chooseDegree(page, 12);

  const proofResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      new URL(response.url()).pathname === "/api/prove",
  );
  await page.getByRole("button", { name: "Prove" }).click();
  const response = await proofResponse;
  const payload = await response.json();

  expect(response.status()).toBe(200);
  expect(payload).toMatchObject({
    outcome: "PROVED",
    method: "zero",
    target: { degree: 12 },
    proof: { verified: true, residualZero: true },
  });
  await expect(page.getByRole("heading", { name: "Proved" })).toBeVisible();
  await expect(
    page.getByText("Exact certificate verified; final remainder is zero."),
  ).toBeVisible();
  await expect(page.locator(".output-triangle .coefficient-mark")).toHaveCount(91);
  await expect(page.getByTestId("editor-page")).toHaveCount(0);
  await expect(page.getByTestId("proof-page")).toBeVisible();
  await expect(page).toHaveURL(/#proof$/);

  const proofLayout = await page.evaluate(() => {
    const documentElement = document.documentElement;
    const results = document.querySelector<HTMLElement>(
      '[data-testid="result-page-scroll"]',
    )!;
    return {
      documentHeight: documentElement.scrollHeight,
      documentClientHeight: documentElement.clientHeight,
      resultScrollHeight: results.scrollHeight,
      resultClientHeight: results.clientHeight,
    };
  });
  expect(proofLayout.documentHeight).toBeLessThanOrEqual(
    proofLayout.documentClientHeight + 1,
  );
  expect(proofLayout.resultScrollHeight).toBeGreaterThan(
    proofLayout.resultClientHeight,
  );

  await page.goBack();
  await expect(page.getByTestId("editor-page")).toBeVisible();
  await expect(page.getByLabel("Degree")).toHaveValue("12");
  await expect(page.getByLabel("Degree")).toBeFocused();
  await page.goForward();
  await expect(page.getByTestId("proof-page")).toBeVisible();
  await page.getByRole("button", { name: "Back to inequality" }).click();
  await expect(page.getByTestId("editor-page")).toBeVisible();
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
  await page.getByRole("button", { name: "Back to inequality" }).click();
  await expect(page.getByLabel("Degree")).toHaveValue("5");
  await expect(page.locator("#coefficient-5-0-0")).toHaveValue("1");
  await expect(page.locator("#coefficient-5-5-5")).toHaveValue("1");
});

test("the degree-12 editor stays usable without page overflow on a narrow screen", async ({
  page,
  isMobile,
}) => {
  test.skip(!isMobile, "This assertion exercises the narrow mobile viewport.");
  await page.goto("/");
  await chooseDegree(page, 12);
  await expect(page.locator(".coefficient-input-slot")).toHaveCount(91);

  const measurements = await page.evaluate(() => {
    const scroll = document.querySelector<HTMLElement>(
      '[data-testid="coefficient-editor-scroll"]',
    )!;
    return {
      bodyWidth: document.body.scrollWidth,
      documentWidth: document.documentElement.scrollWidth,
      viewportWidth: document.documentElement.clientWidth,
      viewportHeight: window.innerHeight,
      documentHeight: document.documentElement.scrollHeight,
      documentClientHeight: document.documentElement.clientHeight,
      scrollWidth: scroll.scrollWidth,
      clientWidth: scroll.clientWidth,
      scrollHeight: scroll.scrollHeight,
      clientHeight: scroll.clientHeight,
      scrollLeft: scroll.scrollLeft,
      buttonBounds: (() => {
        const button = document
          .querySelector<HTMLElement>(".prove-button")!
          .getBoundingClientRect();
        return { top: button.top, bottom: button.bottom };
      })(),
      actionBarPosition: getComputedStyle(
        document.querySelector<HTMLElement>(".proof-button-bar")!,
      ).position,
    };
  });
  expect(measurements.bodyWidth).toBeLessThanOrEqual(measurements.viewportWidth + 1);
  expect(measurements.documentWidth).toBeLessThanOrEqual(
    measurements.viewportWidth + 1,
  );
  expect(measurements.documentHeight).toBeLessThanOrEqual(
    measurements.documentClientHeight + 1,
  );
  expect(measurements.actionBarPosition).toBe("absolute");
  expect(measurements.buttonBounds.top).toBeGreaterThanOrEqual(0);
  expect(measurements.buttonBounds.bottom).toBeLessThanOrEqual(
    measurements.viewportHeight,
  );
  expect(measurements.scrollWidth).toBeGreaterThan(measurements.clientWidth);
  expect(measurements.scrollHeight).toBeGreaterThan(measurements.clientHeight);
  expect(
    Math.abs(
      measurements.scrollLeft -
        (measurements.scrollWidth - measurements.clientWidth) / 2,
    ),
  ).toBeLessThanOrEqual(1);

  const edgeCoefficient = page.locator("#coefficient-12-12-12");
  await edgeCoefficient.fill("1/2");
  await expect(edgeCoefficient).toHaveValue("1/2");
  const focusedBounds = () => page.evaluate(() => {
    const workspace = document.querySelector<HTMLElement>(
      '[data-testid="coefficient-editor-scroll"]',
    )!.getBoundingClientRect();
    const input = document
      .querySelector<HTMLElement>("#coefficient-12-12-12")!
      .getBoundingClientRect();
    return {
      leftGap: input.left - workspace.left,
      rightGap: workspace.right - input.right,
      topGap: input.top - workspace.top,
      bottomGap: workspace.bottom - input.bottom,
    };
  });
  const initiallyFocused = await focusedBounds();
  expect(initiallyFocused.leftGap).toBeGreaterThanOrEqual(-1);
  expect(initiallyFocused.rightGap).toBeGreaterThanOrEqual(-1);
  expect(initiallyFocused.topGap).toBeGreaterThanOrEqual(-1);
  expect(initiallyFocused.bottomGap).toBeGreaterThanOrEqual(-1);

  const originalWorkspaceHeight = measurements.clientHeight;
  await page.setViewportSize({ width: 393, height: 568 });
  await expect
    .poll(() =>
      page.evaluate(
        () =>
          document.querySelector<HTMLElement>(
            '[data-testid="coefficient-editor-scroll"]',
          )?.clientHeight ?? 0,
      ),
    )
    .toBeLessThan(originalWorkspaceHeight);
  await expect
    .poll(async () => (await focusedBounds()).rightGap)
    .toBeGreaterThanOrEqual(-1);
  await expect
    .poll(async () => (await focusedBounds()).bottomGap)
    .toBeGreaterThanOrEqual(-1);
});

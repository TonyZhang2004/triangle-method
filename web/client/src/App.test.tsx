import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import { positiveCubicMonomialProof, zeroProof } from "./test/fixtures";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.history.replaceState(null, "", "/");
});

describe("coefficient proof workflow", () => {
  it("opens as a titleless cubic editor with ten canonically labeled inputs", () => {
    const { container } = render(<App />);

    expect(screen.queryByRole("heading", { level: 1 })).not.toBeInTheDocument();
    const degree = screen.getByLabelText<HTMLSelectElement>("Degree");
    expect(degree).toHaveValue("3");
    expect(Array.from(degree.options, (option) => option.value)).toEqual([
      "2",
      "3",
      "4",
      "5",
      "6",
      "7",
      "8",
      "9",
      "10",
      "11",
      "12",
    ]);
    expect(screen.getAllByRole("textbox")).toHaveLength(10);
    expect(
      screen.getByLabelText("Coefficient of x to the power 3"),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Coefficient of x to the power 3")).toHaveAttribute(
      "maxlength",
      "130",
    );
    expect(
      screen.getByLabelText("Coefficient of y times z to the power 2"),
    ).toBeInTheDocument();

    const firstRow = container.querySelector<HTMLElement>(
      '.coefficient-input-slot[data-row="1"][data-column="0"]',
    );
    const secondRow = container.querySelector<HTMLElement>(
      '.coefficient-input-slot[data-row="1"][data-column="1"]',
    );
    expect(firstRow?.dataset.x).toBe("-78");
    expect(secondRow?.dataset.x).toBe("78");
    expect(Number(firstRow?.dataset.y)).toBeCloseTo((Math.sqrt(3) / 2) * 156, 5);
  });

  it("renders all 91 degree-twelve inputs on the same exact equilateral lattice", async () => {
    const user = userEvent.setup();
    const { container } = render(<App />);

    await user.selectOptions(screen.getByLabelText("Degree"), "12");

    expect(screen.getAllByRole("textbox")).toHaveLength(91);
    expect(screen.getByText("0 of 91 entered")).toBeVisible();
    expect(
      screen.getByText(/Paste a full space, comma, or tab-separated row/i),
    ).toBeVisible();
    const canvas = container.querySelector<HTMLElement>(
      '.input-triangle[data-degree="12"]',
    );
    expect(canvas).toHaveStyle({ width: "2024px" });
    const workspace = screen.getByTestId("coefficient-editor-scroll");
    expect(workspace).toHaveClass("input-triangle-scroll-large");

    const point = (row: number, column: number) =>
      container.querySelector<HTMLElement>(
        `.coefficient-input-slot[data-row="${row}"][data-column="${column}"]`,
      )!;
    const apex = point(0, 0);
    const baseLeft = point(12, 0);
    const baseRight = point(12, 12);
    const interior = point(7, 3);
    expect(Number(apex.dataset.x)).toBe(0);
    expect(Number(apex.dataset.y)).toBe(0);
    expect(Number(baseLeft.dataset.x)).toBe(-6 * 156);
    expect(Number(baseRight.dataset.x)).toBe(6 * 156);
    expect(Number(baseLeft.dataset.y)).toBeCloseTo(
      12 * (Math.sqrt(3) / 2) * 156,
      5,
    );
    expect(Number(baseRight.dataset.y)).toBeCloseTo(
      Number(baseLeft.dataset.y),
      8,
    );
    expect(Number(interior.dataset.x)).toBe((3 - 7 / 2) * 156);
    expect(Number(interior.dataset.y)).toBeCloseTo(
      7 * (Math.sqrt(3) / 2) * 156,
      5,
    );
  });

  it("jumps to and fills a high-degree row from spreadsheet-style paste", async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.selectOptions(screen.getByLabelText("Degree"), "12");

    await user.selectOptions(screen.getByLabelText("Jump to row"), "12");
    const first = document.getElementById("coefficient-12-12-0");
    expect(first).toHaveFocus();

    const values = Array.from({ length: 13 }, (_, index) => String(index + 1));
    fireEvent.paste(first!, {
      clipboardData: { getData: () => values.join("\t") },
    });

    expect(first).toHaveValue("1");
    expect(document.getElementById("coefficient-12-12-6")).toHaveValue("7");
    expect(document.getElementById("coefficient-12-12-12")).toHaveValue("13");
    expect(screen.getByText("13 of 91 entered")).toBeVisible();
    expect(
      screen.getByText("Filled all 13 coefficients in row 13."),
    ).toBeVisible();
  });

  it("preserves each degree's draft while changing the triangle size", async () => {
    const user = userEvent.setup();
    render(<App />);
    const cubicApex = screen.getByLabelText("Coefficient of x to the power 3");
    await user.type(cubicApex, "7/3");

    await user.selectOptions(screen.getByLabelText("Degree"), "12");
    expect(screen.getAllByRole("textbox")).toHaveLength(91);
    await user.type(document.getElementById("coefficient-12-12-12")!, "5");
    await user.selectOptions(screen.getByLabelText("Degree"), "3");
    expect(screen.getByLabelText("Coefficient of x to the power 3")).toHaveValue(
      "7/3",
    );
    await user.selectOptions(screen.getByLabelText("Degree"), "12");
    expect(document.getElementById("coefficient-12-12-12")).toHaveValue("5");
  });

  it("submits a complete degree-twelve request with blanks normalized to zero", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(zeroProof(12)), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<App />);
    await user.selectOptions(screen.getByLabelText("Degree"), "12");
    await user.click(screen.getByRole("button", { name: "Prove" }));

    expect(await screen.findByRole("heading", { name: "Proved" })).toBeVisible();
    expect(screen.getByTestId("proof-page")).toBeVisible();
    expect(screen.queryByTestId("editor-page")).not.toBeInTheDocument();
    expect(window.location.hash).toBe("#proof");
    const init = fetchMock.mock.calls[0][1] as RequestInit;
    const request = JSON.parse(String(init.body)) as {
      degree: number;
      coefficientRows: string[][];
    };
    expect(request.degree).toBe(12);
    expect(request.coefficientRows.map((row) => row.length)).toEqual(
      Array.from({ length: 13 }, (_, row) => row + 1),
    );
    expect(request.coefficientRows.flat()).toHaveLength(91);
    expect(new Set(request.coefficientRows.flat())).toEqual(new Set(["0"]));
  });

  it("focuses the first invalid exact coefficient without sending a request", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<App />);
    const apex = screen.getByLabelText("Coefficient of x to the power 3");
    await user.type(apex, "0.5");
    await user.click(screen.getByRole("button", { name: "Prove" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Fix 1 invalid coefficient",
    );
    await waitFor(() => expect(apex).toHaveFocus());
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("normalizes blank coefficients, submits the versioned contract, and renders a result", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(zeroProof(3)), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByRole("button", { name: "Prove" }));

    expect(await screen.findByRole("heading", { name: "Proved" })).toBeVisible();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect(JSON.parse(String(init.body))).toEqual({
      schema: "triangle_method.proof_request",
      schemaVersion: 1,
      degree: 3,
      coefficientRows: [["0"], ["0", "0"], ["0", "0", "0"], ["0", "0", "0", "0"]],
    });
    expect(screen.getByText(/final remainder is zero/i)).toBeVisible();
    expect(screen.queryByLabelText("Degree")).not.toBeInTheDocument();
  });

  it("opens the proof page immediately while the backend is searching", async () => {
    let finishRequest: (response: Response) => void = () => undefined;
    const fetchMock = vi.fn().mockImplementation(
      () =>
        new Promise<Response>((resolve) => {
          finishRequest = resolve;
        }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole("button", { name: "Prove" }));

    expect(screen.getByTestId("proof-page")).toBeVisible();
    expect(screen.queryByTestId("editor-page")).not.toBeInTheDocument();
    const loading = screen.getByText(
      "Searching for an exact proof certificate…",
    ).parentElement!;
    expect(loading).toBeVisible();
    await waitFor(() => expect(loading).toHaveFocus());
    expect(window.location.hash).toBe("#proof");

    finishRequest(
      new Response(JSON.stringify(zeroProof(3)), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    const heading = await screen.findByRole("heading", { name: "Proved" });
    await waitFor(() => expect(heading).toHaveFocus());
  });

  it("preserves coefficients and retries a failed request", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ message: "The solver is temporarily busy." }), {
          status: 503,
          headers: { "Content-Type": "application/json" },
        }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify(positiveCubicMonomialProof()), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<App />);
    const apex = screen.getByLabelText("Coefficient of x to the power 3");
    await user.type(apex, "1");
    await user.click(screen.getByRole("button", { name: "Prove" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "The solver is temporarily busy.",
    );
    expect(apex).toHaveValue("1");
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("heading", { name: "Proved" })).toBeVisible();
    expect(fetchMock).toHaveBeenCalledTimes(2);
    await user.click(screen.getByRole("button", { name: "Back to inequality" }));
    expect(
      await screen.findByLabelText("Coefficient of x to the power 3"),
    ).toHaveValue("1");
  });

  it("returns from the proof page with the draft preserved for editing", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify(zeroProof(3)), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByRole("button", { name: "Prove" }));
    expect(await screen.findByRole("heading", { name: "Proved" })).toBeVisible();

    await user.click(screen.getByRole("button", { name: "Back to inequality" }));
    const apex = await screen.findByLabelText("Coefficient of x to the power 3");
    expect(apex).toHaveValue("");
    await user.type(apex, "1");
    expect(screen.queryByRole("heading", { name: "Proved" })).not.toBeInTheDocument();
    expect(screen.getByTestId("editor-page")).toBeVisible();
  });
});

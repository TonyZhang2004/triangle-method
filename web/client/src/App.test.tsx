import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import { positiveCubicMonomialProof, zeroProof } from "./test/fixtures";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("coefficient proof workflow", () => {
  it("opens as a titleless cubic editor with ten canonically labeled inputs", () => {
    const { container } = render(<App />);

    expect(screen.queryByRole("heading", { level: 1 })).not.toBeInTheDocument();
    expect(screen.getByLabelText("Degree")).toHaveValue("3");
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

  it("preserves each degree's draft while changing the triangle size", async () => {
    const user = userEvent.setup();
    render(<App />);
    const cubicApex = screen.getByLabelText("Coefficient of x to the power 3");
    await user.type(cubicApex, "7/3");

    await user.selectOptions(screen.getByLabelText("Degree"), "5");
    expect(screen.getAllByRole("textbox")).toHaveLength(21);
    await user.selectOptions(screen.getByLabelText("Degree"), "3");
    expect(screen.getByLabelText("Coefficient of x to the power 3")).toHaveValue(
      "7/3",
    );
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
    expect(apex).toHaveValue("1");
  });

  it("clears a rendered proof as soon as the coefficient draft changes", async () => {
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

    await user.type(screen.getByLabelText("Coefficient of x to the power 3"), "1");
    expect(screen.queryByRole("heading", { name: "Proved" })).not.toBeInTheDocument();
  });
});

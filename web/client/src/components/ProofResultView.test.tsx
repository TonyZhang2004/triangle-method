import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";

import {
  combinedCauchyAmGmProof,
  disprovedProof,
  unknownProof,
  zeroProof,
} from "../test/fixtures";
import { ProofResultView } from "./ProofResultView";

afterEach(cleanup);

describe("proof result presentation", () => {
  it("shows a colored four-term identity and a coefficient-only target triangle", () => {
    const response = combinedCauchyAmGmProof();
    const { container } = render(<ProofResultView result={response} />);

    expect(screen.getByRole("heading", { name: "Proved" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "Squares completed" })).toBeVisible();
    expect(screen.getByText("AM-GM")).toBeVisible();
    expect(screen.getByText("Cauchy")).toBeVisible();
    expect(container.querySelector(".output-triangle .monomial-label")).toBeNull();

    const target = screen.getByRole("img", {
      name: /Target coefficient triangle/,
    });
    const apex = target.querySelector<HTMLElement>(
      '.coefficient-mark[data-row="0"][data-column="0"]',
    );
    expect(apex?.dataset.coefficient).toBe("3");
    expect(apex?.children).toHaveLength(1);
    expect(target.querySelector(".overlap-marker")).not.toBeInTheDocument();
    expect(target.className).not.toContain("component-color-");

    const identityTerms = container.querySelectorAll(".identity-term");
    expect(identityTerms).toHaveLength(4);
    expect(identityTerms[0]).toHaveClass("component-color-0");
    expect(identityTerms[1]).toHaveClass("component-color-0");
    expect(identityTerms[2]).toHaveClass("component-color-0");
    expect(identityTerms[3]).toHaveClass("component-color-1");
    expect(container.querySelector(".identity-nonnegative .mrel")).toHaveTextContent(
      "≥",
    );
    expect(container.querySelector(".structured-proof-identity")).toHaveAttribute(
      "aria-label",
      response.proof?.identityLatex,
    );
    expect(
      container.querySelectorAll(".structured-proof-identity [role='math']"),
    ).toHaveLength(0);
  });

  it("steps through component, accumulated, and exact remainder triangles", async () => {
    const user = userEvent.setup();
    render(<ProofResultView result={combinedCauchyAmGmProof()} />);

    await user.click(screen.getByRole("button", { name: /component-1/i }));
    let triangle = screen.getByRole("img", { name: /Component component-1/ });
    expect(
      triangle.querySelector('[data-row="0"][data-column="0"]'),
    ).toHaveAttribute("data-coefficient", "1");

    await user.click(screen.getByRole("button", { name: "Remainder" }));
    triangle = screen.getByRole("img", { name: /Remainder after component-1/ });
    expect(
      triangle.querySelector('[data-row="0"][data-column="0"]'),
    ).toHaveAttribute("data-coefficient", "2");

    await user.click(screen.getByRole("button", { name: "Next" }));
    expect(
      screen.getByRole("img", { name: /Remainder after component-2/ }),
    ).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Next" }));
    expect(
      screen.getByRole("img", { name: /Remainder after component-3/ }),
    ).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Next" }));
    triangle = screen.getByRole("img", { name: /Remainder after component-4/ });
    expect(
      Array.from(triangle.querySelectorAll<HTMLElement>(".coefficient-mark")).map(
        (mark) => mark.dataset.coefficient,
      ),
    ).toEqual(["0", "0", "0", "0", "0", "0"]);
    expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();

    await user.click(screen.getByRole("button", { name: "Accumulated" }));
    expect(
      screen.getByRole("img", { name: /Accumulated through component-4/ }),
    ).toBeVisible();
  });

  it("renders a single accessible zero-term proof identity", () => {
    const { container } = render(<ProofResultView result={zeroProof(2)} />);
    const identity = container.querySelector(".structured-proof-identity");

    expect(identity).toHaveAttribute("aria-label", "0 = 0 \\ge 0");
    expect(identity?.querySelectorAll(".identity-term")).toHaveLength(0);
    expect(identity?.querySelectorAll(".math-formula")).toHaveLength(3);
  });

  it("explains UNKNOWN without implying that the target is false", () => {
    render(<ProofResultView result={unknownProof()} />);

    expect(screen.getByRole("heading", { name: "Search inconclusive" })).toBeVisible();
    expect(screen.getByText(/does not decide whether the inequality is true/i)).toBeVisible();
    expect(screen.getByRole("img", { name: /Target coefficient triangle/ })).toBeVisible();
  });

  it("shows an exact negative witness for a disproved inequality", async () => {
    const user = userEvent.setup();
    render(<ProofResultView result={disprovedProof()} />);

    expect(
      screen.getByRole("heading", { name: "Counterexample found" }),
    ).toBeVisible();
    expect(screen.getByText(/exact nonnegative point/i)).toBeVisible();
    const details = screen.getByText("Search details");
    await user.click(details);
    expect(
      within(details.closest("details")!).getByText("counterexample.found"),
    ).toBeVisible();
  });
});

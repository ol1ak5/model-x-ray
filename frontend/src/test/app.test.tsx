import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";

import App from "../App";
import { APPROVED, CELL_CHOICE, REJECTED, REVIEW, STEPS, fakeApi, steps } from "./fakeApi";

afterEach(() => vi.unstubAllGlobals());

async function ask(question: string) {
  const user = userEvent.setup();
  render(<App />);
  await user.selectOptions(await screen.findByLabelText("Model"), "demo");
  await user.type(screen.getByLabelText("Question"), question);
  await user.click(screen.getByRole("button", { name: "Investigate" }));
  return user;
}

describe("an investigation in the browser", () => {
  test("streams every step, shows the evidence, and offers the corrected file after approval", async () => {
    const api = fakeApi(
      [...steps(...STEPS.map(([name]) => name)), ["view", REVIEW]],
      [[...steps("human_review", "apply_fix"), ["view", APPROVED]]],
    );
    vi.stubGlobal("fetch", api.fetch);
    const user = await ask("Why did EBITDA 2027 jump?");

    const progress = await screen.findByRole("list", { name: "Progress" });
    for (const [, label] of STEPS) expect(await within(progress).findByText(label)).toBeInTheDocument();

    const report = await screen.findByRole("region", { name: "Report" });
    expect(within(report).getByText(/Root cause found in P&L!H7/)).toBeInTheDocument();
    expect(within(report).getByRole("link", { name: "ev-3" })).toHaveAttribute("href", "#ev-3");

    const board = screen.getByRole("region", { name: "Hypotheses" });
    expect(within(within(board).getByRole("group", { name: "Confirmed" })).getByText("P&L!H7")).toBeInTheDocument();
    expect(within(within(board).getByRole("group", { name: "Confirmed" })).getByText("high confidence")).toBeInTheDocument();
    expect(within(within(board).getByRole("group", { name: "Rejected" })).getByText("P&L!H5")).toBeInTheDocument();

    const tree = screen.getByRole("region", { name: "Cause tree" });
    expect(within(tree).getByText("Opex")).toBeInTheDocument();
    expect(within(tree).getByText("Suspicious")).toBeInTheDocument();
    expect(within(tree).getByText("after fix -52.48")).toBeInTheDocument();

    const evidence = screen.getByRole("region", { name: "Evidence" });
    expect(within(evidence).getByText(/52.01 -> 44.73 in a sandbox copy/)).toBeInTheDocument();
    expect(document.getElementById("ev-3")).not.toBeNull();

    await user.type(screen.getByLabelText("Reason"), "typed opex");
    await user.click(screen.getByRole("button", { name: "Approve fix" }));

    expect(await screen.findByRole("link", { name: "Download corrected model" })).toHaveAttribute("href", "http://localhost:8000/investigations/inv-1/corrected");
    expect(api.sent.at(-1)).toEqual({ url: "http://localhost:8000/investigations/inv-1/resume/stream", body: { action: "approve", reason: "typed opex" } });
    expect(within(progress).getByText("Saving a new version")).toBeInTheDocument();
  });

  test("asks which cell is meant, then remembers a rejection marked intentional", async () => {
    const api = fakeApi(
      [...steps("load_sheet", "map_model", "locate"), ["view", CELL_CHOICE]],
      [
        [...steps("trace", "diagnose", "test", "verify", "explain"), ["view", REVIEW]],
        [...steps("human_review"), ["view", REJECTED]],
      ],
    );
    vi.stubGlobal("fetch", api.fetch);
    const user = await ask("Why did EBITDA 2027 jump?");

    const choice = await screen.findByRole("group", { name: "Which cell do you mean?" });
    await user.click(within(choice).getByRole("button", { name: "Summary!D10" }));
    expect(api.sent.at(-1)?.body).toEqual({ ref: "Summary!D10" });

    await screen.findByRole("region", { name: "Report" });
    await user.type(screen.getByLabelText("Reason"), "Opex frozen per budget meeting");
    await user.click(screen.getByLabelText("This is intentional, do not flag it again"));
    await user.click(screen.getByRole("button", { name: "Reject" }));

    expect(await screen.findByText("Closed without changes. Your decision is saved.")).toBeInTheDocument();
    expect(api.sent.at(-1)?.body).toEqual({ action: "reject", reason: "Opex frozen per budget meeting", intentional: true });
    expect(screen.queryByRole("link", { name: "Download corrected model" })).not.toBeInTheDocument();
  });

  test("lets the reviewer edit the fix, which is tested again", async () => {
    const api = fakeApi([...steps("explain"), ["view", REVIEW]], [[...steps("human_review", "test", "verify", "explain"), ["view", REVIEW]]]);
    vi.stubGlobal("fetch", api.fetch);
    const user = await ask("Why did EBITDA 2027 jump?");

    await user.click(await screen.findByRole("button", { name: "Edit fix" }));
    const formula = screen.getByLabelText("New formula for P&L!H7");
    expect(formula).toHaveValue("=G7*(1+Assumptions!$C$7)");
    await user.clear(formula);
    await user.type(formula, "=G7*1.05");
    await user.type(screen.getByLabelText("Reason"), "use the budget growth");
    await user.click(screen.getByRole("button", { name: "Test my fix" }));

    expect(api.sent.at(-1)?.body).toEqual({
      action: "edit",
      reason: "use the budget growth",
      patch: { cell: "P&L!H7", old_formula: "-45.2", new_formula: "=G7*1.05" },
    });
    expect(await screen.findByRole("region", { name: "Report" })).toBeInTheDocument();
  });

  test("shows a short message when the investigation fails", async () => {
    const api = fakeApi([...steps("load_sheet", "map_model"), ["error", 503, "The AI service took too long to answer. Please try again in a minute."]]);
    vi.stubGlobal("fetch", api.fetch);
    await ask("Why did EBITDA 2027 jump?");

    expect(await screen.findByRole("alert")).toHaveTextContent("The AI service took too long to answer. Please try again in a minute.");
    expect(screen.getByRole("button", { name: "Investigate" })).toBeEnabled();
  });
});

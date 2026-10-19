import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";

import App from "../App";
import { APPROVED, CELL_CHOICE, REJECTED, REVIEW, RUNNING, STEPS, TESTED, fakeApi, steps } from "./fakeApi";

afterEach(() => {
  window.history.replaceState(null, "", "/");
  vi.unstubAllGlobals();
});

function lastResume(api: ReturnType<typeof fakeApi>) {
  return api.sent.filter((request) => request.url.includes("/resume/")).at(-1);
}

async function checkDemo() {
  const user = userEvent.setup();
  render(<App />);
  await user.click(await screen.findByRole("button", { name: "See it in action" }));
  return user;
}

describe("an investigation in the browser", () => {
  test("checks an uploaded model, draws the traced dependencies on the sheet, and offers the corrected file after approval", async () => {
    const api = fakeApi(
      [...steps(...STEPS.map(([name]) => name)), ["view", REVIEW]],
      [[...steps("human_review", "apply_fix"), ["view", APPROVED]]],
    );
    vi.stubGlobal("fetch", api.fetch);
    const user = userEvent.setup();
    render(<App />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Every formula, checked. Under the X-Ray.");
    await user.upload(screen.getByLabelText(/Upload your model/), new File(["xlsx bytes"], "My model.xlsx"));
    expect(await screen.findByText("My model.xlsx")).toBeInTheDocument();
    expect(api.sent.find((request) => request.url.endsWith("/investigations/stream"))?.body).toEqual({ spreadsheet_id: "upload-1", question: "" });

    const grid = await screen.findByRole("region", { name: "Sheet" });
    expect(within(grid).getByRole("button", { name: "P&L!G5, confirmed" })).toHaveTextContent("97.8");
    expect(within(grid).getByText("=-G4*Assumptions!$C$5")).toBeInTheDocument();
    await user.click(within(grid).getByRole("button", { name: "P&L!H4" }));
    expect(within(grid).getByText("=G4*(1+Assumptions!$C$4)")).toBeInTheDocument();

    await waitFor(() => expect(document.querySelectorAll("[data-edge]")).toHaveLength(3));
    expect(document.querySelector("[data-patch=\"P&L!G5\"]")).not.toBeNull();
    expect(screen.getByText("contributes")).toBeInTheDocument();

    const facts = await screen.findByRole("region", { name: "Investigation facts" });
    expect(within(facts).getByText("Gross profit 2025A")).toBeInTheDocument();
    expect(within(facts).getByText(/84\.7 → 285\.8/)).toBeInTheDocument();
    expect(within(facts).getByText("Proof passed")).toBeInTheDocument();
    const checks = within(facts).getByLabelText("Deterministic checks");
    expect(checks.querySelectorAll('[data-state="pass"]')).toHaveLength(3);

    await user.click(within(facts).getByRole("button", { name: "Why?" }));
    const report = within(facts).getByRole("region", { name: "Report" });
    expect(within(report).getByText(/Gross profit 2025A moved from 84\.72 to 285\.76/)).toBeInTheDocument();
    await user.click(within(report).getByRole("link", { name: "ev-7" }));
    await waitFor(() => expect(document.querySelector("[data-highlight=\"P&L!G5\"]")).not.toBeNull());

    await user.type(within(facts).getByLabelText("Reason"), "sign slip on COGS");
    await user.click(within(facts).getByRole("button", { name: "Approve fix" }));

    expect(await screen.findByRole("link", { name: "Download corrected model" })).toHaveAttribute("href", `http://localhost:8000/investigations/${APPROVED.id}/corrected`);
    expect(lastResume(api)).toMatchObject({
      url: `http://localhost:8000/investigations/${REVIEW.id}/resume/stream`,
      body: { action: "approve", reason: "sign slip on COGS", state: { id: REVIEW.id, status: "needs_review" } },
    });
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
    const user = await checkDemo();
    expect(api.sent.find((request) => request.url.endsWith("/investigations/stream"))?.body).toEqual({ spreadsheet_id: "demo", question: "" });

    const choice = await screen.findByRole("group", { name: "Which cell do you mean?" });
    await user.click(within(choice).getByRole("button", { name: "Summary!D10" }));
    expect(lastResume(api)?.body).toMatchObject({ ref: "Summary!D10" });
    const facts = await screen.findByRole("region", { name: "Investigation facts" });
    await user.type(within(facts).getByLabelText("Reason"), "Opex frozen per budget meeting");
    await user.click(within(facts).getByLabelText("Never flag again"));
    await user.click(within(facts).getByRole("button", { name: "Reject" }));

    expect(await screen.findByText("Closed without changes. Your decision is saved.")).toBeInTheDocument();
    expect(lastResume(api)?.body).toMatchObject({ action: "reject", reason: "Opex frozen per budget meeting", intentional: true });
    expect(screen.queryByRole("link", { name: "Download corrected model" })).not.toBeInTheDocument();
  });

  test("lets the reviewer edit the fix, which is tested again", async () => {
    const api = fakeApi([...steps("explain"), ["view", REVIEW]], [[...steps("human_review", "test", "verify", "explain"), ["view", REVIEW]]]);
    vi.stubGlobal("fetch", api.fetch);
    const user = await checkDemo();

    const facts = await screen.findByRole("region", { name: "Investigation facts" });
    await user.click(within(facts).getByRole("button", { name: "Edit fix" }));
    const formula = within(facts).getByLabelText("New formula for P&L!G5");
    expect(formula).toHaveValue("=-G4*Assumptions!$C$5");
    await user.clear(formula);
    await user.type(formula, "=-G4*Assumptions!$C$4");
    await user.type(within(facts).getByLabelText("Reason"), "use the budget growth");
    await user.click(within(facts).getByRole("button", { name: "Test my fix" }));

    expect(lastResume(api)?.body).toMatchObject({
      action: "edit",
      reason: "use the budget growth",
      patch: { cell: "P&L!G5", old_formula: "=G4*Assumptions!$C$5", new_formula: "=-G4*Assumptions!$C$4" },
    });
    expect(await screen.findByRole("region", { name: "Investigation facts" })).toBeInTheDocument();
  });

  test("keeps the sheet, the decision and the reason on screen when a fix cannot be calculated", async () => {
    const api = fakeApi(
      [...steps("explain"), ["view", REVIEW]],
      [],
      ["That fix does not work in P&L!G5: Unsupported function SUMX in P&L!G5. Enter a number, or a formula that starts with =."],
    );
    vi.stubGlobal("fetch", api.fetch);
    const user = await checkDemo();

    const facts = await screen.findByRole("region", { name: "Investigation facts" });
    await user.click(within(facts).getByRole("button", { name: "Edit fix" }));
    const formula = within(facts).getByLabelText("New formula for P&L!G5");
    await user.clear(formula);
    await user.type(formula, "=SUMX(G4)");
    await user.click(within(facts).getByRole("button", { name: "Test my fix" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("starts with =");
    expect(api.sent.at(-1)?.body).toMatchObject({
      action: "edit",
      reason: "",
      patch: { cell: "P&L!G5", old_formula: "=G4*Assumptions!$C$5", new_formula: "=SUMX(G4)" },
      state: { id: REVIEW.id },
    });
    expect(screen.getByRole("region", { name: "Sheet" })).toBeInTheDocument();
    expect(screen.getByText("Review needed")).toBeInTheDocument();
    expect(within(facts).getByRole("button", { name: "Test my fix" })).toBeInTheDocument();
  });

  test("shows a short message when the investigation fails", async () => {
    const api = fakeApi([...steps("load_sheet", "map_model"), ["error", 503, "The AI service took too long to answer. Please try again in a minute."]]);
    vi.stubGlobal("fetch", api.fetch);
    await checkDemo();

    expect(await screen.findByRole("alert")).toHaveTextContent("The AI service took too long to answer. Please try again in a minute.");
    expect(screen.getByRole("button", { name: "Check another model" })).toBeEnabled();
  });

  test("shows the model being read while the first pass runs, with the steps already listed", async () => {
    const api = fakeApi([...steps("load_sheet", "map_model")]);
    vi.stubGlobal("fetch", api.fetch);
    await checkDemo();

    const rail = await screen.findByRole("region", { name: "Investigation steps" });
    const rows = within(rail).getAllByRole("listitem");
    expect(rows.map((row) => row.getAttribute("data-tone"))).toEqual(["done", "done", "active", "pending", "pending", "pending", "pending", "pending"]);

    const frame = screen.getByRole("region", { name: "Sheet" });
    expect(frame).toHaveAttribute("aria-busy", "true");
    expect(within(frame).getByText("Scanning the model — every formula, read in a copy")).toBeInTheDocument();
  });

  test("keeps the model frame and the steps on screen while the agent asks which cell is meant", async () => {
    const api = fakeApi([...steps("load_sheet", "map_model", "locate"), ["view", CELL_CHOICE]]);
    vi.stubGlobal("fetch", api.fetch);
    await checkDemo();

    expect(await screen.findByRole("group", { name: "Which cell do you mean?" })).toBeInTheDocument();
    const rail = within(screen.getByRole("region", { name: "Investigation steps" }));
    const rows = rail.getAllByRole("listitem");
    expect(rows.map((row) => row.getAttribute("data-tone"))).toEqual(["done", "done", "done", "active", "pending", "pending", "pending", "pending"]);
    expect(rows[3].getAttribute("data-tone")).toBe("active");

    const frame = screen.getByRole("region", { name: "Sheet" });
    expect(within(frame).getByText("Waiting for you to pick the cell")).toBeInTheDocument();
  });

  test("explains the investigation step by step, with what each step found", async () => {
    const api = fakeApi([...steps(...STEPS.map(([name]) => name)), ["view", REVIEW]]);
    vi.stubGlobal("fetch", api.fetch);
    await checkDemo();

    const rail = await screen.findByRole("region", { name: "Investigation steps" });
    await waitFor(() => expect(within(rail).getAllByRole("listitem")).toHaveLength(8));

    const rows = within(rail).getAllByRole("listitem");
    expect(rows.map((row) => row.getAttribute("data-tone"))).toEqual(Array.from({ length: 8 }, () => "done"));
    expect(within(rows[2]).getByText("Gross profit 2025A · 84.7 → 285.8")).toBeInTheDocument();
    expect(within(rows[3]).getByText("Revenue +11.5 · COGS +189.5")).toBeInTheDocument();
    expect(within(rows[4]).getByText(/^P&L!G5 — The formula lacks the negative sign/)).toBeInTheDocument();
    expect(within(rows[5]).getByText("P&L!G5 =G4*Assumptions!$C$5 → =-G4*Assumptions!$C$5")).toBeInTheDocument();
    expect(within(rows[6]).getByText("3 of 3 checks passed · proof passed")).toBeInTheDocument();
    expect(within(rows[7]).getByText(/Report ready · \d+ evidence links/)).toBeInTheDocument();
  });

  test("writes what the run found on every arrow, and the diagnosis on the broken one", async () => {
    const api = fakeApi([...steps(...STEPS.map(([name]) => name)), ["view", REVIEW]]);
    vi.stubGlobal("fetch", api.fetch);
    await checkDemo();

    await waitFor(() => expect(document.querySelectorAll("[data-wire-label]")).toHaveLength(2));
    expect(document.querySelector("[data-wire-label='P&L!G4->P&L!G5']")).toBeNull();

    const culprit = document.querySelector("[data-wire-label='P&L!G5->P&L!G6']");
    expect(culprit).toHaveAttribute("data-tone", "bad");
    expect(culprit?.textContent).toContain("COGS +189.5");
    expect(culprit?.textContent).toContain("sign inconsistency");
    expect(culprit).toHaveAttribute("title", "The formula lacks the negative sign present in neighboring cells, causing COGS to be positive instead of negative.");

    const revenue = document.querySelector("[data-wire-label='P&L!G4->P&L!G6']");
    expect(revenue).toHaveAttribute("data-tone", "ok");
    expect(revenue?.textContent).toContain("Revenue +11.5");
    expect(revenue?.textContent).toContain("6% of the move");
  });

  test("keeps the model, the steps and the facts on screen while the fix has been tested but not checked", async () => {
    const api = fakeApi([...steps("load_sheet", "map_model", "locate", "trace", "diagnose", "test"), ["view", TESTED]]);
    vi.stubGlobal("fetch", api.fetch);
    await checkDemo();

    const rail = await screen.findByRole("region", { name: "Investigation steps" });
    await waitFor(() => expect(within(rail).getAllByRole("listitem")).toHaveLength(8));
    const rows = within(rail).getAllByRole("listitem");
    expect(rows[5].getAttribute("data-tone")).toBe("done");
    expect(within(rows[5]).getByText("P&L!G5 =G4*Assumptions!$C$5 → =-G4*Assumptions!$C$5")).toBeInTheDocument();
    expect(rows[6].getAttribute("data-tone")).toBe("active");
    expect(within(rows[6]).getByText("Independent checks on the result")).toBeInTheDocument();

    await waitFor(() => expect(document.querySelectorAll("[data-edge]")).toHaveLength(3));
    expect(screen.getByRole("button", { name: "P&L!G5, suspicious" })).toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: "Investigation facts" })).getByText("Gross profit 2025A")).toBeInTheDocument();
  });

  test("lights up the steps as the agent works through them", async () => {
    const api = fakeApi([...steps("load_sheet", "map_model", "locate", "trace", "diagnose"), ["view", RUNNING]]);
    vi.stubGlobal("fetch", api.fetch);
    await checkDemo();

    const rail = await screen.findByRole("region", { name: "Investigation steps" });
    const rows = within(rail).getAllByRole("listitem");
    await waitFor(() => expect(rows[5].getAttribute("data-tone")).toBe("active"));

    expect(rows.slice(0, 5).map((row) => row.getAttribute("data-tone"))).toEqual(["done", "done", "done", "done", "done"]);
    expect(rows[6].getAttribute("data-tone")).toBe("pending");
    expect(within(rows[2]).getByText("Gross profit 2025A · 84.7 → 285.8")).toBeInTheDocument();
    expect(within(rows[4]).getByText("Looking for the root cause")).toBeInTheDocument();
    expect(within(rows[5]).getByText("Your own file is never touched")).toBeInTheDocument();
  });

  test("does not restart the steps when a resumed run only re-tests the fix", async () => {
    const api = fakeApi([...steps("explain"), ["view", REVIEW]], [[...steps("human_review", "test", "verify", "explain"), ["view", APPROVED]]]);
    vi.stubGlobal("fetch", api.fetch);
    const user = await checkDemo();

    const facts = await screen.findByRole("region", { name: "Investigation facts" });
    await user.click(within(facts).getByRole("button", { name: "Approve fix" }));

    const rail = within(screen.getByRole("region", { name: "Investigation steps" }));
    expect(rail.getByText("Opened the model").closest("li")).toHaveAttribute("data-tone", "done");
    expect(rail.getByText("Found the root cause").closest("li")).toHaveAttribute("data-tone", "done");
    await waitFor(() => expect(rail.getByText("Saved the corrected copy")).toBeInTheDocument());
  });

  test("leaves the dev story behind when the reviewer goes back to the landing", async () => {
    window.history.replaceState(null, "", "/?story=workspace");
    const api = fakeApi([]);
    vi.stubGlobal("fetch", api.fetch);
    const user = userEvent.setup();
    render(<App />);

    expect(await screen.findByRole("region", { name: "Sheet" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Check another model" }));

    expect(window.location.search).toBe("");
    expect(await screen.findByRole("button", { name: "See it in action" })).toBeInTheDocument();
  });
});

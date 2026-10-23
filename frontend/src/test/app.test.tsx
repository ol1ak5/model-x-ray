import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";

import App from "../App";
import type { InvestigationView } from "../api";
import { APPROVED, REJECTED, REVIEW, RUNNING, STEPS, TESTED, fakeApi, steps } from "./fakeApi";

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

describe("the home page", () => {
  test("tells the story section by section and leaves it for the workspace once a check starts", async () => {
    vi.stubGlobal("fetch", fakeApi([...steps(...STEPS.map(([name]) => name)), ["view", REVIEW]]).fetch);
    const user = userEvent.setup();
    render(<App />);
    const sections = screen.getByRole("navigation", { name: "Sections" });
    for (const [link, heading] of [
      ["Why", "One broken formula can move a valuation."],
      ["Strengths", "Built the way an analyst checks a model."],
      ["How it works", "Ten steps, one state machine."],
      ["Stack", "Built on Nebius × NVIDIA."],
    ]) {
      const target = within(sections).getByRole("link", { name: link }).getAttribute("href") as string;
      expect(document.querySelector(target)).toContainElement(screen.getByRole("heading", { level: 2, name: heading }));
    }
    const results = screen.getByRole("table", { name: "Results" });
    expect(within(results).getByText("98%")).toBeInTheDocument();
    expect(within(results).getByText(/against 86% with rules alone/)).toBeInTheDocument();

    await user.click(await screen.findByRole("button", { name: "See it in action" }));
    expect(await screen.findByText("Review needed")).toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: "Sections" })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { level: 2, name: "Ten steps, one state machine." })).not.toBeInTheDocument();
  });
});

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
    expect(within(facts).getByText("3 of 3 checks")).toBeInTheDocument();
    expect(within(facts).getByText(/Fix ready in/)).toBeInTheDocument();
    const checks = within(facts).getByLabelText("Deterministic checks");
    expect(checks.querySelectorAll('[data-state="pass"]')).toHaveLength(3);

    const report = within(facts).getByRole("region", { name: "Report" });
    expect(within(report).getByText(/Gross profit 2025A moved from 84\.72 to 285\.76/)).toBeInTheDocument();
    const cited = (REVIEW.report ?? "").match(/ev-\d+/g) ?? [];
    const onG5 = cited.find((id) => (REVIEW.evidence ?? []).some((record) => record.id === id && record.cell === "P&L!G5"));
    expect(onG5).toBeDefined();
    await user.click(within(report).getByRole("link", { name: onG5 as string }));
    await waitFor(() => expect(document.querySelector("[data-highlight=\"P&L!G5\"]")).not.toBeNull());

    await user.type(within(facts).getByLabelText("Reason"), "sign slip on COGS");
    await user.click(within(facts).getByRole("button", { name: "Approve fix" }));

    const download = await screen.findByRole("link", { name: "Download corrected model" });
    expect(download).toHaveAttribute("href", `http://localhost:8000/investigations/${APPROVED.id}/corrected`);
    fireEvent.click(download);
    expect(screen.queryByRole("link", { name: "Download corrected model" })).toBeNull();
    expect(within(facts).getByText(/the copy is no longer on the server/)).toBeInTheDocument();
    expect(lastResume(api)).toMatchObject({
      url: `http://localhost:8000/investigations/${REVIEW.id}/resume/stream`,
      body: { action: "approve", reason: "sign slip on COGS", state: { id: REVIEW.id, status: "needs_review" } },
    });
  });

  test("goes straight to the review, then remembers a rejection marked intentional", async () => {
    const api = fakeApi(
      [...steps("load_sheet", "map_model", "locate", "trace", "diagnose", "test", "verify", "explain"), ["view", REVIEW]],
      [[...steps("human_review"), ["view", REJECTED]]],
    );
    vi.stubGlobal("fetch", api.fetch);
    const user = await checkDemo();
    expect(api.sent.find((request) => request.url.endsWith("/investigations/stream"))?.body).toEqual({ spreadsheet_id: "demo", question: "" });
    expect(screen.queryByRole("group", { name: "Which cell do you mean?" })).not.toBeInTheDocument();

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

  test("a check with no proven fix says there is nothing to approve and shows no decision menu", async () => {
    const unproven: InvestigationView = {
      ...REVIEW,
      patch: null,
      report: "No error found. Total operating expenses (P&L!G9) is 60.16: the total sums G7:G8 and leaves out G6 in the same block, which gives 60.9 (ev-1).",
    };
    const api = fakeApi([...steps(...STEPS.map(([name]) => name)), ["view", unproven]]);
    vi.stubGlobal("fetch", api.fetch);

    await checkDemo();

    const facts = await screen.findByRole("region", { name: "Investigation facts" });
    expect(screen.getByText("No fix to approve")).toBeInTheDocument();
    expect(within(facts).getByText("The model checks out — nothing to change")).toBeInTheDocument();
    expect(within(facts).getByText(/No cell broke the pattern of its own row, so there is no fix to approve/)).toBeInTheDocument();
    expect(within(facts).getByRole("region", { name: "Report" })).toHaveTextContent(/No error found/);
    expect(within(facts).queryByLabelText("Deterministic checks")).not.toBeInTheDocument();
    expect(within(facts).queryByRole("button", { name: "Approve fix" })).not.toBeInTheDocument();
    expect(within(facts).queryByRole("button", { name: "Reject" })).not.toBeInTheDocument();
    expect(within(facts).queryByRole("button", { name: "Edit fix" })).not.toBeInTheDocument();
    expect(within(facts).queryByPlaceholderText("Reason (optional)")).not.toBeInTheDocument();
    expect(within(facts).queryByLabelText("Never flag again")).not.toBeInTheDocument();
    const rail = screen.getByRole("region", { name: "Investigation steps" });
    expect(within(rail).getByText("Looked for the root cause")).toBeInTheDocument();
    expect(within(rail).queryByText("Found the root cause")).not.toBeInTheDocument();
  });

  test("keeps the page on screen when the service sends no check labels", async () => {
    const withoutLabels: Record<string, unknown> = { ...REVIEW };
    delete withoutLabels.check_labels;
    const api = fakeApi([...steps(...STEPS.map(([name]) => name)), ["view", withoutLabels as never]]);
    vi.stubGlobal("fetch", api.fetch);
    const user = await checkDemo();

    const facts = await screen.findByRole("region", { name: "Investigation facts" });
    expect(within(facts).getByRole("button", { name: "Approve fix" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Investigation steps" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Sheet" })).toBeInTheDocument();
    const rail = screen.getByRole("region", { name: "Investigation steps" });
    expect(within(rail).getByText(/3 of 3 checks passed/)).toBeInTheDocument();
    expect(within(facts).getByRole("region", { name: "Report" })).toBeInTheDocument();
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
    const cause = (REVIEW.hypotheses ?? []).find((item) => item.status === "confirmed") ?? (REVIEW.hypotheses ?? [])[0];
    expect(within(rows[4]).getByText(`${cause.cell} — ${cause.claim}`)).toBeInTheDocument();
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
    const confirmed = (REVIEW.hypotheses ?? []).find((item) => item.status === "confirmed") ?? (REVIEW.hypotheses ?? [])[0];
    expect(culprit?.textContent).toContain(confirmed.error_type.replaceAll("_", " "));
    expect(culprit).toHaveAttribute("title", confirmed.claim);

    const revenue = document.querySelector("[data-wire-label='P&L!G4->P&L!G6']");
    expect(revenue).toHaveAttribute("data-tone", "ok");
    expect(revenue?.textContent).toContain("Revenue +11.5");
    expect(revenue?.textContent).toContain("6% of the move");
  });

  test("shows which cell the locator chose, and among how many, when the question was ambiguous", async () => {
    const ambiguous: InvestigationView = {
      ...REVIEW,
      target_choice: { candidates: ["P&L!G6", "Summary!G6", "P&L!F6"], chosen: "P&L!G6", why: "Gross profit 2025A moves most and sits downstream of the broken row." },
    };
    const api = fakeApi([...steps(...STEPS.map(([name]) => name)), ["view", ambiguous]]);
    vi.stubGlobal("fetch", api.fetch);
    const user = await checkDemo();

    const facts = await screen.findByRole("region", { name: "Investigation facts" });
    expect(await within(facts).findByText(/Chosen among 3 candidates/)).toBeInTheDocument();
    expect(within(facts).getByText("P&L!G6, Summary!G6, P&L!F6")).toBeInTheDocument();
    await user.click(within(facts).getByRole("button", { name: "why?" }));
    expect(within(facts).getByText(/moves most and sits downstream of the broken row/)).toBeInTheDocument();
  });

  test("states the chosen cell without ceremony when the code found only one", async () => {
    const one: InvestigationView = {
      ...REVIEW,
      target_choice: { candidates: [], chosen: "P&L!G6", why: "The only period cell off its row pattern." },
    };
    const api = fakeApi([...steps(...STEPS.map(([name]) => name)), ["view", one]]);
    vi.stubGlobal("fetch", api.fetch);
    await checkDemo();

    const facts = await screen.findByRole("region", { name: "Investigation facts" });
    expect(await within(facts).findByText(/^Chosen:/)).toBeInTheDocument();
    expect(within(facts).queryByText(/Chosen among/)).toBeNull();
  });

  test("reads a margin question as percentages and drops shares of a ratio's change", async () => {
    const margin: InvestigationView = {
      ...REVIEW,
      target: { sheet: "P&L", cell: "G11", label: "EBITDA margin", period: "2025A", value: 1.2, prior_cell: "F11", prior_value: 1.05 },
      causal_tree: {
        cell: "P&L!G11",
        label: "EBITDA margin",
        value_before: 1.05,
        value_after: 1.2,
        delta: 0.15,
        share_of_change: 1,
        suspicious: false,
        children: [
          { cell: "P&L!G10", label: "EBITDA", value_before: 28.24, value_after: 225.6, delta: 197.36, share_of_change: 13.16, suspicious: false, children: [] },
          { cell: "P&L!G4", label: "Revenue", value_before: 176.5, value_after: 188, delta: 11.5, share_of_change: -12.16, suspicious: false, children: [] },
        ],
      },
      hypotheses: [],
      patch: null,
      report: "EBITDA margin rose because COGS flipped sign.",
    };
    const api = fakeApi([...steps(...STEPS.map(([name]) => name)), ["view", margin]]);
    vi.stubGlobal("fetch", api.fetch);
    await checkDemo();

    const facts = await screen.findByRole("region", { name: "Investigation facts" });
    expect(await within(facts).findByText(/105\.0% → 120\.0%/)).toBeInTheDocument();
    await waitFor(() => expect(document.querySelectorAll("[data-wire-label]").length).toBeGreaterThan(0));
    const chips = Array.from(document.querySelectorAll("[data-wire-label]")).map((chip) => chip.textContent ?? "");
    expect(chips.some((text) => text.includes("% of the move"))).toBe(false);
    expect(chips.some((text) => text.includes("1316%"))).toBe(false);
  });

  test("keeps the page usable when a view arrives without the optional label table", async () => {
    const withoutLabels: InvestigationView = { ...REVIEW, check_labels: undefined, target_choice: null };
    const api = fakeApi([...steps(...STEPS.map(([name]) => name)), ["view", withoutLabels]]);
    vi.stubGlobal("fetch", api.fetch);
    await checkDemo();

    const facts = await screen.findByRole("region", { name: "Investigation facts" });
    expect(within(facts).getByText(/84\.7 → 285\.8/)).toBeInTheDocument();
    expect(within(facts).getByRole("region", { name: "Report" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Investigation steps" })).toBeInTheDocument();
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

import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";

import App from "../App";
import type { StoredRun } from "../storage";
import { STORAGE_BYTES, STORAGE_KEY, currentRun, listRuns, saveRun } from "../storage";
import { APPROVED, REVIEW, RUNNING, SHEET, STEPS, fakeApi, steps } from "./fakeApi";

function heavyRun(id: string, updatedAt: number, factor = 20): StoredRun {
  const columns = ["F", "G", "H"].map((letter, index) => ({ letter, header: `${2024 + index}A` }));
  const rows = Array.from({ length: 200 }, (_, offset) => ({
    row: offset + 5,
    label: `Operating line ${offset + 5} with a realistic label`,
    cells: columns.map((column) => ({
      ref: `${column.letter}${offset + 5}`,
      value: 1000 + offset,
      formula: `=${column.letter}${offset + 4}*Assumptions!$C$${offset + 5}`.repeat(factor),
    })),
  }));
  return {
    id,
    spreadsheetId: "demo",
    name: "Demo model",
    question: "",
    startedAt: updatedAt,
    updatedAt,
    steps: [],
    view: { ...REVIEW, id },
    sheet: { sheet: "P&L", header_row: 4, columns, rows },
  };
}

afterEach(() => {
  window.history.replaceState(null, "", "/");
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

async function startDemo() {
  const user = userEvent.setup();
  const view = render(<App />);
  await user.click(await screen.findByRole("button", { name: "See it in action" }));
  return { user, unmount: view.unmount };
}

function sentTo(api: ReturnType<typeof fakeApi>, path: string) {
  return api.sent.filter((request) => request.url.includes(path)).at(-1);
}

function offline() {
  vi.stubGlobal("fetch", async () => {
    throw new Error("the service is unreachable");
  });
}

describe("a run kept in the browser", () => {
  test("a paused check comes back after a reload, and the decision it waits for can still be made", async () => {
    const api = fakeApi(
      [...steps(...STEPS.map(([name]) => name)), ["view", REVIEW]],
      [[...steps("human_review", "apply_fix"), ["view", APPROVED]]],
    );
    vi.stubGlobal("fetch", api.fetch);
    const { user, unmount } = await startDemo();
    await screen.findByRole("region", { name: "Investigation facts" });
    expect(listRuns()).toHaveLength(1);
    unmount();

    render(<App />);
    const facts = await screen.findByRole("region", { name: "Investigation facts" });
    await user.click(within(facts).getByRole("button", { name: "Why?" }));
    const report = within(facts).getByRole("region", { name: "Report" });
    expect(within(report).getByText(/Gross profit 2025A moved from 84\.72 to 285\.76/)).toBeInTheDocument();
    const rail = screen.getByRole("region", { name: "Investigation steps" });
    expect(within(rail).getAllByRole("listitem")).toHaveLength(8);
    expect(within(rail).getByText("Found the root cause")).toBeInTheDocument();

    await user.type(within(facts).getByLabelText("Reason"), "typed opex");
    await user.click(within(facts).getByRole("button", { name: "Approve fix" }));

    expect(await screen.findByRole("link", { name: "Download corrected model" })).toBeInTheDocument();
    expect(sentTo(api, "/resume/stream")).toMatchObject({
      url: `http://localhost:8000/investigations/${REVIEW.id}/resume/stream`,
      body: { action: "approve", reason: "typed opex", state: { id: REVIEW.id, status: "needs_review" } },
    });
  });

  test("the finished check, its sheet and its corrected file come back even when the service is gone", async () => {
    const api = fakeApi([...steps("explain"), ["view", REVIEW]], [[...steps("human_review", "apply_fix"), ["view", APPROVED]]]);
    vi.stubGlobal("fetch", api.fetch);
    const { user, unmount } = await startDemo();
    const facts = await screen.findByRole("region", { name: "Investigation facts" });
    await user.click(within(facts).getByRole("button", { name: "Approve fix" }));
    await screen.findByRole("link", { name: "Download corrected model" });
    unmount();

    vi.unstubAllGlobals();
    offline();
    render(<App />);

    const restored = await screen.findByRole("region", { name: "Investigation facts" });
    await user.click(within(restored).getByRole("button", { name: "Why?" }));
    expect(within(restored).getByRole("region", { name: "Report" })).toHaveTextContent(/Gross profit 2025A moved from 84\.72 to 285\.76/);
    expect(within(restored).getByRole("link", { name: "Download corrected model" })).toHaveAttribute(
      "href",
      `http://localhost:8000/investigations/${APPROVED.id}/corrected`,
    );
    const grid = await screen.findByRole("region", { name: "Sheet" });
    expect(within(grid).getByRole("button", { name: "P&L!G5, confirmed" })).toBeInTheDocument();
  });

  test("a corrupt or foreign value is ignored: the home page shows and a new check runs", async () => {
    const api = fakeApi([...steps("explain"), ["view", REVIEW]]);
    vi.stubGlobal("fetch", api.fetch);
    window.localStorage.setItem(STORAGE_KEY, '{"version":1,"current":"gone","runs":[');
    const broken = render(<App />);
    expect(await screen.findByRole("heading", { level: 1 })).toHaveTextContent("Every formula, checked. Under the X-Ray.");
    broken.unmount();

    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ version: 1, current: "run-1", runs: [{ id: 7, steps: "no" }, { id: "run-1", spreadsheetId: "demo", steps: [] }] }),
    );
    const drifted = render(<App />);
    expect(await screen.findByRole("button", { name: "See it in action" })).toBeInTheDocument();
    drifted.unmount();

    window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ version: 99, current: null, runs: [{ id: "run-1", spreadsheetId: "demo", steps: [] }] }));
    const future = render(<App />);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "See it in action" }));
    expect(await screen.findByRole("region", { name: "Investigation facts" })).toBeInTheDocument();
    future.unmount();
  });

  test("storage that refuses writes does not break the check", async () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("QuotaExceededError");
    });
    const api = fakeApi([...steps("explain"), ["view", REVIEW]]);
    vi.stubGlobal("fetch", api.fetch);

    await startDemo();

    expect(await screen.findByRole("region", { name: "Investigation facts" })).toBeInTheDocument();
    expect(listRuns()).toEqual([]);
  });

  test("drops the oldest checks by size, not only by count, and keeps the newest one", () => {
    const runs = Array.from({ length: 12 }, (_, index) => heavyRun(`old-${index}`, index));
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ version: 1, current: "old-11", runs }));

    saveRun(heavyRun("newest", 99));

    const kept = listRuns();
    const stored = window.localStorage.getItem(STORAGE_KEY) ?? "";
    expect(stored.length).toBeLessThanOrEqual(STORAGE_BYTES);
    expect(kept[0].id).toBe("newest");
    expect(kept.map((run) => run.id)).not.toContain("old-0");
    expect(kept.map((run) => run.id)).toContain("old-11");
  });

  test("a check bigger than the whole budget keeps its facts and drops its sheet", () => {
    saveRun(heavyRun("huge", 1, 200));

    const stored = currentRun();
    expect(stored?.id).toBe("huge");
    expect(stored?.view?.id).toBe("huge");
    expect(stored?.sheet).toBeNull();
    expect((window.localStorage.getItem(STORAGE_KEY) ?? "").length).toBeLessThanOrEqual(STORAGE_BYTES);
  });

  test("a check interrupted by a reload says so, instead of asking for a decision nobody can make, and can be run again", async () => {
    const run = {
      id: RUNNING.id,
      spreadsheetId: "demo",
      name: "Demo model",
      question: "",
      startedAt: 1,
      updatedAt: 1,
      steps: STEPS.slice(0, 5).map(([step, label]) => ({ step, label })),
      view: RUNNING,
      sheet: SHEET,
    };
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ version: 1, current: RUNNING.id, runs: [run] }));
    const api = fakeApi([...steps("explain"), ["view", REVIEW]]);
    vi.stubGlobal("fetch", api.fetch);
    const user = userEvent.setup();

    render(<App />);

    expect(await screen.findByText("Interrupted")).toBeInTheDocument();
    expect(screen.queryByText("Review needed")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Approve fix" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Run again" }));

    await screen.findByRole("region", { name: "Investigation facts" });
    expect(sentTo(api, "/investigations/stream")).toMatchObject({ body: { spreadsheet_id: "demo", question: "" } });
    expect(currentRun()?.view?.id).toBe(REVIEW.id);
  });

  test("a check stored without its sheet still restores its facts and its report", async () => {
    const run = { id: REVIEW.id, spreadsheetId: "demo", name: "Demo model", question: "", startedAt: 1, updatedAt: 1, steps: [], view: REVIEW, sheet: null };
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ version: 1, current: REVIEW.id, runs: [run] }));
    vi.stubGlobal("fetch", async () => {
      throw new Error("the service is unreachable");
    });

    render(<App />);

    const facts = await screen.findByRole("region", { name: "Investigation facts" });
    const user = userEvent.setup();
    await user.click(within(facts).getByRole("button", { name: "Why?" }));
    expect(within(facts).getByRole("region", { name: "Report" })).toHaveTextContent(/Gross profit 2025A moved from 84\.72 to 285\.76/);
  });

  test("the browser keeps the newest 25 checks", async () => {
    const history = Array.from({ length: 30 }, (_, index) => ({
      id: `old-${index}`,
      spreadsheetId: "demo",
      name: "Demo model",
      question: "",
      startedAt: index,
      updatedAt: index,
      steps: [],
      view: null,
      sheet: null,
    }));
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ version: 1, current: "old-29", runs: history }));
    const api = fakeApi([...steps("explain"), ["view", REVIEW]]);
    vi.stubGlobal("fetch", api.fetch);

    await startDemo();
    await screen.findByRole("region", { name: "Investigation facts" });

    await waitFor(() => expect(listRuns()).toHaveLength(25));
    const runs = listRuns();
    expect(runs[0].view?.id).toBe(REVIEW.id);
    expect(runs.map((run) => run.id)).not.toContain("old-0");
    expect(runs.map((run) => run.id)).toContain("old-29");
  });
});

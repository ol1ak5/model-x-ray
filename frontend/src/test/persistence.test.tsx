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
  await user.click((await screen.findAllByRole("button", { name: "Try the demo →" }))[0]);
  return { user, unmount: view.unmount };
}

async function errorRow(user: ReturnType<typeof userEvent.setup>) {
  const errors = await screen.findByRole("region", { name: "Errors detected" });
  await user.click(await within(errors).findByRole("button", { name: /has the wrong sign/ }));
  return errors;
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
    const { unmount } = await startDemo();
    await screen.findByText("Errors detected: 1");
    expect(listRuns()).toHaveLength(1);
    unmount();

    render(<App />);
    expect(await screen.findByRole("heading", { level: 1 })).toHaveTextContent("Demo model.xlsx");
    expect(screen.getByText("1 error detected")).toBeInTheDocument();
    const user = userEvent.setup();
    const errors = await errorRow(user);
    expect(within(errors).getByText(/Gross profit 2025A moved from 84\.72 to 285\.76/)).toBeInTheDocument();

    await user.click(within(errors).getByRole("button", { name: "Approve fix" }));

    expect(await within(errors).findByText("✓ Fix accepted")).toBeInTheDocument();
    expect(sentTo(api, "/resume/stream")).toMatchObject({
      url: `http://localhost:8000/investigations/${REVIEW.id}/resume/stream`,
      body: { action: "approve", state: { id: REVIEW.id, status: "needs_review" } },
    });
  });

  test("the finished check and its decision come back even when the service is gone", async () => {
    const api = fakeApi([...steps("explain"), ["view", REVIEW]], [[...steps("human_review", "apply_fix"), ["view", APPROVED]]]);
    vi.stubGlobal("fetch", api.fetch);
    const { user, unmount } = await startDemo();
    const errors = await errorRow(user);
    await user.click(within(errors).getByRole("button", { name: "Approve fix" }));
    await within(errors).findByText("✓ Fix accepted");
    unmount();

    vi.unstubAllGlobals();
    offline();
    render(<App />);

    expect(await screen.findByText("Review complete", { selector: ".state" })).toBeInTheDocument();
    const restored = await errorRow(userEvent.setup());
    expect(within(restored).getByText("Fixed")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Download Demo model (corrected).xlsx" })).toHaveAttribute("href", `http://localhost:8000/investigations/${APPROVED.id}/corrected`);
  });

  test("a corrupt or foreign value is ignored: the home page shows and a new check runs", async () => {
    const api = fakeApi([...steps("explain"), ["view", REVIEW]]);
    vi.stubGlobal("fetch", api.fetch);
    window.localStorage.setItem(STORAGE_KEY, '{"version":1,"current":"gone","runs":[');
    const broken = render(<App />);
    expect(await screen.findByRole("heading", { level: 1 })).toHaveTextContent("Your AI agent for financial model analysis.");
    broken.unmount();

    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ version: 1, current: "run-1", runs: [{ id: 7, steps: "no" }, { id: "run-1", spreadsheetId: "demo", steps: [] }] }),
    );
    const drifted = render(<App />);
    expect(await screen.findByRole("heading", { level: 1 })).toBeInTheDocument();
    drifted.unmount();

    window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ version: 99, current: null, runs: [{ id: "run-1", spreadsheetId: "demo", steps: [] }] }));
    const future = render(<App />);
    const user = userEvent.setup();
    await user.click((await screen.findAllByRole("button", { name: "Try the demo →" }))[0]);
    expect(await screen.findByText("Errors detected: 1")).toBeInTheDocument();
    future.unmount();
  });

  test("storage that refuses writes does not break the check", async () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("QuotaExceededError");
    });
    const api = fakeApi([...steps("explain"), ["view", REVIEW]]);
    vi.stubGlobal("fetch", api.fetch);

    await startDemo();

    expect(await screen.findByText("Errors detected: 1")).toBeInTheDocument();
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
      name: "Demo model.xlsx",
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
    expect(screen.queryByRole("button", { name: "Approve fix" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Run again" }));

    expect(await screen.findByText("Errors detected: 1")).toBeInTheDocument();
    expect(sentTo(api, "/investigations/stream")).toMatchObject({ body: { spreadsheet_id: "demo", question: "" } });
    await waitFor(() => expect(currentRun()?.view?.id).toBe(REVIEW.id));
  });

  test("a check stored without its sheet still restores its error and its explanation", async () => {
    const run = { id: REVIEW.id, spreadsheetId: "demo", name: "Demo model.xlsx", question: "", startedAt: 1, updatedAt: 1, steps: [], view: REVIEW, sheet: null };
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ version: 1, current: REVIEW.id, runs: [run] }));
    offline();

    render(<App />);

    const errors = await errorRow(userEvent.setup());
    expect(within(errors).getByText("P&L!G5 has the wrong sign")).toBeInTheDocument();
    expect(within(errors).getByText(/Gross profit 2025A moved from 84\.72 to 285\.76/)).toBeInTheDocument();
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
    await screen.findByText("Errors detected: 1");

    await waitFor(() => expect(listRuns()).toHaveLength(25));
    const runs = listRuns();
    expect(runs[0].view?.id).toBe(REVIEW.id);
    expect(runs.map((run) => run.id)).not.toContain("old-0");
    expect(runs.map((run) => run.id)).toContain("old-29");
  });
});

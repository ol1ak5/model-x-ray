import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";

import App from "../App";
import { STORAGE_KEY, listRuns } from "../storage";
import { APPROVED, REVIEW, STEPS, fakeApi, steps } from "./fakeApi";

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
    expect(sentTo(api, "/resume/stream")).toEqual({
      url: `http://localhost:8000/investigations/${REVIEW.id}/resume/stream`,
      body: { action: "approve", reason: "typed opex" },
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

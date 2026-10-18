import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";

import App from "../App";
import { STORAGE_KEY, listRuns } from "../storage";
import { APPROVED, REVIEW, STEPS, fakeApi, steps } from "./fakeApi";

afterEach(() => {
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
    await screen.findByRole("button", { name: "Approve fix" });
    expect(listRuns()).toHaveLength(1);
    unmount();

    render(<App />);
    await screen.findByRole("button", { name: "Approve fix" });
    expect(screen.getByRole("region", { name: "Report" })).toHaveTextContent("Root cause found in P&L!H7");
    expect(screen.getByRole("list", { name: "Progress" })).toHaveTextContent("Writing the explanation");

    await user.type(screen.getByLabelText("Reason"), "typed opex");
    await user.click(screen.getByRole("button", { name: "Approve fix" }));

    expect(await screen.findByRole("link", { name: "Download corrected model" })).toBeInTheDocument();
    expect(sentTo(api, "/resume/stream")).toEqual({ url: "http://localhost:8000/investigations/inv-1/resume/stream", body: { action: "approve", reason: "typed opex" } });
  });

  test("the finished check, its sheet and its corrected file come back even when the service is gone", async () => {
    const api = fakeApi([...steps("explain"), ["view", REVIEW]], [[...steps("human_review", "apply_fix"), ["view", APPROVED]]]);
    vi.stubGlobal("fetch", api.fetch);
    const { user, unmount } = await startDemo();
    await user.click(await screen.findByRole("button", { name: "Approve fix" }));
    await screen.findByRole("link", { name: "Download corrected model" });
    unmount();

    vi.unstubAllGlobals();
    offline();
    render(<App />);

    expect(await screen.findByRole("region", { name: "Report" })).toHaveTextContent("Root cause found in P&L!H7");
    expect(screen.getByRole("link", { name: "Download corrected model" })).toHaveAttribute("href", "http://localhost:8000/investigations/inv-1/corrected");
    const grid = await screen.findByRole("region", { name: "Sheet" });
    expect(within(grid).getByRole("button", { name: "P&L!H7, confirmed" })).toHaveTextContent("(45.2)(52.5)");
  });

  test("a corrupt or foreign value is ignored: the home page shows and a new check runs", async () => {
    const api = fakeApi([...steps("explain"), ["view", REVIEW]]);
    vi.stubGlobal("fetch", api.fetch);
    window.localStorage.setItem(STORAGE_KEY, '{"version":1,"current":"gone","runs":[');
    const broken = render(<App />);
    expect(await screen.findByRole("heading", { level: 1 })).toHaveTextContent("Your Excel models under the X-Ray.");
    broken.unmount();

    window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ version: 1, current: "run-1", runs: [{ id: 7, steps: "no" }, { id: "run-1", spreadsheetId: "demo", steps: [] }] }));
    const drifted = render(<App />);
    expect(await screen.findByRole("button", { name: "See it in action" })).toBeInTheDocument();
    drifted.unmount();

    window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ version: 99, current: null, runs: [{ id: "run-1", spreadsheetId: "demo", steps: [] }] }));
    const future = render(<App />);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "See it in action" }));
    expect(await screen.findByRole("button", { name: "Approve fix" })).toBeInTheDocument();
    future.unmount();
  });

  test("storage that refuses writes does not break the check", async () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("QuotaExceededError");
    });
    const api = fakeApi([...steps("explain"), ["view", REVIEW]]);
    vi.stubGlobal("fetch", api.fetch);

    await startDemo();

    expect(await screen.findByRole("button", { name: "Approve fix" })).toBeInTheDocument();
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
    await screen.findByRole("button", { name: "Approve fix" });

    const runs = listRuns();
    expect(runs).toHaveLength(25);
    expect(runs[0].view?.id).toBe("inv-1");
    expect(runs.map((run) => run.id)).not.toContain("old-0");
    expect(runs.map((run) => run.id)).toContain("old-29");
  });
});

import type { InvestigationView } from "./api";

export type PhaseState = "todo" | "now" | "done" | "wait";

export type Phase = { name: string; hint: string; state: PhaseState };

export const PHASES: [string, string][] = [
  ["Read", "Opens the workbook and labels every line"],
  ["Investigate", "Finds the suspects and their cause"],
  ["Prove", "Tests each fix in a copy"],
  ["Approve", "You approve, edit or reject each fix"],
  ["Review complete", "Every finding settled"],
];

const FINISHES: string[][] = [["map_model", "locate"], ["diagnose", "test"], ["explain"]];

export function phasesOf(steps: { step: string }[], views: (InvestigationView | null)[], running: boolean): Phase[] {
  const seen = new Set(steps.map((entry) => entry.step));
  const settled = views.length > 0 && views.every((view) => view !== null && view.status !== "running");
  const waiting = views.some((view) => view?.status === "needs_review" && view.patch);
  const finished = settled && !waiting;
  const done = [
    settled || FINISHES[0].some((step) => seen.has(step)),
    settled || FINISHES[1].some((step) => seen.has(step)),
    settled || FINISHES[2].some((step) => seen.has(step)),
    finished,
    finished,
  ];
  const states: PhaseState[] = done.map((value) => (value ? "done" : "todo"));
  if (running) {
    const now = settled ? 3 : done.findIndex((value) => !value);
    if (now >= 0) states[now] = "now";
  } else if (waiting) {
    states[3] = "wait";
  }
  return PHASES.map(([name, hint], index) => ({ name, hint, state: states[index] }));
}

export function statusOf(views: (InvestigationView | null)[], running: boolean, lastStep: string | null): { label: string; tone: "run" | "wait" | "done"; line: string } {
  if (running) return { label: "Checking the model", tone: "run", line: lastStep ?? "Reading the model" };
  const stopped = { label: "Interrupted", tone: "wait" as const, line: "The check stopped before it finished" };
  if (views.length === 0 || views.some((view) => view === null || view.status === "running")) return stopped;
  const settled = views as InvestigationView[];
  const waiting = settled.filter((view) => view.status === "needs_review" && view.patch).length;
  if (waiting) return { label: `${waiting} ${waiting === 1 ? "error" : "errors"} detected`, tone: "wait", line: "Waiting for your decision" };
  const decided = settled.filter((view) => view.status === "done");
  const fixed = decided.filter((view) => view.corrected_copy_id).length;
  if (decided.length) return { label: "Review complete", tone: "done", line: fixed ? `${fixed} ${fixed === 1 ? "fix" : "fixes"} saved to a new copy` : "No changes to your file" };
  return { label: "No errors found", tone: "done", line: "Nothing to change in your file" };
}

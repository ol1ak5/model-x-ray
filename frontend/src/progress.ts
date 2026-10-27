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

export function phasesOf(steps: { step: string }[], view: InvestigationView | null, running: boolean): Phase[] {
  const seen = new Set(steps.map((entry) => entry.step));
  const settled = view !== null && view.status !== "running";
  const noFix = settled && view.status === "needs_review" && !view.patch;
  const finished = view?.status === "done" || noFix;
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
  } else if (view?.status === "needs_review" && view.patch) {
    states[3] = "wait";
  }
  return PHASES.map(([name, hint], index) => ({ name, hint, state: states[index] }));
}

export function statusOf(view: InvestigationView | null, running: boolean, lastStep: string | null, earlier: { status: string }[] = []): { label: string; tone: "run" | "wait" | "done"; line: string } {
  if (running) return { label: "Checking the model", tone: "run", line: lastStep ?? (earlier.length ? "Looking for the next error" : "Reading the model") };
  const finished = view?.status === "done" || (view?.status === "needs_review" && !view.patch);
  if (finished && earlier.length) {
    const fixed = earlier.filter((finding) => finding.status === "fixed").length;
    return { label: "Review complete", tone: "done", line: fixed ? `${fixed} ${fixed === 1 ? "fix" : "fixes"} saved to a new copy` : "No changes to your file" };
  }
  if (!view) return { label: "Interrupted", tone: "wait", line: "The check stopped before it finished" };
  if (view.status === "done") return { label: "Review complete", tone: "done", line: view.corrected_copy_id ? "1 fix saved to a new copy" : "No changes to your file" };
  if (view.status === "needs_review" && view.patch) return { label: "1 error detected", tone: "wait", line: "Waiting for your decision" };
  if (view.status === "needs_review") return { label: "No errors found", tone: "done", line: "Nothing to change in your file" };
  return { label: "Interrupted", tone: "wait", line: "The check stopped before it finished" };
}

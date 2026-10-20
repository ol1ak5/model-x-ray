import type { InvestigationView } from "./api";
import { money } from "./format";

export type Tone = "done" | "active" | "pending";
export type RailStep = { key: string; title: string; detail: string | null; tone: Tone };
export type Step = { step: string; label: string };

const PIPELINE: { key: string; title: string; hint: string }[] = [
  { key: "load_sheet", title: "Opened the model", hint: "Every sheet and cell, read in a copy" },
  { key: "map_model", title: "Read the layout", hint: "Which rows are periods, what each line is" },
  { key: "locate", title: "Found the cell", hint: "The number behind your question" },
  { key: "trace", title: "Traced the inputs", hint: "What moved, and by how much" },
  { key: "diagnose", title: "Found the root cause", hint: "Following the formulas into the detail" },
  { key: "test", title: "Tested the fix in a copy", hint: "Your own file is never touched" },
  { key: "verify", title: "Checked the fix", hint: "Independent checks on the result" },
  { key: "explain", title: "Wrote the explanation", hint: "A report quoting its evidence" },
];

function finding(key: string, view: InvestigationView | null): string | null {
  if (!view) return null;

  if (key === "locate") {
    const target = view.target;
    if (!target) return null;
    return `${target.label} ${target.period} · ${money(target.prior_value)} → ${money(target.value)}`;
  }

  if (key === "trace") {
    const parts = (view.contributions ?? []).slice(0, 3).map((item) => `${item.label} ${item.delta >= 0 ? "+" : "-"}${money(Math.abs(item.delta))}`);
    return parts.length > 0 ? parts.join(" · ") : null;
  }

  if (key === "diagnose") {
    const hypotheses = view.hypotheses ?? [];
    const cause = hypotheses.find((item) => item.status === "confirmed") ?? hypotheses[0];
    return cause ? `${cause.cell} — ${cause.claim}` : null;
  }

  if (key === "test") {
    return view.patch ? `${view.patch.cell} ${view.patch.old_formula} → ${view.patch.new_formula}` : null;
  }

  if (key === "verify") {
    const verification = view.verifications?.at(-1);
    if (!verification?.checks) return null;
    const total = Object.keys(view.check_labels ?? {}).length || Object.keys(verification.checks).length;
    const passed = Object.values(verification.checks).filter(Boolean).length;
    const verdict = verification.verdict === "confirmed" ? "proof passed" : verification.verdict === "rejected" ? "fix rejected" : "could not prove it";
    return `${passed} of ${total} checks passed · ${verdict}`;
  }

  if (key === "explain") {
    if (!view.report) return null;
    return `Report ready · ${(view.evidence ?? []).length} evidence links`;
  }

  return null;
}

export function railOf(view: InvestigationView | null, steps: Step[], running: boolean): RailStep[] {
  const arrived = new Map(steps.map((item) => [item.step, item.label]));
  const settled = view !== null && !running;
  const proven = (key: string) => view !== null && finding(key, view) !== null;
  const next = PIPELINE.find((entry) => !arrived.has(entry.key) && !proven(entry.key) && !settled)?.key ?? null;

  const rows: RailStep[] = PIPELINE.map((entry) => {
    if (settled || arrived.has(entry.key) || proven(entry.key)) {
      return { key: entry.key, title: entry.title, detail: finding(entry.key, view) ?? arrived.get(entry.key) ?? entry.hint, tone: "done" };
    }
    return { key: entry.key, title: entry.title, detail: entry.hint, tone: entry.key === next ? "active" : "pending" };
  });

  const extra: RailStep[] = steps
    .filter((item) => !PIPELINE.some((entry) => entry.key === item.step))
    .map((item) => ({ key: item.step, title: item.label, detail: null, tone: "done" }));

  const closed: RailStep[] =
    view?.status === "done"
      ? [
          view.corrected_copy_id
            ? { key: "apply_fix", title: "Saved the corrected copy", detail: "Download it from the bar below", tone: "done" }
            : { key: "closed", title: "Closed without a change", detail: "Your decision is saved", tone: "done" },
        ]
      : [];

  return [...rows, ...extra.filter((item) => !closed.some((entry) => entry.key === item.key)), ...closed];
}

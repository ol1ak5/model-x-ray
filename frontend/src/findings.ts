import type { InvestigationView, SheetWindow } from "./api";

export type FindingStatus = "detected" | "fixed" | "dismissed";

export type Finding = {
  cell: string;
  sheet: string;
  address: string;
  title: string;
  type: string;
  before: string;
  after: string;
  explanation: string[];
  status: FindingStatus;
  dependents: string[];
};

const TYPES: Record<string, [string, string]> = {
  typed_value: ["Typed value", "is a typed number"],
  wrong_reference: ["Wrong reference", "points to the wrong cell"],
  range_inconsistency: ["Incomplete range", "adds up the wrong range"],
  sign_inconsistency: ["Flipped sign", "has the wrong sign"],
  period_inconsistency: ["Wrong period", "uses the wrong period"],
  logic_error: ["Logic error", "breaks the logic of its line"],
  input_outlier: ["Unusual input", "is out of line with the rest"],
};

const CITATION = /\s*\((?:evidence:\s*)?ev-\d+(?:,\s*ev-\d+)*\)/g;

export function splitRef(ref: string): [string, string] {
  const bang = ref.lastIndexOf("!");
  const sheet = ref.slice(0, bang).replace(/^'(.*)'$/, "$1");
  return [sheet, ref.slice(bang + 1).replace(/\$/g, "")];
}

function lineOf(cell: string, sheet: SheetWindow | null): string | null {
  if (!sheet) return null;
  const row = sheet.rows.find((candidate) => candidate.cells.some((entry) => entry.ref === cell));
  if (!row) return null;
  const letter = splitRef(cell)[1].replace(/\d+$/, "");
  const period = sheet.columns.find((column) => column.letter === letter)?.header;
  return [row.label, period].filter(Boolean).join(" ") || null;
}

export function explanationOf(report: string | null): string[] {
  if (!report) return [];
  return report
    .replace(CITATION, "")
    .replace(/`([^`]*)`/g, "$1")
    .replace(/(\S+)\s*(?:->|→|=>)\s*/g, (_, left: string) => (/^-?[\d.,]+$/.test(left) ? `from ${left} to ` : `${left} to `))
    .replace(/\s*[—–]\s*/g, ", ")
    .replace(/;\s+(\w)/g, (_, first: string) => `. ${first.toUpperCase()}`)
    .replace(/\.{2,}(?=\s|$)/g, ".")
    .split(/\n\s*\n/)
    .map((paragraph) => paragraph.trim())
    .filter(Boolean);
}

function dependentsOf(view: InvestigationView, cell: string): string[] {
  const last = view.verifications?.at(-1);
  if (!last) return [];
  return Object.keys(last.after).filter((ref) => ref !== cell && last.after[ref] !== last.before[ref]);
}

export function findingsOf(view: InvestigationView | null, sheet: SheetWindow | null): Finding[] {
  if (!view || view.status === "running" || !view.patch) return [];
  const patch = view.patch;
  const hypothesis = (view.hypotheses ?? []).find((candidate) => candidate.cell === patch.cell && candidate.status === "confirmed") ?? (view.hypotheses ?? []).find((candidate) => candidate.cell === patch.cell);
  const [typeLabel, phrase] = TYPES[hypothesis?.error_type ?? ""] ?? ["Error", "looks wrong"];
  const [sheetName, address] = splitRef(patch.cell);
  const line = lineOf(patch.cell, sheet);
  const status: FindingStatus = view.status === "done" ? (view.corrected_copy_id ? "fixed" : "dismissed") : "detected";
  return [
    {
      cell: patch.cell,
      sheet: sheetName,
      address,
      title: line ? `${line} ${phrase}` : `${patch.cell} ${phrase}`,
      type: typeLabel,
      before: patch.old_formula,
      after: patch.new_formula,
      explanation: explanationOf(view.report),
      status,
      dependents: dependentsOf(view, patch.cell),
    },
  ];
}

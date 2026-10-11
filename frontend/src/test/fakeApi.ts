import type { InvestigationView } from "../api";

export const STEPS: [string, string][] = [
  ["load_sheet", "Reading the workbook"],
  ["map_model", "Understanding the model's layout"],
  ["locate", "Finding the cell"],
  ["trace", "Tracing the formulas"],
  ["diagnose", "Looking for the root cause"],
  ["test", "Testing the fix"],
  ["verify", "Verifying the fix"],
  ["explain", "Writing the explanation"],
];

const REPORT =
  "EBITDA 2027E moved from 40.03 to 52.01 (ev-1). Root cause found in P&L!H7: P&L!H7 is a typed number, not a formula (evidence: ev-3). The fix was tested: P&L!H8 52.01 -> 44.73 in a sandbox copy after patching P&L!H7 (ev-4).";

export const REVIEW: InvestigationView = {
  id: "inv-1",
  status: "needs_review",
  pause: { report: REPORT, patch: { cell: "P&L!H7", old_formula: "-45.2", new_formula: "=G7*(1+Assumptions!$C$7)", source: "agent" } },
  question: "Why did EBITDA 2027 jump?",
  target: { sheet: "P&L", cell: "H8", label: "EBITDA", period: "2027E", value: 52.01, prior_cell: "G8", prior_value: 40.03 },
  causal_tree: {
    cell: "P&L!H8", label: "EBITDA", value_before: 40.03, value_after: 52.01, delta: 11.98, share_of_change: 1, suspicious: false,
    children: [
      { cell: "P&L!H6", label: "Gross profit", value_before: 89.68, value_after: 96.88, delta: 7.2, share_of_change: 0.6, suspicious: false, children: [] },
      { cell: "P&L!H7", label: "Opex", value_before: -49.98, value_after: -45.2, delta: 4.78, share_of_change: 0.4, suspicious: true, children: [] },
    ],
  },
  hypotheses: [
    { id: "hyp-1", cell: "P&L!H7", error_type: "typed_value", claim: "P&L!H7 is a typed number, not a formula", evidence_ids: ["ev-3"], confidence: "high", status: "confirmed" },
    { id: "hyp-2", cell: "P&L!H5", error_type: "sign_inconsistency", claim: "COGS sign differs from the row", evidence_ids: [], confidence: "low", status: "rejected" },
  ],
  evidence: [
    { id: "ev-1", cell: "P&L!H8", kind: "anomaly", text: "EBITDA 2027E = 52.01, prior period G8 = 40.03" },
    { id: "ev-2", cell: "P&L!H6", kind: "expected_pattern", text: "Gross profit contributes +7.20" },
    { id: "ev-3", cell: "P&L!H7", kind: "anomaly", text: "Opex contributes +4.78; typed value where the row uses formulas" },
    { id: "ev-4", cell: "P&L!H7", kind: "verification", text: "P&L!H8 52.01 -> 44.73 in a sandbox copy after patching P&L!H7" },
  ],
  verifications: [{ hypothesis_id: "hyp-1", before: { "P&L!H8": 52.01 }, after: { "P&L!H8": 44.73, "P&L!H7": -52.48 }, checks: { anomaly_resolved: true }, verdict: "confirmed", reason: "the sandbox numbers hold" }],
  patch: { cell: "P&L!H7", old_formula: "-45.2", new_formula: "=G7*(1+Assumptions!$C$7)", source: "agent" },
  report: REPORT,
  corrected_copy_id: null,
  known_overrides: [],
  run_log: [],
};

export const CELL_CHOICE: InvestigationView = {
  ...REVIEW,
  status: "needs_cell",
  pause: { question: "Which cell do you mean?", candidates: ["P&L!H8", "Summary!D10"] },
  target: null,
  causal_tree: null,
  hypotheses: [],
  evidence: [],
  verifications: [],
  patch: null,
  report: null,
};

export const APPROVED: InvestigationView = { ...REVIEW, status: "done", pause: null, corrected_copy_id: "demo-corrected.xlsx" };
export const REJECTED: InvestigationView = { ...REVIEW, status: "done", pause: null, corrected_copy_id: null };

export const SHEET = {
  sheet: "P&L",
  header_row: 3,
  columns: [
    { letter: "F", header: "2025A" },
    { letter: "G", header: "2026E" },
    { letter: "H", header: "2027E" },
  ],
  rows: [
    { row: 7, label: "Opex", cells: [{ ref: "P&L!F7", value: -47.6, formula: null }, { ref: "P&L!G7", value: -49.98, formula: "=F7*(1+Assumptions!$C$7)" }, { ref: "P&L!H7", value: -45.2, formula: null }] },
    { row: 8, label: "EBITDA", cells: [{ ref: "P&L!F8", value: 35.7, formula: "=F6+F7" }, { ref: "P&L!G8", value: 40.03, formula: "=G6+G7" }, { ref: "P&L!H8", value: 52.01, formula: "=H6+H7" }] },
  ],
};

type Event = ["step", string, string] | ["view", InvestigationView] | ["error", number, string];

function sse(events: Event[]): string {
  return events
    .map((event) => {
      if (event[0] === "step") return `event: step\ndata: ${JSON.stringify({ step: event[1], label: event[2] })}\n\n`;
      if (event[0] === "view") return `event: view\ndata: ${JSON.stringify(event[1])}\n\n`;
      return `event: error\ndata: ${JSON.stringify({ status: event[1], detail: event[2] })}\n\n`;
    })
    .join("");
}

function streamed(text: string): Response {
  const bytes = new TextEncoder().encode(text);
  const middle = Math.floor(bytes.length / 2);
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(bytes.slice(0, middle));
      controller.enqueue(bytes.slice(middle));
      controller.close();
    },
  });
  return new Response(body, { headers: { "Content-Type": "text/event-stream" } });
}

export function steps(...names: string[]): Event[] {
  return names.map((name) => {
    const label = STEPS.find(([step]) => step === name)?.[1] ?? { human_review: "Saving the decision", apply_fix: "Saving a new version" }[name] ?? name;
    return ["step", name, label];
  });
}

export function fakeApi(start: Event[], resumes: Event[][] = []) {
  const sent: { url: string; body: unknown }[] = [];
  const queue = [...resumes];
  const fetch = async (url: string, init?: RequestInit): Promise<Response> => {
    const body = init?.body && typeof init.body === "string" ? JSON.parse(init.body) : init?.body;
    sent.push({ url, body });
    if (url.endsWith("/spreadsheets")) return Response.json([{ id: "demo", sheets: ["P&L", "Assumptions", "Summary"] }]);
    if (url.includes("/spreadsheets?name=")) return Response.json({ id: "upload-1", name: decodeURIComponent(url.split("name=")[1]), sheets: ["P&L"] }, { status: 201 });
    if (url.endsWith("/sheet")) return Response.json(SHEET);
    if (url.endsWith("/investigations/stream")) return streamed(sse(start));
    if (url.includes("/resume/stream")) return streamed(sse(queue.shift() ?? []));
    return Response.json({ detail: "unknown" }, { status: 404 });
  };
  return { fetch, sent };
}

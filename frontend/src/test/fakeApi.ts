import type { InvestigationView, SheetWindow, WorkbookView } from "../api";
import done from "./recorded/done.json";
import review from "./recorded/review.json";
import sheet from "./recorded/sheet.json";

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

export const REVIEW = review as unknown as InvestigationView;
export const APPROVED = done as unknown as InvestigationView;
export const SHEET = sheet as unknown as SheetWindow;

export const WORKBOOK: WorkbookView = {
  sheets: [
    {
      name: "P&L",
      rows: 6,
      columns: 7,
      cells: [
        { ref: "A1", value: "Deal model P&L", formula: null },
        { ref: "A4", value: "Revenue", formula: null },
        { ref: "G4", value: 188, formula: null },
        { ref: "A5", value: "COGS", formula: null },
        { ref: "G5", value: 97.76, formula: "=G4*Assumptions!$C$5" },
        { ref: "A6", value: "Gross profit", formula: null },
        { ref: "G6", value: 285.76, formula: "=G4+G5" },
      ],
    },
    { name: "Assumptions", rows: 5, columns: 3, cells: [{ ref: "C5", value: 0.52, formula: null }] },
    { name: "Summary", rows: 6, columns: 8, cells: [{ ref: "G5", value: 225.6, formula: "='P&L'!G10" }, { ref: "H6", value: -0.8586666666666667, formula: "=H5/G5-1" }] },
  ],
};

export const REJECTED: InvestigationView = { ...REVIEW, status: "done", pause: null, corrected_copy_id: null };

export const CLEAR: InvestigationView = {
  ...REVIEW,
  status: "needs_review",
  pause: null,
  patch: null,
  hypotheses: (REVIEW.hypotheses ?? []).map((hypothesis) => ({ ...hypothesis, status: "rejected" })),
  verifications: [],
  report:
    "No error found. Gross profit 2025A moved from 84.72 to 285.76 (ev-1) because COGS (P&L!G5) is 97.84, the same sign as the cost rows below it (ev-2, ev-3). The formula matches the row pattern and no cell broke its own pattern, so no fix was written.",
};

export const TESTED: InvestigationView = {
  ...REVIEW,
  status: "running",
  pause: null,
  report: null,
  corrected_copy_id: null,
  hypotheses: (REVIEW.hypotheses ?? []).map((hypothesis) => ({ ...hypothesis, status: "open" })),
  verifications: [
    {
      hypothesis_id: "hyp-1",
      before: { "P&L!G5": 97.76, "P&L!G6": 285.76, "P&L!G10": 225.6, "P&L!G11": 1.2, "Summary!G5": 225.6, "Summary!G6": 6.988668555240794, "Summary!H6": -0.8586666666666667 },
      after: { "P&L!G5": -97.76, "P&L!G6": 90.24, "P&L!G10": 30.08, "P&L!G11": 0.16, "Summary!G5": 30.08, "Summary!G6": 0.06515580736543924, "Summary!H6": 0.06000000000000005 },
    },
  ],
};

export const RUNNING: InvestigationView = {
  ...REVIEW,
  status: "running",
  pause: null,
  report: null,
  patch: null,
  verifications: null,
  corrected_copy_id: null,
  causal_tree: null,
  hypotheses: [],
  evidence: [],
  run_log: [
    { role: "investigator", model: "nvidia/nemotron-3-super-120b-a12b", input_tokens: 1840, output_tokens: 412, latency_ms: 2140 },
    { role: "verifier", model: null, input_tokens: 660, output_tokens: 97, latency_ms: 810 },
  ],
};

export function fakeSteps(story: string): { step: string; label: string }[] {
  const count = story === "starting" ? 0 : story === "running" ? 5 : STEPS.length;
  return STEPS.slice(0, count).map(([step, label]) => ({ step, label }));
}

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

export function fakeApi(start: Event[], resumes: Event[][] = [], failures: string[] = [], answers: string[] = [], rounds: Event[][] = []) {
  const sent: { url: string; body: unknown }[] = [];
  const queue = [...resumes];
  const starts = [start, ...rounds];
  let started = 0;
  const refusals = [...failures];
  const replies = [...answers];
  const fetch = async (url: string, init?: RequestInit): Promise<Response> => {
    const raw = init?.body;
    const body =
      raw instanceof FormData
        ? { ...JSON.parse(String(raw.get("request"))), file: (raw.get("file") as File | null)?.name }
        : raw && typeof raw === "string"
          ? JSON.parse(raw)
          : raw;
    sent.push({ url, body });
    if (url.endsWith("/spreadsheets")) return Response.json([{ id: "demo", sheets: ["P&L", "Assumptions", "Summary"] }]);
    if (url.includes("/spreadsheets?name=")) return Response.json({ id: "upload-1", name: decodeURIComponent(url.split("name=")[1]), sheets: ["P&L"] }, { status: 201 });
    if (url.endsWith("/sheet")) return Response.json(SHEET);
    if (url.endsWith("/workbook")) return Response.json(WORKBOOK);
    if (url.endsWith("/ask")) return Response.json({ answer: replies.shift() ?? "No answer scripted." });
    if (url.endsWith("/investigations/stream")) return streamed(sse(starts[started++] ?? [...steps("explain"), ["view", CLEAR]]));
    if (url.includes("/resume/stream")) {
      const refusal = refusals.shift();
      if (refusal) return Response.json({ detail: refusal }, { status: 422 });
      return streamed(sse(queue.shift() ?? []));
    }
    return Response.json({ detail: "unknown" }, { status: 404 });
  };
  return { fetch, sent };
}

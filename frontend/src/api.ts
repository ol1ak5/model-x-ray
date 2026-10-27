export const API_URL = (import.meta.env.VITE_API_URL as string | undefined) ?? (import.meta.env.PROD ? "" : "http://localhost:8000");

export type Spreadsheet = { id: string; sheets: string[] };

export type TargetCell = {
  sheet: string;
  cell: string;
  label: string;
  period: string;
  value: number;
  prior_cell: string;
  prior_value: number;
};

export type CausalNode = {
  cell: string;
  label: string;
  value_before: number;
  value_after: number;
  delta: number;
  share_of_change: number;
  suspicious: boolean;
  children: CausalNode[];
};

export type Hypothesis = {
  id: string;
  cell: string;
  error_type: string;
  claim: string;
  evidence_ids: string[];
  confidence: "high" | "medium" | "low";
  status: "open" | "rejected" | "confirmed";
};

export type Evidence = { id: string; cell: string; kind: "anomaly" | "expected_pattern" | "verification"; text: string };

export type Verification = {
  hypothesis_id: string;
  before: Record<string, number>;
  after: Record<string, number>;
  checks?: Record<string, boolean>;
  verdict?: "confirmed" | "rejected" | "inconclusive";
  reason?: string;
};

export type Patch = { cell: string; old_formula: string; new_formula: string; source: "agent" | "human" };

export type Override = { cell: string; content: string; reason: string };

export type TargetChoice = { candidates: string[]; chosen: string; why: string };
export type ReviewPause = { report: string; patch: Patch | null };

export type ModelMap = {
  rows: { label: string; kind: string }[];
  columns: { period: string; kind: string }[];
};

export type Finding = { cell: string; error_type: string; old_formula: string; new_formula: string };

export type Contribution = { cell: string; label: string; delta: number };

export type InvestigationView = {
  id: string;
  status: "running" | "needs_review" | "done";
  pause: ReviewPause | null;
  question: string | null;
  target_choice?: TargetChoice | null;
  target: TargetCell | null;
  causal_tree: CausalNode | null;
  hypotheses: Hypothesis[] | null;
  evidence: Evidence[] | null;
  verifications: Verification[] | null;
  patch: Patch | null;
  report: string | null;
  corrected_copy_id: string | null;
  known_overrides: Override[] | null;
  past_findings: Finding[] | null;
  model_map: ModelMap | null;
  contributions: Contribution[] | null;
  human_decision: Decision | null;
  tool_call_counts: number[] | null;
  node_log: { node: string; latency_ms: number }[] | null;
  attempts: number | null;
  check_labels?: Record<string, string>;
  run_log: { role: string; model: string | null; input_tokens: number | null; output_tokens: number | null; latency_ms: number }[] | null;
  sheet?: SheetWindow | null;
  corrected_file?: CorrectedFile | null;
};

export type CorrectedFile = { name: string; base64: string };

export type Decision = {
  action: "approve" | "edit" | "reject";
  reason: string;
  intentional?: boolean;
  patch?: { cell: string; old_formula: string; new_formula: string };
};

export type ProgressEvent =
  | { kind: "step"; step: string; label: string }
  | { kind: "view"; view: InvestigationView }
  | { kind: "error"; status: number; detail: string };

export class ApiError extends Error {}

async function failure(response: Response): Promise<ApiError> {
  try {
    const body = await response.json();
    return new ApiError(typeof body.detail === "string" ? body.detail : "The request failed.");
  } catch {
    return new ApiError("The Model X-Ray service could not be reached. Please try again.");
  }
}

export type Uploaded = { id: string; name: string; sheets: string[] };

export async function uploadSpreadsheet(file: File): Promise<Uploaded> {
  const response = await fetch(`${API_URL}/spreadsheets?name=${encodeURIComponent(file.name)}`, {
    method: "POST",
    headers: { "Content-Type": "application/octet-stream" },
    body: file,
  });
  if (!response.ok) throw await failure(response);
  return response.json();
}

export async function listSpreadsheets(): Promise<Spreadsheet[]> {
  const response = await fetch(`${API_URL}/spreadsheets`);
  if (!response.ok) throw await failure(response);
  return response.json();
}

export function parseEvents(text: string): { events: ProgressEvent[]; rest: string } {
  const blocks = text.split("\n\n");
  const rest = blocks.pop() ?? "";
  const events: ProgressEvent[] = [];
  for (const block of blocks) {
    const fields = Object.fromEntries(
      block.split("\n").filter((line) => line.includes(": ")).map((line) => [line.slice(0, line.indexOf(": ")), line.slice(line.indexOf(": ") + 2)]),
    );
    const data = JSON.parse(fields.data ?? "{}");
    if (fields.event === "step") events.push({ kind: "step", step: data.step, label: data.label });
    if (fields.event === "view") events.push({ kind: "view", view: data });
    if (fields.event === "error") events.push({ kind: "error", status: data.status, detail: data.detail });
  }
  return { events, rest };
}

function requestBody(body: unknown, file?: File | null): RequestInit {
  if (!file) return { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
  const form = new FormData();
  form.append("request", JSON.stringify(body));
  form.append("file", file, file.name);
  return { method: "POST", body: form };
}

async function stream(path: string, body: unknown, onEvent: (event: ProgressEvent) => void, file?: File | null): Promise<void> {
  const response = await fetch(`${API_URL}${path}`, requestBody(body, file));
  if (!response.ok || !response.body) throw await failure(response);
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    const parsed = parseEvents(buffer + decoder.decode(value, { stream: true }));
    buffer = parsed.rest;
    parsed.events.forEach(onEvent);
  }
  parseEvents(buffer + "\n\n").events.forEach(onEvent);
}

export function startInvestigation(spreadsheetId: string, question: string, onEvent: (event: ProgressEvent) => void, file?: File | null, setAside: string[] = []): Promise<void> {
  const body = setAside.length ? { spreadsheet_id: spreadsheetId, question, set_aside: setAside } : { spreadsheet_id: spreadsheetId, question };
  return stream("/investigations/stream", body, onEvent, file);
}

export function resumeInvestigation(id: string, answer: Decision, onEvent: (event: ProgressEvent) => void, state?: InvestigationView | null, file?: File | null): Promise<void> {
  const carried = state ? { ...state, sheet: undefined, corrected_file: undefined } : null;
  return stream(`/investigations/${id}/resume/stream`, carried ? { ...answer, state: carried } : answer, onEvent, file);
}

export type SheetCell = { ref: string; value: number | null; formula: string | null };
export type SheetWindow = { sheet: string; header_row?: number | null; columns: { letter: string; header: string }[]; rows: { row: number; label: string; cells: SheetCell[] }[] };

export async function getSheet(id: string): Promise<SheetWindow> {
  const response = await fetch(`${API_URL}/investigations/${id}/sheet`);
  if (!response.ok) throw await failure(response);
  return response.json();
}

export type ChatTurn = { role: "user" | "agent"; text: string };

export async function askAgent(id: string, question: string, state: InvestigationView, history: ChatTurn[]): Promise<string> {
  const response = await fetch(`${API_URL}/investigations/${id}/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, history, state: { ...state, sheet: undefined, corrected_file: undefined } }),
  });
  if (!response.ok) throw await failure(response);
  return (await response.json()).answer;
}

export type WorkbookCell = { ref: string; value: number | string | boolean | null; formula: string | null };
export type WorkbookSheet = { name: string; rows: number; columns: number; cells: WorkbookCell[] };
export type WorkbookView = { sheets: WorkbookSheet[] };

export async function getWorkbook(spreadsheetId: string, file?: File | null): Promise<WorkbookView> {
  const response = await fetch(`${API_URL}/workbook`, requestBody({ spreadsheet_id: spreadsheetId }, file));
  if (!response.ok) throw await failure(response);
  return response.json();
}

export function correctedFileUrl(id: string): string {
  return `${API_URL}/investigations/${id}/corrected`;
}

const XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";

export function correctedFileHref(view: InvestigationView): { href: string; download?: string } {
  if (!view.corrected_file) return { href: correctedFileUrl(view.id) };
  return { href: `data:${XLSX_TYPE};base64,${view.corrected_file.base64}`, download: view.corrected_file.name };
}

export function fileOf(corrected: CorrectedFile, name: string): File {
  const bytes = Uint8Array.from(atob(corrected.base64), (char) => char.charCodeAt(0));
  return new File([bytes], name, { type: XLSX_TYPE });
}

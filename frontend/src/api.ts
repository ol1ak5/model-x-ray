export const API_URL = (import.meta.env.VITE_API_URL as string | undefined) ?? "http://localhost:8000";

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
  checks: Record<string, boolean>;
  verdict: "confirmed" | "rejected" | "inconclusive";
  reason: string;
};

export type Patch = { cell: string; old_formula: string; new_formula: string; source: "agent" | "human" };

export type Override = { cell: string; content: string; reason: string };

export type CellChoicePause = { question: string; candidates: string[] };
export type ReviewPause = { report: string; patch: Patch | null };

export type InvestigationView = {
  id: string;
  status: "needs_cell" | "needs_review" | "done";
  pause: CellChoicePause | ReviewPause | null;
  question: string | null;
  target: TargetCell | null;
  causal_tree: CausalNode | null;
  hypotheses: Hypothesis[] | null;
  evidence: Evidence[] | null;
  verifications: Verification[] | null;
  patch: Patch | null;
  report: string | null;
  corrected_copy_id: string | null;
  known_overrides: Override[] | null;
  run_log: { role: string; model: string | null; input_tokens: number | null; output_tokens: number | null; latency_ms: number }[] | null;
};

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

async function stream(path: string, body: unknown, onEvent: (event: ProgressEvent) => void): Promise<void> {
  const response = await fetch(`${API_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
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

export function startInvestigation(spreadsheetId: string, question: string, onEvent: (event: ProgressEvent) => void): Promise<void> {
  return stream("/investigations/stream", { spreadsheet_id: spreadsheetId, question }, onEvent);
}

export function resumeInvestigation(id: string, answer: { ref: string } | Decision, onEvent: (event: ProgressEvent) => void): Promise<void> {
  return stream(`/investigations/${id}/resume/stream`, answer, onEvent);
}

export function correctedFileUrl(id: string): string {
  return `${API_URL}/investigations/${id}/corrected`;
}

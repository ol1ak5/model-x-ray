import type { InvestigationView, SheetWindow } from "./api";

export const STORAGE_KEY = "model-x-ray:runs:v1";

const VERSION = 1;
const KEEP = 25;

export type StoredStep = { step: string; label: string };

export type StoredRun = {
  id: string;
  spreadsheetId: string;
  name: string;
  question: string;
  startedAt: number;
  updatedAt: number;
  steps: StoredStep[];
  view: InvestigationView | null;
  sheet: SheetWindow | null;
};

type Stored = { version: number; current: string | null; runs: StoredRun[] };

export function newRunId(): string {
  return `run-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

function store(): Storage | null {
  try {
    return typeof window === "undefined" ? null : window.localStorage;
  } catch {
    return null;
  }
}

function isRun(value: unknown): value is StoredRun {
  const run = value as StoredRun | null;
  return typeof run?.id === "string" && typeof run?.spreadsheetId === "string" && Array.isArray(run?.steps);
}

function read(): Stored {
  const empty: Stored = { version: VERSION, current: null, runs: [] };
  const raw = store()?.getItem(STORAGE_KEY);
  if (!raw) return empty;
  try {
    const parsed = JSON.parse(raw) as Stored;
    if (parsed.version !== VERSION || !Array.isArray(parsed.runs)) return empty;
    const runs = parsed.runs.filter(isRun).map((run) => ({ ...run, view: run.view ?? null, sheet: run.sheet ?? null }));
    const current = runs.some((run) => run.id === parsed.current) ? parsed.current : null;
    return { version: VERSION, current, runs };
  } catch {
    return empty;
  }
}

function write(state: Stored): void {
  const storage = store();
  if (!storage) return;
  let runs = state.runs.slice(0, KEEP);
  for (;;) {
    try {
      storage.setItem(STORAGE_KEY, JSON.stringify({ ...state, runs }));
      return;
    } catch {
      if (runs.length === 0) {
        try {
          storage.removeItem(STORAGE_KEY);
        } catch {
          return;
        }
        return;
      }
      runs = runs.slice(0, -1);
    }
  }
}

export function listRuns(): StoredRun[] {
  return read().runs;
}

export function currentRun(): StoredRun | null {
  const state = read();
  return state.runs.find((run) => run.id === state.current) ?? null;
}

export function saveRun(run: StoredRun): void {
  const state = read();
  const others = state.runs.filter((held) => held.id !== run.id);
  const runs = [run, ...others].sort((left, right) => right.updatedAt - left.updatedAt);
  write({ version: VERSION, current: run.id, runs });
}

export function clearCurrent(): void {
  const state = read();
  write({ ...state, current: null });
}

export function deleteRun(id: string): void {
  const state = read();
  write({ version: VERSION, current: state.current === id ? null : state.current, runs: state.runs.filter((run) => run.id !== id) });
}

export function clearRuns(): void {
  try {
    store()?.removeItem(STORAGE_KEY);
  } catch {
    return;
  }
}

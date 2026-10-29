import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  ApiError,
  type Decision,
  type InvestigationView,
  type ChatTurn,
  type ProgressEvent,
  type SheetWindow,
  type Spreadsheet,
  askAgent,
  fileOf,
  findSuspects,
  getSheet,
  getWorkbook,
  listSpreadsheets,
  resumeInvestigation,
  startInvestigation,
  uploadSpreadsheet,
} from "./api";
import CheckPage from "./check/CheckPage";
import Boundary from "./components/Boundary";
import Wave from "./components/Wave";
import { findingsOf } from "./findings";
import Landing from "./landing/Landing";
import { phasesOf, statusOf } from "./progress";
import { type StoredStep, clearCurrent, currentRun, newRunId, saveRun } from "./storage";
import { APPROVED, REVIEW, RUNNING, SHEET, fakeSteps } from "./test/fakeApi";

type Run = { id: string; spreadsheetId: string; name: string; question: string; startedAt: number; sheets: string[] };

const UNREACHABLE = "The Model X-Ray service could not be reached. Please try again.";

const ADVICE: Record<string, string> = {
  provider_busy: "The AI service is overloaded. Wait a minute, then try again.",
  provider_timeout: "The AI service took too long. Try again, or check a smaller model.",
  provider_auth: "The deployment's key was refused. The team has to replace it; nothing here will fix it.",
  usage_cap: "The demo's daily limit is reached. Try again tomorrow, or run Model X-Ray locally.",
  workbook_unreadable: "That file could not be read. Send a .xlsx saved by Excel.",
  unsupported_formula: "This model uses a formula the engine cannot calculate yet.",
  unexpected: "Something failed on our side. Try again; the team has the details.",
};

type Failure = { message: string; advice: string };

function described(reason: unknown, fallback = UNREACHABLE): Failure {
  const error = reason instanceof ApiError ? reason : new ApiError(fallback);
  return { message: error.message, advice: ADVICE[error.code] ?? "" };
}

const DEMO_NAME = "Demo model.xlsx";

const DEMOS: Record<string, string> = { "PPA_Model_Europe": "PPA_Model_Europe.xlsx", demo: DEMO_NAME };

function storyRun(story: string | null): { run: Run; views: (InvestigationView | null)[]; busy: number } | null {
  const view = story === "workspace" ? REVIEW : story === "done" ? APPROVED : story === "running" ? RUNNING : null;
  if (!story || (!view && story !== "starting")) return null;
  const run = { id: `story-${story}`, spreadsheetId: "demo", name: DEMO_NAME, question: "", startedAt: 0, sheets: ["P&L", "Assumptions", "Summary"] };
  const busy = story === "running" || story === "starting" ? 1 : 0;
  return { run, views: [story === "running" ? null : view], busy };
}

function groupsOf(suspects: string[]): string[][] {
  return suspects.length < 2 ? [[]] : suspects.map((cell) => suspects.filter((other) => other !== cell));
}

export default function App() {
  const story = import.meta.env.DEV ? new URLSearchParams(window.location.search).get("story") : null;
  const initial = storyRun(story);
  const [demos, setDemos] = useState<Spreadsheet[]>([]);
  const [check, setCheck] = useState<Run | null>(initial?.run ?? null);
  const [busy, setBusy] = useState(initial?.busy ?? 0);
  const [steps, setSteps] = useState<StoredStep[]>(story ? fakeSteps(story) : []);
  const [views, setViews] = useState<(InvestigationView | null)[]>(initial?.views ?? []);
  const [sheet, setSheet] = useState<SheetWindow | null>(initial ? SHEET : null);
  const [fixedIn, setFixedIn] = useState<InvestigationView | null>(null);
  const [error, setError] = useState<Failure | null>(null);
  const [uploading, setUploading] = useState(false);
  const upload = useRef<File | null>(null);
  const onCopy = useRef(false);
  const first = views[0] ?? null;

  useEffect(() => {
    if (story) return;
    const saved = currentRun();
    const restored = saved?.views ?? (saved?.view ? [saved.view] : []);
    if (!saved || restored.length === 0) return;
    setCheck({ id: saved.id, spreadsheetId: saved.spreadsheetId, name: saved.name, question: saved.question, startedAt: saved.startedAt, sheets: saved.sheets ?? [] });
    setSteps(saved.steps);
    setViews(restored);
    setSheet(saved.sheet);
    setFixedIn(saved.fixedIn ?? null);
  }, []);

  useEffect(() => {
    if (!check || story) return;
    saveRun({ ...check, updatedAt: Date.now(), steps, view: first, views, sheet, fixedIn });
  }, [check, steps, views, sheet, fixedIn]);

  useEffect(() => {
    listSpreadsheets()
      .then(setDemos)
      .catch((reason: unknown) => setError(described(reason)));
  }, []);

  useEffect(() => {
    if (!first?.target || story) return;
    if (first.sheet) {
      setSheet(first.sheet);
      return;
    }
    if (sheet) return;
    getSheet(first.id)
      .then(setSheet)
      .catch(() => undefined);
  }, [first]);

  function eventsFor(slot: number, seen?: { view: InvestigationView | null }) {
    return (event: ProgressEvent) => {
      if (event.kind === "step") setSteps((current) => [...current, { step: event.step, label: event.label }]);
      if (event.kind === "view") {
        if (seen) seen.view = event.view;
        setViews((current) => current.map((view, index) => (index === slot ? event.view : view)));
      }
      if (event.kind === "error") setError({ message: event.detail, advice: ADVICE[event.code] ?? "" });
    };
  }

  async function run(work: () => Promise<void>) {
    setBusy((count) => count + 1);
    try {
      await work();
    } catch (reason) {
      setError(described(reason));
    } finally {
      setBusy((count) => count - 1);
    }
  }

  const start = useCallback((spreadsheetId: string, name: string, sheets: string[], file: File | null) => {
    upload.current = file;
    onCopy.current = false;
    setSteps([]);
    setViews([]);
    setSheet(null);
    setFixedIn(null);
    setError(null);
    setCheck({ id: newRunId(), spreadsheetId, name, question: "", startedAt: Date.now(), sheets });
    window.scrollTo?.({ top: 0 });
    void run(async () => {
      const suspects = await findSuspects(spreadsheetId, file).catch(() => []);
      const groups = groupsOf(suspects);
      setViews(groups.map(() => null));
      await Promise.all(groups.map((aside, slot) => run(() => startInvestigation(spreadsheetId, "", eventsFor(slot), file, aside))));
    });
  }, []);

  const startDemo = useCallback(() => {
    const demo = demos.find((candidate) => candidate.id === "PPA_Model_Europe") ?? demos[0];
    if (demo) start(demo.id, DEMOS[demo.id] ?? `${demo.id}.xlsx`, demo.sheets, null);
  }, [demos, start]);

  const startUpload = useCallback(
    async (file: File) => {
      setError(null);
      setUploading(true);
      try {
        const uploaded = await uploadSpreadsheet(file);
        start(uploaded.id, uploaded.name, uploaded.sheets, file);
      } catch (reason) {
        setError(described(reason, "The upload failed. Please try again."));
      } finally {
        setUploading(false);
      }
    },
    [start],
  );

  const decide = useCallback(
    (cell: string, answer: Decision) => {
      const slot = views.findIndex((view) => view?.patch?.cell === cell);
      const view = views[slot];
      if (!view || !check) return;
      setError(null);
      const seen: { view: InvestigationView | null } = { view: null };
      void run(async () => {
        await resumeInvestigation(view.id, answer, eventsFor(slot, seen), view, upload.current, onCopy.current);
        const settled = seen.view;
        if (settled?.corrected_file) {
          upload.current = fileOf(settled.corrected_file, check.name);
          onCopy.current = true;
        }
        if (settled?.corrected_copy_id) setFixedIn({ ...settled, sheet: null });
      });
    },
    [views, check],
  );

  const retry = useCallback(() => {
    if (check) start(check.spreadsheetId, check.name, check.sheets, upload.current);
  }, [check, start]);

  const ask = useCallback(
    (cell: string, question: string, history: ChatTurn[]) => {
      const view = views.find((candidate) => candidate?.patch?.cell === cell);
      if (!view) return Promise.reject(new ApiError("The check has not finished yet."));
      return askAgent(view.id, question, view, history);
    },
    [views],
  );

  const reset = useCallback(() => {
    setSteps([]);
    setViews([]);
    setSheet(null);
    setFixedIn(null);
    setError(null);
    setCheck(null);
    upload.current = null;
    onCopy.current = false;
    clearCurrent();
    const url = new URL(window.location.href);
    url.searchParams.delete("story");
    window.history.replaceState(null, "", url);
    window.scrollTo?.({ top: 0 });
  }, []);

  const spreadsheetId = check?.spreadsheetId ?? "";
  const loadWorkbook = useCallback(() => getWorkbook(spreadsheetId, upload.current), [spreadsheetId]);
  const running = busy > 0;
  const phases = useMemo(() => phasesOf(steps, views, running), [steps, views, running]);
  const findings = useMemo(() => views.flatMap((view) => findingsOf(view, view?.sheet ?? sheet)), [views, sheet]);
  const status = statusOf(views, running, steps.at(-1)?.label ?? null);
  const shown = views.length > 0 && views.every((view) => view !== null) ? first : null;

  return (
    <>
      <Wave />
      {check ? (
        <Boundary onReset={reset}>
          <CheckPage
            name={check.name}
            sheets={check.sheets}
            phases={phases}
            status={status}
            findings={findings}
            view={shown}
            fixedIn={fixedIn}
            running={running}
            error={error}
            loadWorkbook={loadWorkbook}
            onDecide={decide}
            onHome={reset}
            onDemo={startDemo}
            onRetry={retry}
            onAsk={ask}
          />
        </Boundary>
      ) : (
        <Landing onDemo={startDemo} onUpload={startUpload} busy={uploading} demoReady={demos.length > 0} error={error} />
      )}
    </>
  );
}

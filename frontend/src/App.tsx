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
import { type Finding, findingsOf } from "./findings";
import Landing from "./landing/Landing";
import { phasesOf, statusOf } from "./progress";
import { type StoredStep, clearCurrent, currentRun, newRunId, saveRun } from "./storage";
import { APPROVED, REVIEW, RUNNING, SHEET, fakeSteps } from "./test/fakeApi";

type Phase = "idle" | "running" | "paused" | "done" | "interrupted";

type Run = { id: string; spreadsheetId: string; name: string; question: string; startedAt: number; sheets: string[] };

const UNREACHABLE = "The Model X-Ray service could not be reached. Please try again.";

const DEMO_NAME = "Demo model.xlsx";

const MAX_ROUNDS = 6;

const DEMOS: Record<string, string> = { "PPA_Model_Europe": "PPA_Model_Europe.xlsx", demo: DEMO_NAME };

function storyRun(story: string | null): { run: Run; view: InvestigationView | null; phase: Phase } | null {
  const view = story === "workspace" ? REVIEW : story === "done" ? APPROVED : story === "running" ? RUNNING : null;
  if (!story || (!view && story !== "starting")) return null;
  const run = { id: `story-${story}`, spreadsheetId: "demo", name: DEMO_NAME, question: "", startedAt: 0, sheets: ["P&L", "Assumptions", "Summary"] };
  return { run, view: story === "running" ? null : view, phase: story === "done" ? "done" : story === "workspace" ? "paused" : "running" };
}

export default function App() {
  const story = import.meta.env.DEV ? new URLSearchParams(window.location.search).get("story") : null;
  const initial = storyRun(story);
  const [demos, setDemos] = useState<Spreadsheet[]>([]);
  const [check, setCheck] = useState<Run | null>(initial?.run ?? null);
  const [phase, setPhase] = useState<Phase>(initial?.phase ?? "idle");
  const [steps, setSteps] = useState<StoredStep[]>(story ? fakeSteps(story) : []);
  const [view, setView] = useState<InvestigationView | null>(initial?.view ?? null);
  const [sheet, setSheet] = useState<SheetWindow | null>(initial ? SHEET : null);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [earlier, setEarlier] = useState<Finding[]>([]);
  const [setAside, setSetAside] = useState<string[]>([]);
  const [fixedIn, setFixedIn] = useState<InvestigationView | null>(null);
  const upload = useRef<File | null>(null);

  useEffect(() => {
    if (story) return;
    const saved = currentRun();
    if (!saved?.view) return;
    setCheck({ id: saved.id, spreadsheetId: saved.spreadsheetId, name: saved.name, question: saved.question, startedAt: saved.startedAt, sheets: saved.sheets ?? [] });
    setSteps(saved.steps);
    setEarlier(saved.earlier ?? []);
    setSetAside(saved.setAside ?? []);
    setFixedIn(saved.fixedIn ?? null);
    setView(saved.view);
    setSheet(saved.sheet);
    setPhase(saved.view.status === "done" ? "done" : saved.view.status === "running" ? "interrupted" : "paused");
  }, []);

  useEffect(() => {
    if (!check || story) return;
    saveRun({ ...check, updatedAt: Date.now(), steps, view, sheet, earlier, setAside, fixedIn });
  }, [check, steps, view, sheet, earlier, setAside, fixedIn]);

  useEffect(() => {
    listSpreadsheets()
      .then(setDemos)
      .catch((reason: unknown) => setError(reason instanceof ApiError ? reason.message : UNREACHABLE));
  }, []);

  useEffect(() => {
    if (!view?.target || story) return;
    if (view.sheet) {
      setSheet(view.sheet);
      return;
    }
    if (sheet) return;
    getSheet(view.id)
      .then(setSheet)
      .catch(() => undefined);
  }, [view]);

  function onEvent(event: ProgressEvent) {
    if (event.kind === "step") setSteps((current) => [...current, { step: event.step, label: event.label }]);
    if (event.kind === "view") {
      setView(event.view);
      setPhase(event.view.status === "running" ? "running" : event.view.status === "done" ? "done" : "paused");
    }
    if (event.kind === "error") {
      setError(event.detail);
      setPhase((current) => (current === "running" ? "paused" : current));
    }
  }

  async function run(work: Promise<void>, fallback: Phase) {
    try {
      await work;
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : UNREACHABLE);
      setPhase(fallback);
    }
  }

  const round = useCallback((spreadsheetId: string, aside: string[]) => {
    setSteps([]);
    setView(null);
    setSheet(null);
    setError(null);
    setPhase("running");
    void run(startInvestigation(spreadsheetId, "", onEvent, upload.current, aside), "interrupted");
  }, []);

  const start = useCallback(
    (spreadsheetId: string, name: string, sheets: string[], file: File | null) => {
      upload.current = file;
      setEarlier([]);
      setSetAside([]);
      setFixedIn(null);
      setCheck({ id: newRunId(), spreadsheetId, name, question: "", startedAt: Date.now(), sheets });
      window.scrollTo?.({ top: 0 });
      round(spreadsheetId, []);
    },
    [round],
  );

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
        setError(reason instanceof ApiError ? reason.message : "The upload failed. Please try again.");
      } finally {
        setUploading(false);
      }
    },
    [start],
  );

  const next = useCallback(
    (final: InvestigationView) => {
      if (!check) return;
      const settled = findingsOf(final, final.sheet ?? sheet);
      const found = [...earlier, ...settled];
      const aside = [...setAside, ...settled.map((finding) => finding.cell)];
      if (final.corrected_file) upload.current = fileOf(final.corrected_file, check.name);
      if (final.corrected_copy_id) setFixedIn({ ...final, sheet: null });
      setEarlier(found);
      setSetAside(aside);
      if (found.length < MAX_ROUNDS) round(check.spreadsheetId, aside);
    },
    [check, sheet, earlier, setAside, round],
  );

  const decide = useCallback(
    (answer: Decision) => {
      if (!view) return;
      setError(null);
      setPhase("running");
      const last: { view: InvestigationView | null } = { view: null };
      const watch = (event: ProgressEvent) => {
        if (event.kind === "view") last.view = event.view;
        onEvent(event);
      };
      const work = resumeInvestigation(view.id, answer, watch, view, upload.current).then(() => {
        if (last.view?.status === "done") next(last.view);
      });
      void run(work, "paused");
    },
    [view, next],
  );

  const retry = useCallback(() => {
    if (check) round(check.spreadsheetId, setAside);
  }, [check, setAside, round]);

  const ask = useCallback(
    (question: string, history: ChatTurn[]) => {
      if (!view) return Promise.reject(new ApiError("The check has not finished yet."));
      return askAgent(view.id, question, view, history);
    },
    [view],
  );

  const reset = useCallback(() => {
    setSteps([]);
    setView(null);
    setSheet(null);
    setError(null);
    setPhase("idle");
    setCheck(null);
    setEarlier([]);
    setSetAside([]);
    setFixedIn(null);
    upload.current = null;
    clearCurrent();
    const url = new URL(window.location.href);
    url.searchParams.delete("story");
    window.history.replaceState(null, "", url);
    window.scrollTo?.({ top: 0 });
  }, []);

  const spreadsheetId = check?.spreadsheetId ?? "";
  const loadWorkbook = useCallback(() => getWorkbook(spreadsheetId, upload.current), [spreadsheetId]);
  const running = phase === "running";
  const phases = useMemo(() => phasesOf(steps, view, running), [steps, view, running]);
  const findings = useMemo(() => [...earlier, ...findingsOf(view, sheet).filter((finding) => !earlier.some((settled) => settled.cell === finding.cell))], [earlier, view, sheet]);
  const status = statusOf(view, running, steps.at(-1)?.label ?? null, earlier);

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
            view={view}
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

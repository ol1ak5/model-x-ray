import { memo, useCallback, useEffect, useMemo, useState } from "react";

import {
  ApiError,
  type Decision,
  type InvestigationView,
  type ProgressEvent,
  type SheetWindow,
  type Spreadsheet,
  getSheet,
  listSpreadsheets,
  resumeInvestigation,
  startInvestigation,
} from "./api";
import Alert from "./components/Alert";
import Boundary from "./components/Boundary";
import Button from "./components/Button";
import Chip from "./components/Chip";
import FactsBar from "./components/FactsBar";
import Hero from "./components/Hero";
import Logo from "./components/Logo";
import type { Marks } from "./components/SheetGrid";
import SheetSkeleton from "./components/SheetSkeleton";
import Stage from "./components/Stage";
import StepRail from "./components/StepRail";
import { clearCurrent, currentRun, newRunId, saveRun } from "./storage";
import { type Step, railOf } from "./steps";
import { APPROVED, CLEAR, RUNNING, REVIEW, SHEET, fakeSteps } from "./test/fakeApi";
import styles from "./App.module.css";

type Phase = "idle" | "running" | "paused" | "done" | "interrupted";

type Run = { id: string; spreadsheetId: string; name: string; question: string; startedAt: number };

const UNREACHABLE = "The Model X-Ray service could not be reached. Please try again.";

function marksOf(view: InvestigationView): Marks {
  const hypotheses = view.hypotheses ?? [];
  const suspicious = new Set(hypotheses.filter((h) => h.status === "open").map((h) => h.cell));
  const traced = new Set<string>();
  const walk = (node: InvestigationView["causal_tree"]) => {
    if (!node) return;
    traced.add(node.cell);
    if (node.suspicious) suspicious.add(node.cell);
    node.children.forEach(walk);
  };
  walk(view.causal_tree);
  return {
    suspicious,
    confirmed: new Set(hypotheses.filter((h) => h.status === "confirmed").map((h) => h.cell)),
    traced,
    target: view.target ? `${view.target.sheet}!${view.target.cell}` : null,
    after: view.verifications?.at(-1)?.after ?? {},
    patch: view.patch,
  };
}

const MemoStage = memo(Stage);
const MemoFacts = memo(FactsBar);
const MemoRail = memo(StepRail);

export default function App() {
  const params = import.meta.env.DEV ? new URLSearchParams(window.location.search) : null;
  const story = params?.get("story") ?? null;
  const [demos, setDemos] = useState<Spreadsheet[]>([]);
  const [phase, setPhase] = useState<Phase>(story === "starting" || story === "running" ? "running" : story === "done" ? "done" : story ? "paused" : "idle");
  const [steps, setSteps] = useState<Step[]>(story ? fakeSteps(story) : []);
  const [view, setView] = useState<InvestigationView | null>(
    story === "workspace" ? REVIEW : story === "running" ? RUNNING : story === "done" ? APPROVED : story === "clear" ? CLEAR : null,
  );
  const [sheet, setSheet] = useState<SheetWindow | null>(story === "workspace" || story === "running" || story === "done" || story === "clear" ? SHEET : null);
  const [check, setCheck] = useState<Run | null>(null);
  const [modelName, setModelName] = useState(story ? "My model.xlsx" : "");
  const [error, setError] = useState<string | null>(params?.get("error") ?? null);
  const [sheetError, setSheetError] = useState<string | null>(null);
  const [highlight, setHighlight] = useState<string | null>(null);

  const showEvidence = useCallback(
    (id: string) => {
      const record = view?.evidence?.find((item) => item.id === id);
      if (!record) return;
      setHighlight(record.cell);
      window.setTimeout(() => setHighlight(null), 3800);
    },
    [view],
  );

  useEffect(() => {
    if (story) return;
    const saved = currentRun();
    if (!saved) return;
    setCheck({ id: saved.id, spreadsheetId: saved.spreadsheetId, name: saved.name, question: saved.question, startedAt: saved.startedAt });
    setSteps(saved.steps);
    setView(saved.view);
    setSheet(saved.sheet);
    setModelName(saved.name);
    setPhase(saved.view ? (saved.view.status === "done" ? "done" : saved.view.status === "running" ? "interrupted" : "paused") : "idle");
  }, []);

  useEffect(() => {
    if (!check) return;
    saveRun({ ...check, updatedAt: Date.now(), steps, view, sheet });
  }, [check, steps, view, sheet]);

  useEffect(() => {
    listSpreadsheets()
      .then(setDemos)
      .catch((reason: unknown) => setError(reason instanceof ApiError ? reason.message : UNREACHABLE));
  }, []);

  const targetKey = view?.target ? `${view.id}:${view.target.sheet}` : null;
  useEffect(() => {
    if (!view || !targetKey || story) return;
    getSheet(view.id)
      .then(setSheet)
      .catch((reason: unknown) => {
        setSheetError(reason instanceof ApiError ? reason.message : UNREACHABLE);
      });
  }, [targetKey]);

  function stopped(current: InvestigationView | null): Phase {
    return current && current.status === "needs_review" ? "paused" : "idle";
  }

  function onEvent(event: ProgressEvent) {
    if (event.kind === "step") setSteps((current) => [...current, { step: event.step, label: event.label }]);
    if (event.kind === "view") {
      setView(event.view);
      setPhase(event.view.status === "running" ? "running" : event.view.status === "done" ? "done" : "paused");
    }
    if (event.kind === "error") {
      setError(event.detail);
      setPhase(stopped(view));
    }
  }

  async function run(work: Promise<void>) {
    try {
      await work;
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : UNREACHABLE);
      setPhase(stopped(view));
    }
  }

  const start = useCallback((spreadsheetId: string, question: string, name: string) => {
    setSteps([]);
    setView(null);
    setSheet(null);
    setError(null);
    setSheetError(null);
    setModelName(name);
    setPhase("running");
    setCheck({ id: newRunId(), spreadsheetId, question, name, startedAt: Date.now() });
    void run(startInvestigation(spreadsheetId, question, onEvent));
  }, []);

  const resume = useCallback(
    (answer: Decision) => {
      if (!view) return;
      setError(null);
      setPhase("running");
      void run(resumeInvestigation(view.id, answer, onEvent, view));
    },
    [view],
  );

  const reset = useCallback(() => {
    setSteps([]);
    setView(null);
    setSheet(null);
    setError(null);
    setSheetError(null);
    setPhase("idle");
    setCheck(null);
    clearCurrent();
    const url = new URL(window.location.href);
    ["story", "static", "error"].forEach((key) => url.searchParams.delete(key));
    window.history.replaceState(null, "", url);
  }, []);

  const marks = useMemo(() => (view ? marksOf(view) : null), [view]);
  const rail = useMemo(() => railOf(view, steps, phase === "running"), [view, steps, phase]);

  const stageNote =
    sheetError !== null
      ? "The model could not be shown"
      : phase === "running"
          ? "Scanning the model — every formula, read in a copy"
          : "Loading the model";
  const started = phase === "running" || steps.length > 0 || view !== null;
  const status =
    phase === "running"
      ? { label: "Checking…", tone: "blue" as const }
      : phase === "paused"
        ? view && !view.patch
          ? { label: "No fix to approve", tone: "neutral" as const }
          : { label: "Review needed", tone: "amber" as const }
        : phase === "interrupted"
          ? { label: "Interrupted", tone: "neutral" as const }
          : phase === "done"
          ? { label: "Done", tone: "green" as const }
          : { label: "Stopped", tone: "neutral" as const };

  return (
    <div className={styles.page}>
      <header className={styles.nav}>
        <button type="button" className={styles.brand} onClick={reset}>
          <Logo />
          Model X-Ray
        </button>
        <p className={styles.powered}>Powered by NVIDIA Nemotron on Nebius Token Factory</p>
      </header>

      {!started && <Hero demos={demos} error={error} onStart={start} onError={setError} />}

      {started && (
        <main className={styles.case}>
          <div className={styles.topbar}>
            <div>
              <p className={styles.eyebrow}>Model check</p>
              <h1 className={styles.title}>
                {modelName}
                <Chip tone={status.tone} pulse={phase === "running"}>
                  {status.label}
                </Chip>
              </h1>
            </div>
            <div className={styles.topbarActions}>
              {phase === "interrupted" && check && (
                <Button variant="primary" onClick={() => start(check.spreadsheetId, check.question, check.name)}>
                  Run again
                </Button>
              )}
              <Button variant="ghost" disabled={phase === "running"} onClick={reset}>
                Check another model
              </Button>
            </div>
          </div>
          <Boundary onReset={reset}>
            {(error || sheetError) && (
              <div className={styles.alertRow}>
                <Alert>{error ?? sheetError}</Alert>
              </div>
            )}
            <div className={styles.body}>
              <MemoRail steps={rail} />
              <div className={styles.stageArea}>
                {sheet && view && marks ? (
                  <MemoStage view={view} sheet={sheet} marks={marks} highlight={highlight} running={phase === "running"} />
                ) : (
                  <SheetSkeleton note={stageNote} />
                )}
              </div>
            </div>
            {view && <MemoFacts view={view} onDecide={resume} onEvidence={showEvidence} />}
          </Boundary>
        </main>
      )}

      <footer className={styles.footer}>
        <span className={styles.footerBrand}>
          Model X-Ray
          {view && view.run_log && view.run_log.length > 0 && (
            <span className={styles.footerMeta}>
              {" "}
              · {view.run_log.length} Nemotron calls · {Math.round(view.run_log.reduce((sum, row) => sum + (row.input_tokens ?? 0) + (row.output_tokens ?? 0), 0) / 1000)}k tokens
            </span>
          )}
        </span>
        <span className={styles.footerNote}>Runs in your session. Fixes are always written to a copy.</span>
      </footer>
    </div>
  );
}

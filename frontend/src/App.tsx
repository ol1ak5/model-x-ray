import { memo, useCallback, useEffect, useMemo, useState } from "react";

import {
  ApiError,
  type CellChoicePause,
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
import Button from "./components/Button";
import CellChoice from "./components/CellChoice";
import Chip from "./components/Chip";
import DetailTabs, { type Tab } from "./components/DetailTabs";
import Hero from "./components/Hero";
import Logo from "./components/Logo";
import Outcome from "./components/Outcome";
import Progress, { type Step } from "./components/Progress";
import Report from "./components/Report";
import Review from "./components/Review";
import SheetGrid, { type Marks } from "./components/SheetGrid";
import { GLOW, VARIANT } from "./theme";
import styles from "./App.module.css";

type Phase = "idle" | "running" | "paused" | "done";

const UNREACHABLE = "The Model X-Ray service could not be reached. Please try again.";

function marksOf(view: InvestigationView): Marks {
  const hypotheses = view.hypotheses ?? [];
  const suspicious = new Set(hypotheses.filter((h) => h.status === "open").map((h) => h.cell));
  const walk = (node: InvestigationView["causal_tree"]) => {
    if (!node) return;
    if (node.suspicious) suspicious.add(node.cell);
    node.children.forEach(walk);
  };
  walk(view.causal_tree);
  return {
    suspicious,
    confirmed: new Set(hypotheses.filter((h) => h.status === "confirmed").map((h) => h.cell)),
    target: view.target ? `${view.target.sheet}!${view.target.cell}` : null,
    after: view.verifications?.at(-1)?.after ?? {},
    patch: view.patch,
  };
}

const MemoSheetGrid = memo(SheetGrid);
const MemoReport = memo(Report);
const MemoDetailTabs = memo(DetailTabs);
const MemoProgress = memo(Progress);
const MemoCellChoice = memo(CellChoice);
const MemoReview = memo(Review);
const MemoOutcome = memo(Outcome);

export default function App() {
  const [demos, setDemos] = useState<Spreadsheet[]>([]);
  const [phase, setPhase] = useState<Phase>("idle");
  const [steps, setSteps] = useState<Step[]>([]);
  const [view, setView] = useState<InvestigationView | null>(null);
  const [sheet, setSheet] = useState<SheetWindow | null>(null);
  const [modelName, setModelName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("tree");

  const showEvidence = useCallback((id: string) => {
    setTab("evidence");
    window.setTimeout(() => {
      const record = document.getElementById(id);
      record?.scrollIntoView?.({ behavior: "smooth", block: "center" });
    }, 50);
  }, []);

  useEffect(() => {
    listSpreadsheets()
      .then(setDemos)
      .catch((reason: unknown) => setError(reason instanceof ApiError ? reason.message : UNREACHABLE));
  }, []);

  const targetKey = view?.target ? `${view.id}:${view.target.sheet}` : null;
  useEffect(() => {
    if (!view || !targetKey) return;
    getSheet(view.id)
      .then(setSheet)
      .catch(() => setSheet(null));
  }, [targetKey]);

  function onEvent(event: ProgressEvent) {
    if (event.kind === "step") setSteps((current) => [...current, { step: event.step, label: event.label }]);
    if (event.kind === "view") {
      setView(event.view);
      setPhase(event.view.status === "done" ? "done" : "paused");
    }
    if (event.kind === "error") {
      setError(event.detail);
      setPhase("idle");
    }
  }

  async function run(work: Promise<void>) {
    try {
      await work;
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : UNREACHABLE);
      setPhase("idle");
    }
  }

  const start = useCallback((spreadsheetId: string, question: string, name: string) => {
    setSteps([]);
    setView(null);
    setSheet(null);
    setError(null);
    setModelName(name);
    setPhase("running");
    void run(startInvestigation(spreadsheetId, question, onEvent));
  }, []);

  const resume = useCallback(
    (answer: { ref: string } | Decision) => {
      if (!view) return;
      setError(null);
      setPhase("running");
      void run(resumeInvestigation(view.id, answer, onEvent));
    },
    [view],
  );

  const reset = useCallback(() => {
    setSteps([]);
    setView(null);
    setSheet(null);
    setError(null);
    setPhase("idle");
  }, []);

  const marks = useMemo(() => (view ? marksOf(view) : null), [view]);

  const started = phase === "running" || steps.length > 0 || view !== null;
  const choice = view?.status === "needs_cell" ? (view.pause as CellChoicePause) : null;
  const status =
    phase === "running"
      ? { label: "Checking…", tone: "blue" as const }
      : phase === "paused" && view?.status === "needs_cell"
        ? { label: "Needs your input", tone: "amber" as const }
        : phase === "paused"
          ? { label: "Review needed", tone: "amber" as const }
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
        <main className={styles.workspace}>
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
            <Button variant="ghost" disabled={phase === "running"} onClick={reset}>
              Check another model
            </Button>
          </div>
          <div className={styles.columns}>
            <div className={styles.main}>
              {view?.report && <MemoReport view={view} onEvidence={showEvidence} />}
              {sheet && view && marks ? (
                <MemoSheetGrid key={view.id + sheet.sheet} sheet={sheet} marks={marks} title="Sheet" light={GLOW && VARIANT === "dark"} />
              ) : (
                phase === "running" && (
                  <div className={styles.scanning} aria-hidden="true">
                    <p className={styles.scanningTitle}>Scanning your model…</p>
                    {Array.from({ length: 7 }, (_, index) => (
                      <span key={index} className={styles.skeletonRow} style={{ animationDelay: `${index * 0.12}s` }} />
                    ))}
                  </div>
                )
              )}
              {view && <MemoDetailTabs view={view} tab={tab} onTab={setTab} />}
            </div>
            <aside className={styles.side}>
              <MemoProgress steps={steps} running={phase === "running"} />
              {error && <Alert>{error}</Alert>}
              {choice && phase === "paused" && <MemoCellChoice pause={choice} onChoose={(ref) => resume({ ref })} />}
              {view?.status === "needs_review" && phase === "paused" && <MemoReview patch={view.patch} onDecide={resume} />}
              {phase === "done" && view && <MemoOutcome view={view} />}
            </aside>
          </div>
        </main>
      )}
    </div>
  );
}

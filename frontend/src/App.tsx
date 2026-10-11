import { useEffect, useState } from "react";

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
import CellChoice from "./components/CellChoice";
import DetailTabs, { type Tab } from "./components/DetailTabs";
import Hero from "./components/Hero";
import Logo from "./components/Logo";
import Outcome from "./components/Outcome";
import Progress, { type Step } from "./components/Progress";
import Report from "./components/Report";
import Review from "./components/Review";
import SheetGrid, { type Marks } from "./components/SheetGrid";

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

export default function App() {
  const [demos, setDemos] = useState<Spreadsheet[]>([]);
  const [phase, setPhase] = useState<Phase>("idle");
  const [steps, setSteps] = useState<Step[]>([]);
  const [view, setView] = useState<InvestigationView | null>(null);
  const [sheet, setSheet] = useState<SheetWindow | null>(null);
  const [modelName, setModelName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("tree");

  function showEvidence(id: string) {
    setTab("evidence");
    window.setTimeout(() => {
      const record = document.getElementById(id);
      record?.scrollIntoView?.({ behavior: "smooth", block: "center" });
      record?.focus();
    }, 50);
  }

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

  function start(spreadsheetId: string, question: string, name: string) {
    setSteps([]);
    setView(null);
    setSheet(null);
    setError(null);
    setModelName(name);
    setPhase("running");
    void run(startInvestigation(spreadsheetId, question, onEvent));
  }

  function resume(answer: { ref: string } | Decision) {
    if (!view) return;
    setError(null);
    setPhase("running");
    void run(resumeInvestigation(view.id, answer, onEvent));
  }

  function reset() {
    setSteps([]);
    setView(null);
    setSheet(null);
    setError(null);
    setPhase("idle");
  }

  const started = phase === "running" || steps.length > 0 || view !== null;
  const choice = view?.status === "needs_cell" ? (view.pause as CellChoicePause) : null;

  return (
    <div className="page">
      <header className="nav">
        <button type="button" className="brand" onClick={reset}>
          <Logo />
          Model X-Ray
        </button>
        <p className="powered">Powered by NVIDIA Nemotron on Nebius Token Factory</p>
      </header>

      {!started && <Hero demos={demos} error={error} onStart={start} onError={setError} />}

      {started && (
        <main className="workspace">
          <div className="topbar">
            <div>
              <p className="eyebrow">Model check</p>
              <h1 className="ws-title">
                {modelName}
                <span className={`status ${phase}`}>{phase === "running" ? "Checking…" : phase === "paused" && view?.status === "needs_cell" ? "Needs your input" : phase === "paused" ? "Review needed" : phase === "done" ? "Done" : "Stopped"}</span>
              </h1>
            </div>
            <button type="button" className="secondary" onClick={reset} disabled={phase === "running"}>
              Check another model
            </button>
          </div>
          <div className="ws-main">
            <div className="ws-left">
              {view?.report && <Report view={view} onEvidence={showEvidence} />}
              {sheet && view ? (
                <SheetGrid key={view.id + sheet.sheet} sheet={sheet} marks={marksOf(view)} title="Sheet" />
              ) : (
                phase === "running" && (
                  <div className="card scanning" aria-hidden="true">
                    <p className="scanning-title">Scanning your model…</p>
                    {Array.from({ length: 7 }, (_, index) => (
                      <span key={index} className="skeleton-row" style={{ animationDelay: `${index * 0.12}s` }} />
                    ))}
                  </div>
                )
              )}
              {view && <DetailTabs view={view} tab={tab} onTab={setTab} />}
            </div>
            <aside className="ws-side">
              <Progress steps={steps} running={phase === "running"} />
              {error && (
                <p className="alert" role="alert">
                  {error}
                </p>
              )}
              {choice && phase === "paused" && <CellChoice pause={choice} onChoose={(ref) => resume({ ref })} />}
              {view?.status === "needs_review" && phase === "paused" && <Review patch={view.patch} onDecide={resume} />}
              {phase === "done" && view && <Outcome view={view} />}
            </aside>
          </div>
        </main>
      )}
    </div>
  );
}

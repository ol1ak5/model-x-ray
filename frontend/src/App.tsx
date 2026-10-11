import { useEffect, useState } from "react";

import {
  ApiError,
  type CellChoicePause,
  type Decision,
  type InvestigationView,
  type ProgressEvent,
  type Spreadsheet,
  listSpreadsheets,
  resumeInvestigation,
  startInvestigation,
} from "./api";
import CauseTree from "./components/CauseTree";
import CellChoice from "./components/CellChoice";
import EvidencePanel from "./components/EvidencePanel";
import HypothesisBoard from "./components/HypothesisBoard";
import Outcome from "./components/Outcome";
import Progress, { type Step } from "./components/Progress";
import QuestionForm from "./components/QuestionForm";
import Report from "./components/Report";
import Review from "./components/Review";

type Phase = "idle" | "running" | "paused" | "done";

export default function App() {
  const [spreadsheets, setSpreadsheets] = useState<Spreadsheet[]>([]);
  const [phase, setPhase] = useState<Phase>("idle");
  const [steps, setSteps] = useState<Step[]>([]);
  const [view, setView] = useState<InvestigationView | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listSpreadsheets()
      .then(setSpreadsheets)
      .catch((reason: unknown) => setError(reason instanceof ApiError ? reason.message : "The Model X-Ray service could not be reached. Please try again."));
  }, []);

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
      setError(reason instanceof ApiError ? reason.message : "The Model X-Ray service could not be reached. Please try again.");
      setPhase("idle");
    }
  }

  function start(spreadsheetId: string, question: string) {
    setSteps([]);
    setView(null);
    setError(null);
    setPhase("running");
    void run(startInvestigation(spreadsheetId, question, onEvent));
  }

  function resume(answer: { ref: string } | Decision) {
    if (!view) return;
    setError(null);
    setPhase("running");
    void run(resumeInvestigation(view.id, answer, onEvent));
  }

  const choice = view?.status === "needs_cell" ? (view.pause as CellChoicePause) : null;
  const latestAfter = view?.verifications?.at(-1)?.after ?? {};

  return (
    <div className="page">
      <header className="masthead">
        <div className="brand">
          <span className="logo" aria-hidden="true">X</span>
          <div>
            <h1>Model X-Ray</h1>
            <p className="tagline">The debugger for financial models. Ask why a number changed; get the cause, the proof and a fix you approve.</p>
          </div>
        </div>
        <p className="powered">NVIDIA Nemotron on Nebius Token Factory</p>
      </header>

      <main className="layout">
        <aside className="controls">
          <QuestionForm spreadsheets={spreadsheets} busy={phase === "running"} onStart={start} />
          {error && (
            <p className="alert" role="alert">
              {error}
            </p>
          )}
          {steps.length > 0 && <Progress steps={steps} running={phase === "running"} />}
          {choice && phase === "paused" && <CellChoice pause={choice} onChoose={(ref) => resume({ ref })} />}
          {view?.status === "needs_review" && phase === "paused" && <Review patch={view.patch} onDecide={resume} />}
          {phase === "done" && view && <Outcome view={view} />}
        </aside>

        <section className="results" aria-label="Investigation">
          {!view && phase !== "running" && (
            <div className="empty">
              <h2>How it works</h2>
              <ol>
                <li>Pick a model and ask about a number that surprised you.</li>
                <li>The agent traces the formulas, tests suspects on a copy and lets a second model try to prove the fix wrong.</li>
                <li>You read the evidence and approve, edit or reject. The original file is never changed.</li>
              </ol>
            </div>
          )}
          {view?.report && <Report text={view.report} target={view.target} />}
          {view?.hypotheses && view.hypotheses.length > 0 && <HypothesisBoard hypotheses={view.hypotheses} />}
          {view?.causal_tree && <CauseTree root={view.causal_tree} after={latestAfter} />}
          {view?.evidence && view.evidence.length > 0 && <EvidencePanel evidence={view.evidence} />}
        </section>
      </main>
    </div>
  );
}

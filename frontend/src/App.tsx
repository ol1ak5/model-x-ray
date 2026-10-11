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
import CauseTree from "./components/CauseTree";
import CellChoice from "./components/CellChoice";
import EvidencePanel from "./components/EvidencePanel";
import Hero from "./components/Hero";
import Logo from "./components/Logo";
import HypothesisBoard from "./components/HypothesisBoard";
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
            <p>
              Checking <strong>{modelName}</strong>
            </p>
            <button type="button" className="secondary" onClick={reset} disabled={phase === "running"}>
              Check another model
            </button>
          </div>
          <div className="ws-main">
            <div className="ws-left">
              {sheet && view && <SheetGrid key={view.id + sheet.sheet} sheet={sheet} marks={marksOf(view)} title="Sheet" />}
              {view?.report && <Report text={view.report} target={view.target} />}
              {view?.hypotheses && view.hypotheses.length > 0 && <HypothesisBoard hypotheses={view.hypotheses} />}
              {view?.causal_tree && <CauseTree root={view.causal_tree} after={view.verifications?.at(-1)?.after ?? {}} />}
              {view?.evidence && view.evidence.length > 0 && <EvidencePanel evidence={view.evidence} />}
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

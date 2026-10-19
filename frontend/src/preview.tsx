import { StrictMode, type ReactNode } from "react";
import { createRoot } from "react-dom/client";

import "./styles/tokens.css";
import "./styles/base.css";
import { THEME, VARIANT } from "./theme";
import FactsBar from "./components/FactsBar";
import Stage from "./components/Stage";
import CellChoice from "./components/CellChoice";
import Alert from "./components/Alert";
import Button from "./components/Button";
import Chip from "./components/Chip";
import { SHEET, REVIEW, CELL_CHOICE, APPROVED, REJECTED, RUNNING, STEPS } from "./test/fakeApi";
import StepRail from "./components/StepRail";
import { railOf } from "./steps";
import styles from "./preview.module.css";

const ALL = STEPS.map(([step, label]) => ({ step, label }));
const MID = ALL.slice(0, 5);

const MARKS = {
  suspicious: new Set(["P&L!G5"]),
  confirmed: new Set(["P&L!G5"]),
  traced: new Set(["P&L!G6", "P&L!G4", "P&L!G5"]),
  target: "P&L!G6",
  after: { "P&L!G6": 90.24 },
  patch: REVIEW.patch,
};

function Section({ label, children }: { label: string; children: ReactNode }) {
  return (
    <section className={styles.section}>
      <p className={`eyebrow ${styles.label}`}>{label}</p>
      <div className={styles.body}>{children}</div>
    </section>
  );
}

export default function Preview() {
  const pause = CELL_CHOICE.pause && "question" in CELL_CHOICE.pause ? CELL_CHOICE.pause : null;

  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <h1 className={styles.title}>Component preview</h1>
        <p className="muted">Every workspace state — dev-only, never part of the production build.</p>
      </header>

      <Section label="stage — traced, reviewed">
        <Stage view={REVIEW} sheet={SHEET} marks={MARKS} highlight={null} running={false} />
      </Section>

      <Section label="steps — settled">
        <StepRail steps={railOf(REVIEW, ALL, false)} />
      </Section>

      <Section label="steps — running">
        <StepRail steps={railOf(RUNNING, MID, true)} />
      </Section>

      <Section label="steps — approved">
        <StepRail steps={railOf(APPROVED, ALL, false)} />
      </Section>

      <Section label="facts — review">
        <FactsBar view={REVIEW} onDecide={() => {}} onEvidence={() => {}} />
      </Section>

      <Section label="stage — running">
        <Stage view={{ ...REVIEW, patch: null }} sheet={SHEET} marks={{ ...MARKS, patch: null }} highlight={null} running />
      </Section>

      <Section label="facts — running">
        <FactsBar view={RUNNING} onDecide={() => {}} onEvidence={() => {}} />
      </Section>

      <Section label="facts — approved">
        <FactsBar view={APPROVED} onDecide={() => {}} onEvidence={() => {}} />
      </Section>

      <Section label="facts — rejected">
        <FactsBar view={REJECTED} onDecide={() => {}} onEvidence={() => {}} />
      </Section>

      <Section label="cell choice — ambiguous question">
        {pause && <CellChoice pause={pause} onChoose={() => {}} />}
      </Section>

      <Section label="primitives">
        <div className={styles.row}>
          <Button variant="primary">Upload your model</Button>
          <Button variant="secondary">See it in action</Button>
          <Button variant="ghost">Reset</Button>
          <Button variant="danger">Reject</Button>
        </div>
        <div className={styles.row}>
          <Chip tone="neutral">needs review</Chip>
          <Chip tone="green">confirmed</Chip>
          <Chip tone="red">rejected</Chip>
          <Chip tone="amber" pulse>
            streaming
          </Chip>
        </div>
        <Alert>The Model X-Ray service could not be reached.</Alert>
      </Section>
    </main>
  );
}

const root = document.getElementById("root");
if (root) {
  document.documentElement.dataset.theme = THEME;
  document.documentElement.dataset.variant = VARIANT;
  createRoot(root).render(
    <StrictMode>
      <Preview />
    </StrictMode>,
  );
}

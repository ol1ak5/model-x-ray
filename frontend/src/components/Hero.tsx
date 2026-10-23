import type { CSSProperties } from "react";
import type { SheetWindow, Spreadsheet } from "../api";
import { GLOW } from "../theme";
import Alert from "./Alert";
import QuestionForm from "./QuestionForm";
import SheetGrid from "./SheetGrid";
import Waves from "./Waves";
import styles from "./Hero.module.css";

const SAMPLE: SheetWindow = {
  sheet: "P&L",
  header_row: 3,
  columns: [
    { letter: "F", header: "2025A" },
    { letter: "G", header: "2026E" },
    { letter: "H", header: "2027E" },
  ],
  rows: [
    ["Revenue", 4, [185.2, 200.0, 216.0]],
    ["COGS", 5, [-101.9, -110.0, -118.8]],
    ["Gross profit", 6, [83.3, 90.0, -25.0]],
    ["Operating expenses", 7, [-47.6, -50.0, -52.5]],
    ["EBITDA", 8, [35.7, 40.0, -77.5]],
  ].map(([label, row, values]) => ({
    row: row as number,
    label: label as string,
    cells: (values as number[]).map((value, index) => ({ ref: `P&L!${"FGH"[index]}${row}`, value, formula: null })),
  })),
};

const WIDE_SAMPLE: SheetWindow = {
  ...SAMPLE,
  columns: [...SAMPLE.columns, { letter: "I", header: "2028E" }],
  rows: SAMPLE.rows.map((row, index) => ({
    ...row,
    cells: [
      ...row.cells.map((cell) => ({ ...cell, value: { "P&L!G6": -25.0, "P&L!G8": -75.0, "P&L!H6": 97.2, "P&L!H8": 44.7 }[cell.ref] ?? cell.value })),
      { ref: `P&L!I${row.row}`, value: [233.3, -128.3, 105.0, -55.1, 49.9][index], formula: null },
    ],
  })),
};

const STEPS = [
  { name: "Scan", text: "Every formula, typed value and input" },
  { name: "Anomaly", text: "P&L!H6 breaks the pattern of its row" },
  { name: "Trace", text: "EBITDA 2027E absorbs the bad −25.0" },
  { name: "Fix & verify", text: "=H4+H5 applied · EBITDA recalculates to 44.7" },
];

export default function Hero({ demos, error, onStart, onError }: { demos: Spreadsheet[]; error: string | null; onStart: (id: string, question: string, name: string) => void; onError: (message: string) => void }) {
  const demoShift = import.meta.env.DEV ? new URLSearchParams(window.location.search).get("demo-t") : null;
  const shiftStyle = demoShift ? ({ "--demo-shift": `-${demoShift}s` } as CSSProperties) : undefined;
  return (
    <div className={styles.home}>
      <section className={!GLOW ? `${styles.hero} ${styles.demo}` : styles.hero} style={shiftStyle}>
        <div className={styles.lead}>
          <p className={styles.eyebrow}>
            <span className={styles.spark} aria-hidden="true">✦</span>
            The financial model debugger · NVIDIA Nemotron on Nebius
          </p>
          <h1 className={styles.headline}>
            <span className={styles.hl1}>Every formula, checked.{"\u00A0"}</span>
            <span className={styles.accent}>Under the X-Ray.</span>
          </h1>
          <p className={styles.sub}>An AI agent that reads every formula like an analyst, recalculates every number like Excel, and proves each fix before you approve it.</p>
          <p className={styles.try}>
            <span className={`${styles.q} ${styles.q1}`}>Why did 2027 EBITDA drop to −77.5?</span>
            <span className={`${styles.q} ${styles.q2}`}>Is the H6 gross profit figure reliable?</span>
            <span className={`${styles.q} ${styles.q3}`}>What breaks if COGS moves 5%?</span>
          </p>
          <div className={styles.actions}>
            <QuestionForm demos={demos} onStart={onStart} onError={onError} />
            {error && <Alert>{error}</Alert>}
          </div>
        </div>
        <div className={styles.stage}>
          <div className={styles.framepos}>
            <div className={styles.frame}>
              <span className={styles.scan} aria-hidden="true" />
              <span className={styles.chip} aria-hidden="true">
                EBITDA 44.7 ✓
              </span>
              {GLOW && (
                <>
                  <span className={styles.glassBack} />
                  <span className={styles.glassMid} />
                  <span className={styles.circuitLeft} />
                  <span className={styles.circuitTop} />
                  <span className={styles.circuitRight} />
                </>
              )}
              <SheetGrid sheet={GLOW ? WIDE_SAMPLE : SAMPLE} title="Example sheet" light marks={{ suspicious: new Set(), confirmed: new Set(GLOW ? ["P&L!G6"] : []), traced: new Set<string>(), target: null, after: {}, patch: null }} />
            </div>
          </div>
          <ol className={styles.steps}>
            {STEPS.map((step, index) => (
              <li key={step.name} className={`${styles.step} ${styles[`step${index + 1}`]}`}>
                <span className={styles.dot} />
                <div className={styles.stepBody}>
                  <p className={styles.stepName}>{step.name}</p>
                  <p className={styles.stepText}>{step.text}</p>
                </div>
              </li>
            ))}
          </ol>
          <p className={styles.proof}>
            <strong>98%</strong> of planted errors fixed · <strong>0</strong> false alarms on deliberate values · every fix recalculated
          </p>
        </div>
      </section>
      {GLOW && <Waves />}
    </div>
  );
}

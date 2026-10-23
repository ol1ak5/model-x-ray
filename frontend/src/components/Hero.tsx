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

export default function Hero({ demos, error, onStart, onError }: { demos: Spreadsheet[]; error: string | null; onStart: (id: string, question: string, name: string) => void; onError: (message: string) => void }) {
  const demoShift = import.meta.env.DEV ? new URLSearchParams(window.location.search).get("demo-t") : null;
  const shiftStyle = demoShift ? ({ "--demo-shift": `-${demoShift}s` } as CSSProperties) : undefined;
  return (
    <div className={styles.home}>
      <section className={!GLOW ? `${styles.hero} ${styles.demo}` : styles.hero} style={shiftStyle}>
        <div className={styles.lead}>
          <h1 className={styles.headline}>
            <span className={styles.hl1}>Your Excel models.{"\u00A0"}</span>
            <span className={styles.hl2}>
              Under the <span className={styles.accent}>X-Ray.</span>
            </span>
          </h1>
          <p className={styles.sub}>An AI agent that reads your model the way a financial analyst checks it.</p>
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
              <div className={styles.titlebar} aria-hidden="true">
                <span className={styles.excel}>X</span>
                <span className={styles.file}>Deal model.xlsx</span>
                <span className={styles.saved}>Saved</span>
                <span className={styles.controls}>
                  <i />
                  <i />
                  <i />
                </span>
              </div>
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
              <SheetGrid
                sheet={GLOW ? WIDE_SAMPLE : SAMPLE}
                title="Example sheet"
                light
                formula={
                  <>
                    <span className={styles.nameBox}>H6</span>
                    <span className={styles.fx}>fx</span>
                    <span className={styles.fxValue}>
                      <span className={styles.fxTyped}>-25.0</span>
                      <span className={styles.fxFixed}>=H4+H5</span>
                    </span>
                  </>
                }
                marks={{ suspicious: new Set(), confirmed: new Set(GLOW ? ["P&L!G6"] : []), traced: new Set<string>(), target: null, after: {}, patch: null }}
              />
              <div className={styles.tabs} aria-hidden="true">
                <span className={styles.activeTab}>P&amp;L</span>
                <span>Assumptions</span>
                <span>Summary</span>
                <span className={styles.plus}>+</span>
              </div>
              <div className={styles.status} aria-hidden="true">
                <span>Ready</span>
                <span>100%</span>
              </div>
            </div>
          </div>
        </div>
      </section>
      {GLOW && <Waves />}
    </div>
  );
}

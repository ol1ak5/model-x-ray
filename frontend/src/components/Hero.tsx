import type { SheetWindow, Spreadsheet } from "../api";
import { GLOW } from "../theme";
import AnalysisSummary from "./AnalysisSummary";
import Icon from "./Icon";
import Waves from "./Waves";
import QuestionForm from "./QuestionForm";
import SheetGrid from "./SheetGrid";

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

const STEPS = [
  { icon: "scan" as const, title: "Scans every formula", text: "Finds hardcodes and broken references, even when several errors are mixed." },
  { icon: "trace" as const, title: "Traces the cause", text: "Follows each number back to the cell that moved it." },
  { icon: "shield" as const, title: "Proves the fix", text: "Every detected error is corrected on a copy and verified before you see it." },
  { icon: "user" as const, title: "You decide", text: "Approve, edit or reject the changes. Your original file is never changed." },
];

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
  return (
    <div className="home">
      <section className="hero">
        <div className="hero-copy">
          <p className="eyebrow">The financial model debugger</p>
          <h1>
            Your Excel models{" "}
            <br />
            under the <span className="green">X-Ray.</span>
          </h1>
          <p className="lead">Model X-Ray checks every formula in your model, finds the cells that break the logic, proves each fix on a copy and lets you approve it before anything changes.</p>
          <QuestionForm demos={demos} onStart={onStart} onError={onError} />
          {error && (
            <p className="alert" role="alert">
              {error}
            </p>
          )}
        </div>
        <div className="hero-visual" aria-hidden="true">
          <SheetGrid sheet={GLOW ? WIDE_SAMPLE : SAMPLE} title="Example sheet" showFormulaBar={false} marks={{ suspicious: new Set(), confirmed: new Set([GLOW ? "P&L!G6" : "P&L!H6"]), target: null, after: {}, patch: null }} />
          {GLOW ? (
            <AnalysisSummary />
          ) : (
            <div className="issue-card">
              <span className="issue-icon">!</span>
              <div>
                <p className="issue-head">Formula issue detected in cell H6</p>
                <p className="issue-text">Expected =H4+H5 but found the typed value -25.0</p>
              </div>
              <span className="issue-link">View details →</span>
            </div>
          )}
        </div>
      </section>
      {GLOW && <Waves />}

      <section className="steps" aria-labelledby="steps-title">
        <p className="eyebrow">How it works</p>
        <h2 id="steps-title" className="section-title">
          Go beyond the numbers. <span className="green">See the logic.</span>
        </h2>
        <ol className="step-list">
          {STEPS.map((step, index) => (
            <li key={step.title} className="step">
              <span className="step-number">{index + 1}</span>
              <span className="feature-icon"><Icon name={step.icon} /></span>
              <h3 className="step-title">{step.title}</h3>
              <p>{step.text}</p>
            </li>
          ))}
        </ol>
      </section>
    </div>
  );
}

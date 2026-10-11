import type { SheetWindow, Spreadsheet } from "../api";
import Icon from "./Icon";
import QuestionForm from "./QuestionForm";
import SheetGrid from "./SheetGrid";

const SAMPLE: SheetWindow = {
  sheet: "P&L",
  columns: [
    { letter: "F", header: "2025A" },
    { letter: "G", header: "2026E" },
    { letter: "H", header: "2027E" },
  ],
  rows: [
    ["Revenue", 4, [185.2, 200.0, 216.0]],
    ["COGS", 5, [-101.9, -110.0, -118.8]],
    ["Gross profit", 6, [83.3, 90.0, 97.2]],
    ["Operating expenses", 7, [-47.6, -50.0, -45.2]],
    ["EBITDA", 8, [35.7, 40.0, 52.0]],
  ].map(([label, row, values]) => ({
    row: row as number,
    label: label as string,
    cells: (values as number[]).map((value, index) => ({ ref: `P&L!${"FGH"[index]}${row}`, value, formula: null })),
  })),
};

const BENEFITS = [
  { icon: "grid" as const, title: "Works with your Excel files", text: "Upload an .xlsx. No add-ins, no extra tools." },
  { icon: "spark" as const, title: "AI-powered analysis", text: "NVIDIA Nemotron agents investigate like an analyst." },
  { icon: "file" as const, title: "Evidence for every finding", text: "Each claim links to the cells and numbers behind it." },
  { icon: "chart" as const, title: "Built for finance", text: "For M&A, FP&A and deal teams who own the model." },
];

const STEPS = [
  { icon: "scan" as const, title: "Scans every formula", text: "Finds hardcodes and broken references, even when several errors are mixed." },
  { icon: "trace" as const, title: "Traces the cause", text: "Follows each number back to the cell that moved it." },
  { icon: "shield" as const, title: "Proves the fix", text: "Tests the fix on a copy; a second model tries to prove it wrong." },
  { icon: "user" as const, title: "You decide", text: "Approve, edit or reject. Your original file is never changed." },
];

export default function Hero({ demos, error, onStart, onError }: { demos: Spreadsheet[]; error: string | null; onStart: (id: string, question: string, name: string) => void; onError: (message: string) => void }) {
  return (
    <>
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
          <SheetGrid sheet={SAMPLE} title="Example sheet" showFormulaBar={false} marks={{ suspicious: new Set(), confirmed: new Set(["P&L!H7"]), target: null, after: {}, patch: null }} />
          <div className="issue-card">
            <span className="issue-icon">!</span>
            <div>
              <p className="issue-head">Formula issue detected in cell H7</p>
              <p className="issue-text">Expected =G7*(1+$C$7) but found the typed value -45.2</p>
            </div>
            <span className="issue-link">View details →</span>
          </div>
        </div>
      </section>

      <section className="benefits" aria-label="Why Model X-Ray">
        {BENEFITS.map((item) => (
          <div key={item.title} className="benefit">
            <span className="feature-icon"><Icon name={item.icon} /></span>
            <div>
              <h2>{item.title}</h2>
              <p>{item.text}</p>
            </div>
          </div>
        ))}
      </section>

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
    </>
  );
}

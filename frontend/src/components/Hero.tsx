import type { Spreadsheet, SheetWindow } from "../api";
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
    ["Opex", 7, [-47.6, -50.0, -45.2]],
    ["EBITDA", 8, [35.7, 40.0, 52.0]],
  ].map(([label, row, values]) => ({
    row: row as number,
    label: label as string,
    cells: (values as number[]).map((value, index) => ({ ref: `P&L!${"FGH"[index]}${row}`, value, formula: null })),
  })),
};

const FEATURES = [
  { icon: "scan" as const, title: "Scans every formula", text: "Finds hardcodes and broken references, even when several errors are mixed." },
  { icon: "trace" as const, title: "Traces the cause", text: "Follows each number back to the cell that moved it." },
  { icon: "shield" as const, title: "Proves the fix", text: "Tests the fix on a copy; a second model tries to prove it wrong." },
  { icon: "user" as const, title: "You decide", text: "Approve, edit or reject. Your original file is never changed." },
];

export default function Hero({ demos, busy, error, onStart, onError }: { demos: Spreadsheet[]; busy: boolean; error: string | null; onStart: (id: string, question: string, name: string) => void; onError: (message: string) => void }) {
  return (
    <>
      <section className="hero">
        <div className="hero-copy">
          <p className="eyebrow">Financial model debugger</p>
          <h1>
            Your Excel models.
            <br />
            Under the <span className="green">X-Ray.</span>
          </h1>
          <p className="lead">Model X-Ray checks every formula in your model, finds the cells that break the logic, proves each fix on a copy and lets you approve it before anything changes.</p>
          <QuestionForm demos={demos} busy={busy} onStart={onStart} onError={onError} />
          {error && (
            <p className="alert" role="alert">
              {error}
            </p>
          )}
        </div>
        <div className="hero-visual" aria-hidden="true">
          <SheetGrid sheet={SAMPLE} title="Example sheet" marks={{ suspicious: new Set(), confirmed: new Set(["P&L!H7"]), target: "P&L!H8", after: { "P&L!H7": -52.5, "P&L!H8": 44.7 }, patch: { cell: "P&L!H7", old_formula: "-45.2", new_formula: "=G7*(1+Assumptions!$C$7)" } }} />
          <div className="issues-float">
            <p className="issues-title">Issues detected</p>
            <p className="issue"><span className="dot red" />Hardcoded value <span className="muted">Opex 2027E</span></p>
            <p className="issue"><span className="dot amber" />Reference mismatch <span className="muted">COGS 2026E</span></p>
            <p className="issue"><span className="dot green" />Fix proven <span className="muted">EBITDA 52.0 → 44.7</span></p>
          </div>
        </div>
      </section>
      <section className="features" aria-label="What Model X-Ray does">
        {FEATURES.map((feature) => (
          <div key={feature.title} className="feature">
            <span className="feature-icon"><Icon name={feature.icon} /></span>
            <div>
              <h2>{feature.title}</h2>
              <p>{feature.text}</p>
            </div>
          </div>
        ))}
      </section>
    </>
  );
}

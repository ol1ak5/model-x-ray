import { useEffect, useState } from "react";

const ROWS: [number, string, string, string, string, string][] = [
  [2, "Revenue", "185.2", "200.0", "216.0", "D2"],
  [3, "COGS", "(101.9)", "(110.0)", "(118.8)", "D3"],
  [4, "Gross profit", "83.3", "90.0", "(25.0)", "D4"],
  [5, "Operating expenses", "(47.6)", "(50.0)", "(52.5)", "D5"],
  [6, "EBITDA", "35.7", "40.0", "(77.5)", "D6"],
];

const FRAMES = [280, 280, 280, 280, 280, 1500, 1500, 500, 1200, 700, 4200];

type Look = { scan: number | null; bad: string[]; src: string[]; good: string[]; d4: string; d6: string; name: string; formula: string; tone: "" | "red" | "green"; status: string; busy: boolean; stage: number };

function lookOf(frame: number): Look {
  const base: Look = { scan: null, bad: [], src: [], good: [], d4: "(25.0)", d6: "(77.5)", name: "D4", formula: "-25.0", tone: "", status: "Scanning formulas", busy: true, stage: 0 };
  if (frame < 5) return { ...base, scan: frame };
  if (frame === 5) return { ...base, bad: ["D4"], tone: "red", status: "D4 is a typed value", stage: 1 };
  if (frame === 6) return { ...base, bad: ["D4", "D6"], src: ["D2", "D3"], tone: "red", status: "Tracing EBITDA", stage: 2 };
  if (frame === 7) return { ...base, bad: ["D6"], formula: "=D2+D3", tone: "green", status: "Tracing EBITDA", stage: 2 };
  if (frame === 8) return { ...base, bad: ["D6"], good: ["D4"], d4: "97.2", formula: "=D2+D3", tone: "green", status: "Tracing EBITDA", stage: 2 };
  if (frame === 9) return { ...base, good: ["D4"], d4: "97.2", name: "D6", formula: "=D4+D5", tone: "green", status: "Tracing EBITDA", stage: 2, scan: 9 };
  return { ...base, good: ["D4", "D6"], d4: "97.2", d6: "44.7", name: "D6", formula: "=D4+D5", tone: "green", status: "Fix tested", busy: false, stage: 3 };
}

export default function HeroSheet() {
  const [frame, setFrame] = useState(0);

  useEffect(() => {
    const timer = window.setTimeout(() => setFrame((current) => (current + 1) % FRAMES.length), FRAMES[frame]);
    return () => window.clearTimeout(timer);
  }, [frame]);

  const look = lookOf(frame);
  const cellClass = (index: number, ref: string | null) => {
    const marks = ["n"];
    if (look.scan === index || (look.scan === 9 && ref === "D6")) marks.push("scan");
    if (ref && look.bad.includes(ref)) marks.push("bad");
    if (ref && look.src.includes(ref)) marks.push("src");
    if (ref && look.good.includes(ref)) marks.push("good");
    return marks.join(" ");
  };
  const valueOf = (ref: string, shown: string) => (ref === "D4" ? look.d4 : ref === "D6" ? look.d6 : shown);

  return (
    <div className="sheetcol" aria-hidden="true">
      <div className="sheet">
        <div className="titlebar">
          <b>X</b>Deal model.xlsx
        </div>
        <div className="ribbon">
          {["File", "Home", "Insert", "Page Layout", "Formulas", "Data", "Review", "View"].map((tab) => (
            <span key={tab} className={tab === "Formulas" ? "on" : undefined}>
              {tab}
            </span>
          ))}
        </div>
        <div className="fx">
          <span className="nm">{look.name}</span>
          <i>fx</i>
          <span className={`formula ${look.tone}`}>{look.formula}</span>
        </div>
        <table>
          <thead>
            <tr>
              <th />
              <th className="a">A</th>
              <th>B</th>
              <th>C</th>
              <th>D</th>
            </tr>
          </thead>
          <tbody>
            <tr className="years">
              <td className="rn">1</td>
              <td>P&amp;L</td>
              <td className="n">2025A</td>
              <td className="n">2026E</td>
              <td className="n">2027E</td>
            </tr>
            {ROWS.map(([row, label, b, c, d, ref], index) => (
              <tr key={row} className={row === 6 ? "total" : undefined}>
                <td className="rn">{row}</td>
                <td>{label}</td>
                <td className={cellClass(index, null)}>{b}</td>
                <td className={cellClass(index, null)}>{c}</td>
                <td className={cellClass(index, ref)}>{valueOf(ref, d)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="tabs">
          <span className="on">P&amp;L</span>
          <span>Balance sheet</span>
          <span>Cash flow</span>
          <span className="st">
            <i className={look.busy ? "ring busy" : "ring"} />
            {look.status}
          </span>
        </div>
      </div>
      <div className="steps3">
        <span className={look.stage >= 1 ? "on" : undefined}>Error detected</span>
        <i />
        <span className={look.stage >= 2 ? "on" : undefined}>Checks run</span>
        <i />
        <span className={look.stage >= 3 ? "on last" : "last"}>Fixed</span>
      </div>
    </div>
  );
}

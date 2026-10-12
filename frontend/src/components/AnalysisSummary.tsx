const ROWS = [
  { tone: "red", count: 1, label: "Hardcoded value", where: "Gross profit 2026E" },
  { tone: "amber", count: 1, label: "Calculation mismatch", where: "EBITDA 2026E" },
  { tone: "amber", count: 0, label: "Broken references", where: "" },
  { tone: "green", count: 32, label: "Checks passed", where: "" },
];

export default function AnalysisSummary() {
  return (
    <div className="summary-panel">
      <p className="summary-title">Analysis summary</p>
      {ROWS.map((row) => (
        <p key={row.label} className="summary-row">
          <span className={`summary-icon ${row.tone}`}>{row.tone === "green" ? "✓" : "!"}</span>
          <span className={`summary-count ${row.tone}`}>{row.count}</span>
          <span className="summary-label">
            {row.label}
            {row.where && <span className="summary-where">{row.where}</span>}
          </span>
        </p>
      ))}
    </div>
  );
}

import styles from "./AnalysisSummary.module.css";

const ROWS = [
  { tone: "red", count: 1, label: "Hardcoded value", where: "Gross profit 2026E" },
  { tone: "amber", count: 1, label: "Calculation mismatch", where: "EBITDA 2026E" },
  { tone: "amber", count: 0, label: "Broken references", where: "" },
  { tone: "green", count: 32, label: "Checks passed", where: "" },
];

export default function AnalysisSummary() {
  return (
    <div className={styles.panel}>
      <p className={styles.title}>Analysis summary</p>
      {ROWS.map((row) => (
        <p key={row.label} className={styles.row}>
          <span className={`${styles.icon} ${styles[row.tone]}`}>{row.tone === "green" ? "✓" : "!"}</span>
          <span className={`${styles.count} ${styles[row.tone]}`}>{row.count}</span>
          <span className={styles.label}>
            {row.label}
            {row.where && <span className={styles.where}>{row.where}</span>}
          </span>
        </p>
      ))}
    </div>
  );
}

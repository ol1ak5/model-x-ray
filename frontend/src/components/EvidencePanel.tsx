import type { Evidence } from "../api";
import styles from "./EvidencePanel.module.css";

const KINDS: Record<Evidence["kind"], string> = { anomaly: "Anomaly", expected_pattern: "Expected", verification: "Sandbox proof" };

export default function EvidencePanel({ evidence }: { evidence: Evidence[] }) {
  return (
    <section aria-labelledby="evidence-title">
      <h2 id="evidence-title" className="visually-hidden">
        Evidence
      </h2>
      <ol className={styles.evidence}>
        {evidence.map((record) => (
          <li key={record.id} id={record.id} tabIndex={-1} className={styles.record}>
            <span className={`mono ${styles.id}`}>{record.id}</span>
            <span className={`${styles.kind} ${styles[record.kind]}`}>{KINDS[record.kind]}</span>
            <span className={`mono ${styles.cell}`}>{record.cell}</span>
            <p className={styles.text}>{record.text}</p>
          </li>
        ))}
      </ol>
    </section>
  );
}

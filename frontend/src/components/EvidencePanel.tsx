import type { Evidence } from "../api";

const KINDS: Record<Evidence["kind"], string> = { anomaly: "Anomaly", expected_pattern: "Expected", verification: "Sandbox proof" };

export default function EvidencePanel({ evidence }: { evidence: Evidence[] }) {
  return (
    <section className="card" aria-labelledby="evidence-title">
      <h2 id="evidence-title">Evidence</h2>
      <ol className="evidence">
        {evidence.map((record) => (
          <li key={record.id} id={record.id} tabIndex={-1}>
            <span className="mono id">{record.id}</span>
            <span className={`kind-tag ${record.kind}`}>{KINDS[record.kind]}</span>
            <span className="mono">{record.cell}</span>
            <p>{record.text}</p>
          </li>
        ))}
      </ol>
    </section>
  );
}

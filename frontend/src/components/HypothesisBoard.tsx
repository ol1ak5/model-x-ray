import type { Hypothesis } from "../api";

const COLUMNS: { status: Hypothesis["status"]; title: string }[] = [
  { status: "open", title: "Open" },
  { status: "rejected", title: "Rejected" },
  { status: "confirmed", title: "Confirmed" },
];

export default function HypothesisBoard({ hypotheses }: { hypotheses: Hypothesis[] }) {
  return (
    <section className="card" aria-labelledby="hypotheses-title">
      <h2 id="hypotheses-title">Findings</h2>
      <div className="board">
        {COLUMNS.map((column) => (
          <div key={column.status} role="group" aria-label={column.title} className={`column ${column.status}`}>
            <h3>{column.title}</h3>
            {hypotheses
              .filter((hypothesis) => hypothesis.status === column.status)
              .map((hypothesis) => (
                <article key={hypothesis.id} className="hypothesis">
                  <p className="mono">{hypothesis.cell}</p>
                  <p className="kind">{hypothesis.error_type.replaceAll("_", " ")}</p>
                  <p>{hypothesis.claim}</p>
                  <p className={`confidence ${hypothesis.confidence}`}>{hypothesis.confidence} confidence</p>
                </article>
              ))}
          </div>
        ))}
      </div>
    </section>
  );
}

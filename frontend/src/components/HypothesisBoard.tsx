import type { Hypothesis } from "../api";

const GROUPS: { status: Hypothesis["status"]; title: string }[] = [
  { status: "confirmed", title: "Confirmed" },
  { status: "open", title: "Open" },
  { status: "rejected", title: "Rejected" },
];

export default function HypothesisBoard({ hypotheses }: { hypotheses: Hypothesis[] }) {
  return (
    <section aria-labelledby="hypotheses-title">
      <h2 id="hypotheses-title" className="visually-hidden">
        Findings
      </h2>
      {GROUPS.filter((group) => hypotheses.some((h) => h.status === group.status)).map((group) => (
        <div key={group.status} role="group" aria-label={group.title} className={`finding-group ${group.status}`}>
          <h3>{group.title}</h3>
          {hypotheses
            .filter((hypothesis) => hypothesis.status === group.status)
            .map((hypothesis) => (
              <article key={hypothesis.id} className="finding">
                <span className={`status-dot ${hypothesis.status}`} aria-hidden="true" />
                <span className="mono finding-cell">{hypothesis.cell}</span>
                <span className="finding-kind">{hypothesis.error_type.replaceAll("_", " ")}</span>
                <p className="finding-claim">{hypothesis.claim}</p>
                <span className={`confidence ${hypothesis.confidence}`}>{hypothesis.confidence} confidence</span>
              </article>
            ))}
        </div>
      ))}
    </section>
  );
}

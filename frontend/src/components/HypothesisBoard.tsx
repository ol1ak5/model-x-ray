import type { Hypothesis } from "../api";
import styles from "./HypothesisBoard.module.css";

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
        <div key={group.status} role="group" aria-label={group.title} className={styles.group}>
          <h3 className={styles.groupTitle}>{group.title}</h3>
          {hypotheses
            .filter((hypothesis) => hypothesis.status === group.status)
            .map((hypothesis) => (
              <article key={hypothesis.id} className={styles.finding}>
                <span className={`${styles.dot} ${styles[hypothesis.status]}`} aria-hidden="true" />
                <span className={`mono ${styles.cell}`}>{hypothesis.cell}</span>
                <span className={styles.kind}>{hypothesis.error_type.replaceAll("_", " ")}</span>
                <p className={styles.claim}>{hypothesis.claim}</p>
                <span className={`${styles.confidence} ${styles[hypothesis.confidence]}`}>{hypothesis.confidence} confidence</span>
              </article>
            ))}
        </div>
      ))}
    </section>
  );
}

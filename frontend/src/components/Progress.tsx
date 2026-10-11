import Chip from "./Chip";
import Spinner from "./Spinner";
import styles from "./Progress.module.css";

export type Step = { step: string; label: string };

export default function Progress({ steps, running }: { steps: Step[]; running: boolean }) {
  return (
    <section className={styles.progress} aria-labelledby="progress-title">
      <h2 id="progress-title" className={styles.title}>
        Progress
        <Chip tone="neutral">{steps.length}</Chip>
      </h2>
      <ol className={styles.list} aria-label="Progress">
        {steps.map((step, index) => (
          <li key={`${step.step}-${index}`} className={styles.done}>
            <span className={styles.tick} aria-hidden="true">
              ✓
            </span>
            {step.label}
          </li>
        ))}
        {running && (
          <li className={styles.working} aria-live="polite">
            <Spinner />
            Working…
          </li>
        )}
      </ol>
    </section>
  );
}

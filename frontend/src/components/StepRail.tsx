import type { RailStep } from "../steps";
import styles from "./StepRail.module.css";

export default function StepRail({ steps }: { steps: RailStep[] }) {
  return (
    <section className={styles.rail} aria-label="Investigation steps">
      <p className={styles.head}>Step by step</p>
      <ol className={styles.list}>
        {steps.map((step, index) => (
          <li key={step.key} className={styles.row} data-tone={step.tone} style={{ animationDelay: `${index * 60}ms` }}>
            <span className={styles.marker} aria-hidden="true" />
            <div className={styles.text}>
              <p className={styles.title}>{step.title}</p>
              {step.detail && (
                <p className={styles.detail} title={step.detail}>
                  {step.detail}
                </p>
              )}
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}

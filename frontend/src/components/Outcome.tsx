import { type InvestigationView, correctedFileUrl } from "../api";
import Button from "./Button";
import styles from "./Outcome.module.css";

export default function Outcome({ view }: { view: InvestigationView }) {
  return (
    <div className={styles.outcome} aria-live="polite">
      <h2 className={styles.title}>Done</h2>
      {view.corrected_copy_id ? (
        <>
          <p className={styles.text}>The fix is written into a new copy with a Change log tab. Your original file is unchanged.</p>
          <Button variant="primary" href={correctedFileUrl(view.id)}>
            Download corrected model
          </Button>
        </>
      ) : (
        <p className={styles.text}>Closed without changes. Your decision is saved.</p>
      )}
    </div>
  );
}

import { useState } from "react";

import type { Decision, Patch } from "../api";
import Button from "./Button";
import styles from "./Review.module.css";

export default function Review({ patch, onDecide }: { patch: Patch | null; onDecide: (decision: Decision) => void }) {
  const [reason, setReason] = useState("");
  const [intentional, setIntentional] = useState(false);
  const [editing, setEditing] = useState(false);
  const [formula, setFormula] = useState(patch?.new_formula ?? "");

  return (
    <div className={styles.review}>
      <h2 className={styles.title}>Your decision</h2>
      {patch ? (
        <div className={styles.fix}>
          <p className={styles.fixCell}>
            Proposed change for <span className="mono">{patch.cell}</span>
          </p>
          <p className={styles.fixRow}>
            <span className={styles.fixLabel}>Current</span>
            <span className={`mono ${styles.old}`}>{patch.old_formula}</span>
          </p>
          <p className={styles.fixRow}>
            <span className={styles.fixLabel}>Proposed</span>
            <span className={`mono ${styles.new}`}>{patch.new_formula}</span>
          </p>
        </div>
      ) : (
        <p className={styles.noFix}>No change to apply.</p>
      )}
      <label className={styles.label} htmlFor="reason">
        Reason
      </label>
      <textarea id="reason" className={styles.textarea} rows={2} value={reason} onChange={(event) => setReason(event.target.value)} placeholder="Why you approve, edit or reject" />
      {editing && patch && (
        <>
          <label className={styles.label} htmlFor="formula">
            New formula for {patch.cell}
          </label>
          <input id="formula" className={`mono ${styles.input}`} value={formula} onChange={(event) => setFormula(event.target.value)} />
        </>
      )}
      <label className={styles.check}>
        <input type="checkbox" checked={intentional} onChange={(event) => setIntentional(event.target.checked)} />
        This is intentional, do not flag it again
      </label>
      <div className={styles.actions}>
        {editing && patch ? (
          <Button variant="primary" disabled={!formula.trim()} onClick={() => onDecide({ action: "edit", reason, patch: { cell: patch.cell, old_formula: patch.old_formula, new_formula: formula.trim() } })}>
            Test my fix
          </Button>
        ) : (
          <Button variant="primary" disabled={!patch} onClick={() => onDecide({ action: "approve", reason })}>
            Approve fix
          </Button>
        )}
        {patch && !editing && (
          <Button variant="secondary" onClick={() => setEditing(true)}>
            Edit fix
          </Button>
        )}
        <Button variant="danger" onClick={() => onDecide(intentional ? { action: "reject", reason, intentional: true } : { action: "reject", reason })}>
          Reject
        </Button>
      </div>
    </div>
  );
}

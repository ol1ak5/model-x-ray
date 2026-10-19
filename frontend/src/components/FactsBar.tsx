import { useState } from "react";

import { type Decision, correctedFileUrl, type InvestigationView } from "../api";
import { money } from "../format";
import Button from "./Button";
import WireKey from "./WireKey";
import styles from "./FactsBar.module.css";

function withEvidenceLinks(text: string, onEvidence: (id: string) => void) {
  return text.split(/(ev-\d+)/g).map((part, index) =>
    /^ev-\d+$/.test(part) ? (
      <a
        key={index}
        href={`#${part}`}
        onClick={(event) => {
          event.preventDefault();
          onEvidence(part);
        }}
      >
        {part}
      </a>
    ) : (
      part
    ),
  );
}

function asFormula(text: string): string {
  const trimmed = text.trim();
  if (trimmed.startsWith("=") || Number.isFinite(Number(trimmed))) return trimmed;
  return `=${trimmed}`;
}

export default function FactsBar({
  view,
  onDecide,
  onEvidence,
}: {
  view: InvestigationView;
  onDecide: (decision: Decision) => void;
  onEvidence: (id: string) => void;
}) {
  const [why, setWhy] = useState(false);
  const [editing, setEditing] = useState(false);
  const [reason, setReason] = useState("");
  const [intentional, setIntentional] = useState(false);
  const [formula, setFormula] = useState(view.patch?.new_formula ?? "");

  const target = view.target;
  const verification = view.verifications?.at(-1) ?? null;
  const checks = verification?.checks ?? {};
  const verdict = verification?.verdict ?? null;

  return (
    <section className={styles.bar} aria-label="Investigation facts">
      {target && (
        <p className={styles.target}>
          <span className={styles.targetName}>
            {target.label} {target.period}
          </span>
          <span className="mono">
            {money(target.prior_value)} → {money(target.value)}
          </span>
        </p>
      )}

      {view.causal_tree && <WireKey />}

      <div className={styles.trailing}>
        {Object.keys(view.check_labels).length > 0 && (
          <p className={styles.checks} aria-label="Deterministic checks">
            {Object.entries(view.check_labels).map(([key, label]) => (
              <span key={key} className={styles.check} data-state={checks[key] ? "pass" : checks[key] === false ? "fail" : "wait"} title={label} />
            ))}
          </p>
        )}
        {verdict && <span className={styles.verdict}>{verdict === "confirmed" ? "Proof passed" : verdict === "rejected" ? "Fix rejected" : "Unproven"}</span>}
        {view.report && (
          <button type="button" className={styles.why} aria-expanded={why} onClick={() => setWhy((value) => !value)}>
            {why ? "Hide" : "Why?"}
          </button>
        )}
      </div>

      {view.report && why && (
        <div className={styles.narrative} role="region" aria-label="Report">
          <p>{withEvidenceLinks(view.report, onEvidence)}</p>
        </div>
      )}

      {view.status === "needs_review" && (
        <div className={styles.decision}>
          {editing && view.patch && (
            <>
              <label className={styles.sr} htmlFor="formula">
                New formula for {view.patch.cell}
              </label>
              <input id="formula" className={`mono ${styles.field}`} value={formula} onChange={(event) => setFormula(event.target.value)} />
            </>
          )}
          <label className={styles.sr} htmlFor="reason">
            Reason
          </label>
          <input id="reason" className={styles.field} value={reason} placeholder="Reason (optional)" onChange={(event) => setReason(event.target.value)} />
          <label className={styles.intentional}>
            <input type="checkbox" checked={intentional} onChange={(event) => setIntentional(event.target.checked)} />
            Never flag again
          </label>
          <div className={styles.buttons}>
            {editing && view.patch ? (
              <Button
                variant="primary"
                disabled={!formula.trim()}
                onClick={() => onDecide({ action: "edit", reason, patch: { cell: view.patch!.cell, old_formula: view.patch!.old_formula, new_formula: asFormula(formula) } })}
              >
                Test my fix
              </Button>
            ) : (
              <>
                <Button variant="primary" disabled={!view.patch} onClick={() => onDecide({ action: "approve", reason })}>
                  Approve fix
                </Button>
                {view.patch && (
                  <Button variant="secondary" onClick={() => setEditing(true)}>
                    Edit fix
                  </Button>
                )}
              </>
            )}
            <Button variant="danger" onClick={() => onDecide(intentional ? { action: "reject", reason, intentional: true } : { action: "reject", reason })}>
              Reject
            </Button>
          </div>
        </div>
      )}

      {view.status === "done" && (
        <p className={styles.closed}>
          {view.corrected_copy_id ? (
            <>
              Fix applied to a new copy. <a href={correctedFileUrl(view.id)}>Download corrected model</a>
            </>
          ) : (
            "Closed without changes. Your decision is saved."
          )}
        </p>
      )}
    </section>
  );
}

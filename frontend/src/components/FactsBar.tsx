import { useState } from "react";

import { type Decision, correctedFileUrl, type InvestigationView } from "../api";
import { figure, kindOf } from "../format";
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

function plural(count: number, one: string, many: string): string {
  return count === 1 ? `1 ${one}` : `${count} ${many}`;
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
  const [choiceWhy, setChoiceWhy] = useState(false);
  const [editing, setEditing] = useState(false);
  const [reason, setReason] = useState("");
  const [intentional, setIntentional] = useState(false);
  const [formula, setFormula] = useState(view.patch?.new_formula ?? "");
  const [downloaded, setDownloaded] = useState(false);

  const target = view.target;
  const kind = kindOf(view.model_map, target?.label);
  const verification = view.verifications?.at(-1) ?? null;
  const checks = verification?.checks ?? {};
  const labels = Object.keys(view.check_labels ?? {});
  const passed = labels.filter((key) => checks[key]).length;
  const suspects = view.hypotheses?.length ?? 0;
  const evidence = view.evidence?.length ?? 0;
  const traced = target ? `${target.sheet}!${target.cell}` : null;
  const lines = view.model_map ? new Set(view.model_map.rows.map((row) => row.label)).size : 0;
  const settled = view.status !== "running";
  const clean = (view.report ?? "").startsWith("No error found");
  const showChecks = Boolean(view.patch) || Boolean(view.corrected_copy_id);

  const facts = [
    traced ? (
      <>
        traced <span className="mono">{traced}</span>
      </>
    ) : null,
    lines > 0 ? `${lines} lines read` : null,
    suspects > 0 ? `${plural(suspects, "suspect", "suspects")} examined` : null,
    evidence > 0 ? plural(evidence, "evidence link", "evidence links") : null,
  ].filter((item) => item !== null);

  return (
    <section className={styles.bar} aria-label="Investigation facts">
      {target && (
        <p className={styles.target}>
          <span className={styles.targetName}>
            {target.label} {target.period}
          </span>
          <span className="mono">
            {figure(target.prior_value, kind)} → {figure(target.value, kind)}
          </span>
        </p>
      )}

      {view.target_choice && (
        <p className={styles.choice} title={view.target_choice.why}>
          {view.target_choice.candidates.length > 1 ? (
            <>
              Chosen among {view.target_choice.candidates.length} candidates:{" "}
              <span className="mono">{view.target_choice.candidates.join(", ")}</span>
            </>
          ) : (
            <>
              Chosen: <span className="mono">{view.target_choice.chosen}</span>
            </>
          )}
          {view.target_choice.why && (
            <button type="button" className={styles.choiceWhy} aria-expanded={choiceWhy} onClick={() => setChoiceWhy((value) => !value)}>
              why?
            </button>
          )}
        </p>
      )}

      {choiceWhy && view.target_choice?.why && <p className={styles.choiceNote}>{view.target_choice.why}</p>}

      {view.causal_tree && <WireKey />}

      <div className={styles.trailing}>
        {labels.length > 0 && showChecks && (
          <p className={styles.checks} aria-label="Deterministic checks">
            {labels.map((key) => (
              <span key={key} className={styles.check} data-state={checks[key] ? "pass" : checks[key] === false ? "fail" : "wait"} title={view.check_labels?.[key]} />
            ))}
          </p>
        )}
        {labels.length > 0 && showChecks && settled && (
          <span className={styles.verdict}>
            {passed} of {labels.length} checks
          </span>
        )}
      </div>

      {settled && view.status === "needs_review" && (
        <div className={styles.outcome} data-tone={view.patch ? "fix" : "clear"}>
          <p className={styles.outcomeTitle}>
            {view.patch ? (
              <>
                Fix ready in <span className="mono">{view.patch.cell}</span>
              </>
            ) : clean ? (
              "The model checks out — nothing to change"
            ) : (
              "Nothing to change in this model"
            )}
          </p>
          <p className={styles.outcomeFacts}>{facts.length > 0 ? facts.map((item, index) => <span key={index}>{index > 0 && <span className={styles.dot}> · </span>}{item}</span>) : null}</p>
          <p className={styles.outcomeNote}>
            {view.patch ? (
              <>
                <span className={`mono ${styles.old}`}>{view.patch.old_formula}</span> → <span className={`mono ${styles.new}`}>{view.patch.new_formula}</span>. Your file is untouched: the fix goes to a copy only if you approve it.
              </>
            ) : clean ? (
              "No cell broke the pattern of its own row, so there is no fix to approve. The report below lists what was checked."
            ) : (
              "No formula was rewritten, so there is nothing to approve. The report below lists what was checked."
            )}
          </p>
        </div>
      )}

      {settled && view.status === "done" && view.corrected_copy_id && (
        <div className={styles.outcome} data-tone="fix">
          <p className={styles.outcomeTitle}>
            Fixed and checked{view.patch ? <> in <span className="mono">{view.patch.cell}</span></> : null}
          </p>
          <p className={styles.outcomeFacts}>
            {passed} of {labels.length} checks passed · written to a copy, never your file
          </p>
        </div>
      )}

      {view.report && (
        <div className={styles.report} role="region" aria-label="Report">
          <p className={styles.reportLabel}>What was checked</p>
          <p className={styles.reportText}>{withEvidenceLinks(view.report, onEvidence)}</p>
        </div>
      )}

      {view.status === "needs_review" && view.patch && (
        <div className={styles.decision}>
          {editing && (
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
            {editing ? (
              <Button
                variant="primary"
                disabled={!formula.trim()}
                onClick={() => onDecide({ action: "edit", reason, patch: { cell: view.patch!.cell, old_formula: view.patch!.old_formula, new_formula: asFormula(formula) } })}
              >
                Test my fix
              </Button>
            ) : (
              <>
                <Button variant="primary" onClick={() => onDecide({ action: "approve", reason })}>
                  Approve fix
                </Button>
                <Button variant="secondary" onClick={() => setEditing(true)}>
                  Edit fix
                </Button>
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
            downloaded ? (
              <>The corrected model went to your downloads, and the copy is no longer on the server.</>
            ) : (
              <>
                Fix applied to a new copy.{" "}
                <a href={correctedFileUrl(view.id)} onClick={() => setDownloaded(true)}>
                  Download corrected model
                </a>
              </>
            )
          ) : (
            "Closed without changes. Your decision is saved."
          )}
        </p>
      )}
    </section>
  );
}

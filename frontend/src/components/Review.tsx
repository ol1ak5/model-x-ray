import { useState } from "react";

import type { Decision, Patch } from "../api";

export default function Review({ patch, onDecide }: { patch: Patch | null; onDecide: (decision: Decision) => void }) {
  const [reason, setReason] = useState("");
  const [intentional, setIntentional] = useState(false);
  const [editing, setEditing] = useState(false);
  const [formula, setFormula] = useState(patch?.new_formula ?? "");

  return (
    <div className="card review">
      <h2>Your decision</h2>
      {patch ? (
        <p className="fix">
          Proposed fix for <span className="mono">{patch.cell}</span>: <span className="mono old">{patch.old_formula}</span> →{" "}
          <span className="mono new">{patch.new_formula}</span>
        </p>
      ) : (
        <p className="fix">No fix to apply.</p>
      )}
      <label htmlFor="reason">Reason</label>
      <textarea id="reason" rows={2} value={reason} onChange={(event) => setReason(event.target.value)} placeholder="Why you approve, edit or reject" />
      {editing && patch && (
        <>
          <label htmlFor="formula">New formula for {patch.cell}</label>
          <input id="formula" className="mono" value={formula} onChange={(event) => setFormula(event.target.value)} />
        </>
      )}
      <label className="check">
        <input type="checkbox" checked={intentional} onChange={(event) => setIntentional(event.target.checked)} />
        This is intentional, do not flag it again
      </label>
      <div className="actions">
        {editing && patch ? (
          <button type="button" className="primary" disabled={!formula.trim()} onClick={() => onDecide({ action: "edit", reason, patch: { cell: patch.cell, old_formula: patch.old_formula, new_formula: formula.trim() } })}>
            Test my fix
          </button>
        ) : (
          <button type="button" className="primary" disabled={!patch} onClick={() => onDecide({ action: "approve", reason })}>
            Approve fix
          </button>
        )}
        {patch && !editing && (
          <button type="button" onClick={() => setEditing(true)}>
            Edit fix
          </button>
        )}
        <button type="button" className="danger" onClick={() => onDecide(intentional ? { action: "reject", reason, intentional: true } : { action: "reject", reason })}>
          Reject
        </button>
      </div>
    </div>
  );
}

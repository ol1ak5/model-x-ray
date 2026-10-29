import { type FormEvent, useCallback, useState } from "react";

import { ApiError, type ChatTurn, type Decision, type InvestigationView, type WorkbookView, correctedFileHref } from "../api";
import Brand from "../components/Brand";
import type { Finding } from "../findings";
import type { Phase } from "../progress";
import SheetDialog, { type Marks } from "./SheetDialog";

type Pending = "approve" | "edit" | "reject" | null;

type Status = { label: string; tone: "run" | "wait" | "done"; line: string };

const LABELS: Record<Finding["status"], string> = { detected: "Error detected", fixed: "Fixed", dismissed: "Not an error" };

function Chat({ cell, onAsk }: { cell: string; onAsk: (question: string, history: ChatTurn[]) => Promise<string> }) {
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [draft, setDraft] = useState("");
  const [thinking, setThinking] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const id = `ask-${cell.replace(/[^A-Za-z0-9]/g, "-")}`;

  async function send(event: FormEvent) {
    event.preventDefault();
    const question = draft.trim();
    if (!question || thinking) return;
    const history = turns;
    setTurns([...history, { role: "user", text: question }]);
    setDraft("");
    setFailure(null);
    setThinking(true);
    try {
      const answer = await onAsk(question, history);
      setTurns((current) => [...current, { role: "agent", text: answer }]);
    } catch (reason) {
      setFailure(reason instanceof ApiError ? reason.message : "The agent could not be reached. Please try again.");
    } finally {
      setThinking(false);
    }
  }

  return (
    <div className="chat">
      <div className="thread" aria-live="polite">
        {turns.map((turn, index) => (
          <p key={index} className={`msg ${turn.role === "user" ? "me" : "agent"}`}>
            <b>{turn.role === "user" ? "You:" : "Model X-Ray:"}</b> {turn.text}
          </p>
        ))}
        {thinking && (
          <p className="msg agent thinking">
            <b>Model X-Ray:</b> Thinking…
          </p>
        )}
        {failure && (
          <p className="alert" role="alert">
            {failure}
          </p>
        )}
      </div>
      <form className="ask" onSubmit={send}>
        <label htmlFor={id} className="visually-hidden">
          Ask the agent about this error
        </label>
        <input id={id} type="text" placeholder="Ask the agent about the error or the fix" autoComplete="off" maxLength={500} value={draft} onChange={(event) => setDraft(event.target.value)} />
        <button className="btn plain" type="submit" disabled={thinking || !draft.trim()}>
          Ask
        </button>
      </form>
    </div>
  );
}

function Item({ finding, open, pending, busy, onToggle, onOpenSheet, onDecide, onAsk }: { finding: Finding; open: boolean; pending: Pending; busy: boolean; onToggle: () => void; onOpenSheet: () => void; onDecide: (decision: Decision, kind: Pending) => void; onAsk: (question: string, history: ChatTurn[]) => Promise<string> }) {
  const [mode, setMode] = useState<"actions" | "edit" | "reject">("actions");
  const [formula, setFormula] = useState(finding.after);
  const [never, setNever] = useState(false);
  const decided = finding.status !== "detected";
  const id = finding.cell.replace(/[^A-Za-z0-9]/g, "-");

  return (
    <li className={open ? "open-item" : undefined}>
      <button type="button" className="erow" aria-expanded={open} onClick={onToggle}>
        <span className="cell">{finding.cell}</span>
        <span className="what">{finding.title}</span>
        <span className={`st ${finding.status}`}>{LABELS[finding.status]}</span>
        <span className="chev" aria-hidden="true">
          ›
        </span>
      </button>
      {open && (
        <div className="ebody">
          <dl className="facts">
            <dt>Where</dt>
            <dd>
              <code>{finding.cell}</code>
              <button type="button" className="open" onClick={onOpenSheet}>
                Open in the sheet
              </button>
            </dd>
            <dt>Error</dt>
            <dd>
              <code className="bad">{finding.before}</code>
            </dd>
            <dt>{finding.status === "fixed" ? "Fixed with" : "Solution"}</dt>
            <dd>
              <code className="good">{finding.after}</code>
            </dd>
            <dt>Explanation</dt>
            <dd className="explain">
              {finding.explanation.map((paragraph) => (
                <p key={paragraph}>{paragraph}</p>
              ))}
            </dd>
          </dl>

          {finding.status === "fixed" && <div className="done-note">✓ Fix accepted</div>}

          {!decided && mode === "actions" && (
            <div className="actions">
              <button type="button" className="btn go" disabled={busy} onClick={() => onDecide({ action: "approve", reason: "" }, "approve")}>
                {pending === "approve" ? "Testing in a copy…" : "Approve fix"}
              </button>
              <button type="button" className="btn plain" disabled={busy} onClick={() => setMode("edit")}>
                Edit fix
              </button>
              <button type="button" className="btn no" disabled={busy} onClick={() => setMode("reject")}>
                Reject
              </button>
            </div>
          )}

          {!decided && mode === "edit" && (
            <div className="editbox">
              <label htmlFor={`edit-${id}`}>
                Your formula for <code>{finding.cell}</code>
              </label>
              <div className="editrow">
                <input id={`edit-${id}`} type="text" value={formula} spellCheck={false} onChange={(event) => setFormula(event.target.value)} />
                <button type="button" className="btn go" disabled={busy || !formula.trim()} onClick={() => onDecide({ action: "edit", reason: "", patch: { cell: finding.cell, old_formula: finding.before, new_formula: formula.trim() } }, "edit")}>
                  {pending === "edit" ? "Testing your fix…" : "Test my fix"}
                </button>
                <button type="button" className="btn plain" disabled={busy} onClick={() => setMode("actions")}>
                  Cancel
                </button>
              </div>
              <p className="hint2">The agent recalculates your formula in a copy and checks it before you approve.</p>
            </div>
          )}

          {!decided && mode === "reject" && (
            <div className="rejectbox">
              <p className="q">Why are you rejecting it?</p>
              <div className="editrow">
                <button type="button" className="btn plain" disabled={busy} onClick={() => onDecide({ action: "reject", reason: "It's not an error", intentional: never }, "reject")}>
                  It's not an error
                </button>
                <button type="button" className="btn no" disabled={busy} onClick={() => setMode("actions")}>
                  Cancel
                </button>
              </div>
              <label className="never">
                <input type="checkbox" checked={never} onChange={(event) => setNever(event.target.checked)} /> Never flag this cell again
              </label>
            </div>
          )}

          {finding.status !== "fixed" && <Chat cell={finding.cell} onAsk={onAsk} />}
        </div>
      )}
    </li>
  );
}

export default function CheckPage({
  name,
  sheets,
  phases,
  status,
  findings,
  view,
  fixedIn,
  running,
  error,
  loadWorkbook,
  onDecide,
  onHome,
  onDemo,
  onRetry,
  onAsk,
}: {
  name: string;
  sheets: string[];
  phases: Phase[];
  status: Status;
  findings: Finding[];
  view: InvestigationView | null;
  fixedIn: InvestigationView | null;
  running: boolean;
  error: { message: string; advice: string } | null;
  loadWorkbook: () => Promise<WorkbookView>;
  onDecide: (cell: string, decision: Decision) => void;
  onHome: () => void;
  onDemo: () => void;
  onRetry: () => void;
  onAsk: (cell: string, question: string, history: ChatTurn[]) => Promise<string>;
}) {
  const [filter, setFilter] = useState("All");
  const [open, setOpen] = useState<Set<string>>(new Set());
  const [pending, setPending] = useState<Pending>(null);
  const [viewer, setViewer] = useState<{ sheet: string; title: string; marks: Marks } | null>(null);
  const shownPending = running ? pending : null;
  const types = ["All", ...new Set(findings.map((finding) => finding.type))];
  const listed = findings.filter((finding) => filter === "All" || finding.type === filter);
  const settled = findings.length > 0 && findings.every((finding) => finding.status !== "detected");
  const fixed = findings.filter((finding) => finding.status === "fixed").length;
  const done = phases.filter((phase) => phase.state === "done").length;
  const load = useCallback(() => loadWorkbook(), [loadWorkbook]);

  function toggle(cell: string) {
    setOpen((current) => {
      const next = new Set(current);
      if (next.has(cell)) next.delete(cell);
      else next.add(cell);
      return next;
    });
  }

  function decide(cell: string, decision: Decision, kind: Pending) {
    setPending(kind);
    onDecide(cell, decision);
  }

  const download = fixedIn ? correctedFileHref(fixedIn) : view ? correctedFileHref(view) : null;

  return (
    <div className="check">
      <header className="site-nav static">
        <div className="wrap">
          <Brand onHome={onHome} />
          <div className="nav-right">
            <nav className="nav-links" aria-label="Demo">
              <button type="button" onClick={onDemo} disabled={running}>
                Try the demo
              </button>
            </nav>
            <button type="button" className="pill green sm" onClick={onHome}>
              Check another model
            </button>
          </div>
        </div>
      </header>

      <main className="wrap">
        <div className="vh">
          <div>
            <h1>{name}</h1>
            {sheets.length > 0 && (
              <div className="sheets">
                <span>Sheets in this file:</span>
                {sheets.map((sheet) => (
                  <button type="button" key={sheet} onClick={() => setViewer({ sheet, title: `${sheet} · ${name}`, marks: null })}>
                    {sheet}
                  </button>
                ))}
              </div>
            )}
          </div>
          <div className="meta" aria-live="polite">
            <span className={`state ${status.tone}`}>{status.label}</span>
            <span>{status.line}</span>
          </div>
        </div>

        {error && (
          <p className="alert" role="alert">
            {error.message}
            {error.advice && <span className="alert-advice"> {error.advice}</span>}
          </p>
        )}

        <div className="two">
          <section className="steps" aria-label="Progress">
            <p className="label">
              Progress: {done} of {phases.length}
            </p>
            <ol>
              {phases.map((phase) => (
                <li key={phase.name} className={phase.state === "todo" ? undefined : phase.state} data-state={phase.state}>
                  <span className="d">{phase.state === "done" ? "✓" : ""}</span>
                  <div>
                    <b>{phase.name}</b>
                    <small>{phase.hint}</small>
                  </div>
                </li>
              ))}
            </ol>
          </section>

          <section aria-label="Errors detected">
            <p className="label">Errors detected: {findings.length}</p>
            {findings.length > 0 ? (
              <>
                <div className="filters">
                  {types.map((type) => (
                    <button type="button" key={type} className={type === filter ? "on" : undefined} aria-pressed={type === filter} onClick={() => setFilter(type)}>
                      {type}
                      <span className="n">{type === "All" ? findings.length : findings.filter((finding) => finding.type === type).length}</span>
                    </button>
                  ))}
                </div>
                <ul className="elist">
                  {listed.map((finding) => (
                    <Item
                      key={finding.cell}
                      finding={finding}
                      open={open.has(finding.cell)}
                      pending={shownPending}
                      busy={running}
                      onToggle={() => toggle(finding.cell)}
                      onOpenSheet={() => setViewer({ sheet: finding.sheet, title: `${finding.cell} · ${finding.title}`, marks: { error: finding.cell, dependents: finding.dependents } })}
                      onDecide={(decision, kind) => decide(finding.cell, decision, kind)}
                      onAsk={(question, history) => onAsk(finding.cell, question, history)}
                    />
                  ))}
                </ul>
                {settled && !running && fixed > 0 && download && (
                  <div className="done-note">
                    <span>
                      ✓ {fixed === 1 ? "The fix is" : `${fixed} fixes are`} saved to a new copy.
                      <small>Your original file is unchanged.</small>
                    </span>
                    <a className="pill green" {...download}>
                      Download {name.replace(/\.xlsx$/i, "")} (corrected).xlsx
                    </a>
                  </div>
                )}
              </>
            ) : (
              <>
                <p className="empty">{running ? "Errors appear here as the agent finds them." : !view || view.status === "running" ? "The check stopped before it found anything." : "The agent found nothing to fix in this model."}</p>
                {!running && (!view || view.status === "running") && (
                  <button type="button" className="pill green sm retry" onClick={onRetry}>
                    Run again
                  </button>
                )}
              </>
            )}
          </section>
        </div>
      </main>

      <SheetDialog open={viewer !== null} name={name} sheet={viewer?.sheet ?? sheets[0] ?? ""} title={viewer?.title ?? ""} marks={viewer?.marks ?? null} load={load} onClose={() => setViewer(null)} />

      <footer className="site-footer">
        <div className="wrap">
          <span>Model X-Ray</span>
          <span>Powered by NVIDIA Nemotron on Nebius Token Factory</span>
        </div>
      </footer>
    </div>
  );
}

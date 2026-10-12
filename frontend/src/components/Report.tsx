import type { ReactNode } from "react";

import type { InvestigationView } from "../api";
import { money } from "../format";

type Outcome = { title: string; tone: "found" | "clean" | "unproven" };

function outcomeOf(text: string): Outcome {
  if (text.includes("Root cause found")) return { title: "Root cause found", tone: "found" };
  if (text.startsWith("No error found")) return { title: "No error found", tone: "clean" };
  return { title: "No confirmed error", tone: "unproven" };
}

function withEvidenceLinks(text: string, onEvidence: (id: string) => void): ReactNode[] {
  return text.split(/(ev-\d+)/).map((part, index) =>
    /^ev-\d+$/.test(part) ? (
      <a
        key={index}
        href={`#${part}`}
        className="evidence-link"
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

export default function Report({ view, onEvidence }: { view: InvestigationView; onEvidence: (id: string) => void }) {
  const text = view.report ?? "";
  const outcome = outcomeOf(text);
  const target = view.target;
  const targetRef = target ? `${target.sheet}!${target.cell}` : null;
  const confirmed = view.hypotheses?.find((h) => h.status === "confirmed");
  const after = targetRef ? view.verifications?.at(-1)?.after?.[targetRef] : undefined;
  const headline = confirmed ? `Root cause found in ${confirmed.cell}` : outcome.title;
  const detail = confirmed ? confirmed.claim : outcome.tone === "clean" ? "The change is explained by its inputs. Nothing breaks the model's logic." : "The agent checked the suspects below but could not prove an error.";

  return (
    <section className={`card result ${outcome.tone}`} aria-labelledby="report-title">
      <div className="result-head">
        <p className={`badge ${outcome.tone}`}>{outcome.title}</p>
        <h2 id="report-title" className="visually-hidden">
          Report
        </h2>
      </div>
      <p className="result-title">{headline}</p>
      <p className="result-detail">{detail}</p>
      {target && (
        <div className="kpis">
          <div className="kpi">
            <span className="kpi-label">
              {target.label} {target.period} <span className="mono">{targetRef}</span>
            </span>
            <span className="kpi-value">
              {money(target.prior_value)} → {money(target.value)}
            </span>
          </div>
          {after !== undefined && (
            <div className="kpi good">
              <span className="kpi-label">After the correction</span>
              <span className="kpi-value">{money(after)}</span>
            </div>
          )}
          {confirmed && (
            <div className="kpi">
              <span className="kpi-label">Confidence</span>
              <span className="kpi-value capitalize">{confirmed.confidence}</span>
            </div>
          )}
        </div>
      )}
      <p className="report-text">{withEvidenceLinks(text, onEvidence)}</p>
    </section>
  );
}

import type { ReactNode } from "react";

import type { TargetCell } from "../api";

function outcome(text: string): { title: string; tone: string } {
  if (text.includes("Root cause found")) return { title: "Root cause found", tone: "found" };
  if (text.startsWith("No error found")) return { title: "No error found", tone: "clean" };
  return { title: "No confirmed error", tone: "unproven" };
}

function withEvidenceLinks(text: string): ReactNode[] {
  return text.split(/(ev-\d+)/).map((part, index) =>
    /^ev-\d+$/.test(part) ? (
      <a key={index} href={`#${part}`} className="evidence-link">
        {part}
      </a>
    ) : (
      part
    ),
  );
}

export default function Report({ text, target }: { text: string; target: TargetCell | null }) {
  const { title, tone } = outcome(text);
  return (
    <section className="card report" aria-labelledby="report-title">
      <h2 id="report-title">Report</h2>
      <p className={`badge ${tone}`}>{title}</p>
      {target && (
        <p className="target">
          <span className="mono">
            {target.sheet}!{target.cell}
          </span>{" "}
          {target.label} {target.period}: {target.prior_value.toFixed(2)} → {target.value.toFixed(2)}
        </p>
      )}
      <p className="report-text">{withEvidenceLinks(text)}</p>
    </section>
  );
}

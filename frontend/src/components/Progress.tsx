export type Step = { step: string; label: string };

export default function Progress({ steps, running }: { steps: Step[]; running: boolean }) {
  return (
    <div className="card">
      <h2 id="progress-title">Progress</h2>
      <ol className="progress" aria-label="Progress">
        {steps.map((step, index) => (
          <li key={`${step.step}-${index}`} className="done">
            <span className="tick" aria-hidden="true">✓</span>
            {step.label}
          </li>
        ))}
        {running && (
          <li className="working" aria-live="polite">
            <span className="spinner" aria-hidden="true" />
            Working…
          </li>
        )}
      </ol>
    </div>
  );
}

import { type InvestigationView, correctedFileUrl } from "../api";

export default function Outcome({ view }: { view: InvestigationView }) {
  return (
    <div className="card outcome" aria-live="polite">
      <h2>Done</h2>
      {view.corrected_copy_id ? (
        <>
          <p>The fix is written into a new copy with a Change log tab. Your original file is unchanged.</p>
          <a className="primary download" href={correctedFileUrl(view.id)}>
            Download corrected model
          </a>
        </>
      ) : (
        <p>Closed without changes. Your decision is saved.</p>
      )}
    </div>
  );
}

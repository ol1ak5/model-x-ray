import { type ChangeEvent, type FormEvent, useState } from "react";

import { ApiError, type Spreadsheet, uploadSpreadsheet } from "../api";
import Icon from "./Icon";

type Chosen = { id: string; name: string };

export default function QuestionForm({ demos, busy, onStart, onError }: { demos: Spreadsheet[]; busy: boolean; onStart: (spreadsheetId: string, question: string, name: string) => void; onError: (message: string) => void }) {
  const [chosen, setChosen] = useState<Chosen | null>(null);
  const [uploading, setUploading] = useState(false);
  const [asking, setAsking] = useState(false);
  const [question, setQuestion] = useState("");

  async function upload(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      const uploaded = await uploadSpreadsheet(file);
      setChosen({ id: uploaded.id, name: uploaded.name });
    } catch (reason) {
      onError(reason instanceof ApiError ? reason.message : "The upload failed. Please try again.");
    } finally {
      setUploading(false);
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    if (chosen) onStart(chosen.id, asking ? question.trim() : "", chosen.name);
  }

  return (
    <form className="ask" onSubmit={submit}>
      <input id="upload" type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" className="visually-hidden" onChange={upload} />
      <label htmlFor="upload" className="dropzone">
        <span className="drop-icon"><Icon name="upload" /></span>
        <span className="drop-title">{uploading ? "Uploading…" : chosen ? chosen.name : "Upload your model"}</span>
        <span className="drop-hint">{chosen ? "Ready to check. Choose another file to replace it." : "Excel .xlsx, up to 10 MB. Your file stays private."}</span>
      </label>
      <div className="ask-row">
        <button type="submit" className="primary" disabled={busy || uploading || !chosen}>
          {busy ? "Checking…" : "Check model"}
        </button>
        {demos.map((demo) => (
          <button key={demo.id} type="button" className="secondary" onClick={() => setChosen({ id: demo.id, name: demos.length === 1 ? "Demo model" : demo.id })}>
            <Icon name="play" size={16} />
            {demos.length === 1 ? "Try the demo model" : `Try demo: ${demo.id}`}
          </button>
        ))}
      </div>
      {asking ? (
        <>
          <label htmlFor="question">Number to explain (optional)</label>
          <textarea id="question" rows={2} value={question} placeholder="For example: EBITDA 2027" onChange={(event) => setQuestion(event.target.value)} />
        </>
      ) : (
        <button type="button" className="link-button subtle" onClick={() => setAsking(true)}>
          Ask about a specific number instead
        </button>
      )}
    </form>
  );
}

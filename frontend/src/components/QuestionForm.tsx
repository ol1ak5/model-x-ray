import { type FormEvent, useState } from "react";

import type { Spreadsheet } from "../api";

const EXAMPLES = ["Why did EBITDA 2027 jump?", "Why did revenue fall next year?"];

export default function QuestionForm({ spreadsheets, busy, onStart }: { spreadsheets: Spreadsheet[]; busy: boolean; onStart: (spreadsheetId: string, question: string) => void }) {
  const [spreadsheetId, setSpreadsheetId] = useState("");
  const [question, setQuestion] = useState("");

  function submit(event: FormEvent) {
    event.preventDefault();
    if (spreadsheetId && question.trim()) onStart(spreadsheetId, question.trim());
  }

  return (
    <form className="card ask" onSubmit={submit}>
      <label htmlFor="model">Model</label>
      <select id="model" value={spreadsheetId} onChange={(event) => setSpreadsheetId(event.target.value)}>
        <option value="" disabled>
          Choose a model
        </option>
        {spreadsheets.map((spreadsheet) => (
          <option key={spreadsheet.id} value={spreadsheet.id}>
            {spreadsheet.id}
          </option>
        ))}
      </select>
      <label htmlFor="question">Question</label>
      <textarea id="question" rows={3} value={question} placeholder="Why did EBITDA 2027 jump?" onChange={(event) => setQuestion(event.target.value)} />
      <div className="examples" aria-label="Example questions">
        {EXAMPLES.map((example) => (
          <button key={example} type="button" className="chip" onClick={() => setQuestion(example)}>
            {example}
          </button>
        ))}
      </div>
      <button type="submit" className="primary" disabled={busy || !spreadsheetId || !question.trim()}>
        {busy ? "Investigating…" : "Investigate"}
      </button>
    </form>
  );
}

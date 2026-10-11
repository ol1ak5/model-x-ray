import { type ChangeEvent, useState } from "react";

import { ApiError, type Spreadsheet, uploadSpreadsheet } from "../api";
import Icon from "./Icon";

export default function QuestionForm({ demos, onStart, onError }: { demos: Spreadsheet[]; onStart: (spreadsheetId: string, question: string, name: string) => void; onError: (message: string) => void }) {
  const [uploading, setUploading] = useState(false);

  async function upload(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      const uploaded = await uploadSpreadsheet(file);
      onStart(uploaded.id, "", uploaded.name);
    } catch (reason) {
      onError(reason instanceof ApiError ? reason.message : "The upload failed. Please try again.");
    } finally {
      setUploading(false);
    }
  }

  const demo = demos[0];
  return (
    <div className="ask-row">
      <input id="upload" type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" className="visually-hidden" onChange={upload} disabled={uploading} />
      <label htmlFor="upload" className="primary button-like">
        <Icon name="upload" size={18} />
        {uploading ? "Uploading…" : "Upload your model"}
      </label>
      {demo && (
        <button type="button" className="demo-button" onClick={() => onStart(demo.id, "", "Demo model")}>
          <span className="play-ring">
            <Icon name="play" size={13} />
          </span>
          Try demo
        </button>
      )}
      <p className="ask-note">Excel .xlsx, up to 10 MB. Your file stays private; corrections are saved to a new copy.</p>
    </div>
  );
}

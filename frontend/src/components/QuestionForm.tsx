import { type ChangeEvent, useState } from "react";

import { ApiError, type Spreadsheet, uploadSpreadsheet } from "../api";
import Spinner from "./Spinner";
import styles from "./QuestionForm.module.css";

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
    <div className={styles.boxes}>
      {demo && (
        <button type="button" className={`${styles.box} ${styles.demo}`} aria-label="See it in action" onClick={() => onStart(demo.id, "", "Demo model")}>
          <span className={styles.icon} aria-hidden="true">
            ▶
          </span>
          <span className={styles.title}>See it in action</span>
        </button>
      )}
      <input id="upload" type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" className="visually-hidden" onChange={upload} disabled={uploading} />
      <label htmlFor="upload" className={`${styles.box} ${styles.upload}`}>
        <span className={styles.icon} aria-hidden="true">
          {uploading ? <Spinner size={1} /> : "↑"}
        </span>
        <span className={styles.title}>{uploading ? "Uploading…" : "Upload your model"}</span>
      </label>
      <p className={styles.note}>Excel .xlsx up to 10 MB. Your file stays private.</p>
    </div>
  );
}

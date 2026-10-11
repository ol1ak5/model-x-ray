import { type ChangeEvent, useState } from "react";

import { ApiError, type Spreadsheet, uploadSpreadsheet } from "../api";
import Button from "./Button";
import Icon from "./Icon";
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
    <div className={styles.row}>
      <input id="upload" type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" className="visually-hidden" onChange={upload} disabled={uploading} />
      <Button variant="primary" htmlFor="upload" className={styles.upload}>
        {uploading ? <Spinner size={1.125} /> : <Icon name="upload" size={18} />}
        {uploading ? "Uploading…" : "Upload your model"}
      </Button>
      {demo && (
        <Button variant="secondary" className={styles.demo} onClick={() => onStart(demo.id, "", "Demo model")}>
          <Icon name="play" size={13} />
          See it in action
        </Button>
      )}
      <p className={styles.note}>Excel .xlsx, up to 10 MB. Your file stays private. Approved changes are saved to a new copy.</p>
    </div>
  );
}

import { useState } from "react";

import type { CellChoicePause } from "../api";
import Button from "./Button";
import styles from "./CellChoice.module.css";

export default function CellChoice({ pause, onChoose }: { pause: CellChoicePause; onChoose: (ref: string) => void }) {
  const [typed, setTyped] = useState("");
  return (
    <fieldset className={styles.choice}>
      <legend className={styles.legend}>{pause.question}</legend>
      {pause.candidates.length > 0 && (
        <div className={styles.candidates}>
          {pause.candidates.map((candidate) => (
            <Button key={candidate} variant="secondary" className={`mono ${styles.cell}`} onClick={() => onChoose(candidate)}>
              {candidate}
            </Button>
          ))}
        </div>
      )}
      <label className={styles.label} htmlFor="cell">
        Or type a cell, for example P&amp;L!H8
      </label>
      <div className={styles.inline}>
        <input id="cell" className={styles.input} value={typed} onChange={(event) => setTyped(event.target.value)} />
        <Button variant="primary" disabled={!typed.includes("!")} onClick={() => onChoose(typed.trim())}>
          Use this cell
        </Button>
      </div>
    </fieldset>
  );
}

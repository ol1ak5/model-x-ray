import { useState } from "react";

import type { CellChoicePause } from "../api";

export default function CellChoice({ pause, onChoose }: { pause: CellChoicePause; onChoose: (ref: string) => void }) {
  const [typed, setTyped] = useState("");
  return (
    <fieldset className="card choice">
      <legend>{pause.question}</legend>
      {pause.candidates.length > 0 && (
        <div className="candidates">
          {pause.candidates.map((candidate) => (
            <button key={candidate} type="button" className="cell-button" onClick={() => onChoose(candidate)}>
              {candidate}
            </button>
          ))}
        </div>
      )}
      <label htmlFor="cell">Or type a cell, for example P&amp;L!H8</label>
      <div className="inline">
        <input id="cell" value={typed} onChange={(event) => setTyped(event.target.value)} />
        <button type="button" disabled={!typed.includes("!")} onClick={() => onChoose(typed.trim())}>
          Use this cell
        </button>
      </div>
    </fieldset>
  );
}

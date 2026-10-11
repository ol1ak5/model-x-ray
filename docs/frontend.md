# Frontend

The React app (`frontend/`, Vite + TypeScript, plain CSS) is the face of Model X-Ray. It talks only to the HTTP API (`docs/api.md`). Issue: #74.

## Running it

```
scripts/dev.sh
```

One command: installs the npm dependencies if missing, starts the API on `http://localhost:8000` and the app on `http://localhost:5173`, prints both URLs, and stops both on Ctrl+C. Running them separately still works: `scripts/serve.sh`, then `npm --prefix frontend install` once and `npm --prefix frontend run dev`. `VITE_API_URL` points the app at another API, e.g. the deployed one. Tests: `npm --prefix frontend test`; production build: `npm --prefix frontend run build`.

## Screen flow

One page follows the investigation. The left column holds what the user does; the right column holds what the agent found.

1. **Home.** "Your Excel models under the X-Ray." with two actions: Upload your model (picks an `.xlsx`, uploads it with `POST /spreadsheets` and starts the check at once) and Try demo (starts a live check of the demo model from `GET /spreadsheets`; no recorded video). Both call `POST /investigations/stream` without a question: the agent decides where to look. Below: "Go beyond the numbers. See the logic." with the four steps (scan, trace, prove, decide). The example sheet on the right is a static illustration.
2. **Progress.** Each `step` event adds a line with Olya's labels ("Reading the workbook", ..., "Writing the explanation"); a spinner shows while the stream is open. A retry shows the diagnose, test and verify steps again.
3. **Which cell?** When the view is `needs_cell`, the question and candidate cells appear as buttons, with a box for typing any cell (needed when nothing matched). The choice resumes the stream with `{"ref": ...}`.
4. **Review.** The workspace header shows "Model check", the model name and a status chip (Checking…, Needs your input, Review needed, Done); while the sheet is not loaded yet, an animated placeholder says "Scanning your model…". When the view is `needs_review`:
   - **Result card** on top: the outcome badge and a coloured edge ("Root cause found", "No error found", "No confirmed error"), a headline ("Root cause found in P&L!G5"), the target's movement and its value after the correction, the confidence, and the full report where every `ev-N` opens the Evidence tab at that card.
   - **The sheet** under it, then three **tabs**: Cause tree (each input with a bar for its share of the change), Findings (confirmed, open, rejected), Evidence (count shown on the tab).
   - **Your decision** (right column): the proposed change as Current and Proposed formulas, a reason, "This is intentional, do not flag it again", and Approve fix, Edit fix (a formula box, then Test my fix) or Reject.
5. **Done.** After approval, "Download corrected model" (`GET /investigations/{id}/corrected`); otherwise "Closed without changes. Your decision is saved."

Errors from the API or the stream appear as one short sentence in an alert; the user can ask again.

## Code

| File | Role |
|---|---|
| `src/api.ts` | Types matching the API's JSON, the SSE stream reader (`fetch` + `ReadableStream`, because `EventSource` cannot POST), `listSpreadsheets`, `startInvestigation`, `resumeInvestigation`, `correctedFileUrl` |
| `src/App.tsx` | The page and its state: phase (`idle`, `running`, `paused`, `done`), steps, the latest view, the error |
| `src/components/` | `Hero` (home page), `QuestionForm` (the two home actions), `Logo`, `Icon`, `SheetGrid` (the sheet with menu bar, formula bar and highlighted cells, fed by `GET /investigations/{id}/sheet`), `Progress`, `CellChoice`, `Report`, `HypothesisBoard`, `CauseTree`, `EvidencePanel`, `Review`, `Outcome` |
| `src/styles.css` | White and Excel-green tokens, a soft green gradient background, two columns from 960 px, one column on phones |

## Accessibility

Every control has a visible label; sections are named regions; the pause is a `fieldset` with its question as the legend; progress updates are announced (`aria-live`); errors use `role="alert"`; focus outlines are visible; the spinner stops with `prefers-reduced-motion`.

## Tests

`src/test/app.test.tsx` drives the whole page through a fake API that streams real event shapes (`src/test/fakeApi.ts`), the way a user would: by labels, buttons and visible text. It covers a full investigation with approval and download, the cell choice with an intentional rejection, editing the fix, and a failure message.

# Frontend

The React app (`frontend/`, Vite + TypeScript, plain CSS) is the face of Model X-Ray. It talks only to the HTTP API (`docs/api.md`). Issue: #74.

## Running it

```
scripts/serve.sh
npm --prefix frontend install
npm --prefix frontend run dev
```

The API runs on `http://localhost:8000`, the app on `http://localhost:5173` (allowed by the API's default `MODEL_X_RAY_ALLOWED_ORIGINS`). `VITE_API_URL` points the app at another API, e.g. the deployed one. Tests: `npm --prefix frontend test`; production build: `npm --prefix frontend run build`.

## Screen flow

One page follows the investigation. The left column holds what the user does; the right column holds what the agent found.

1. **Ask.** Pick a model (`GET /spreadsheets`) and type a question; example questions fill the box. Investigate starts `POST /investigations/stream`.
2. **Progress.** Each `step` event adds a line with Olya's labels ("Reading the workbook", ..., "Writing the explanation"); a spinner shows while the stream is open. A retry shows the diagnose, test and verify steps again.
3. **Which cell?** When the view is `needs_cell`, the question and candidate cells appear as buttons, with a box for typing any cell (needed when nothing matched). The choice resumes the stream with `{"ref": ...}`.
4. **Review.** When the view is `needs_review`:
   - **Report** with an outcome badge ("Root cause found", "No error found", "No confirmed error"), the target movement, and every `ev-N` as a link to its evidence card.
   - **Hypotheses** in three columns (open, rejected, confirmed), each with cell, error type, claim and confidence.
   - **Cause tree**: every node's prior and current value, its share of the change, a "Suspicious" flag, and the value after the tested fix.
   - **Evidence**: anomalies, expected patterns and the sandbox proof, each addressable by its id.
   - **Your decision**: the proposed fix (old → new), a reason, "This is intentional, do not flag it again", and Approve fix, Edit fix (a formula box, then Test my fix) or Reject.
5. **Done.** After approval, "Download corrected model" (`GET /investigations/{id}/corrected`); otherwise "Closed without changes. Your decision is saved."

Errors from the API or the stream appear as one short sentence in an alert; the user can ask again.

## Code

| File | Role |
|---|---|
| `src/api.ts` | Types matching the API's JSON, the SSE stream reader (`fetch` + `ReadableStream`, because `EventSource` cannot POST), `listSpreadsheets`, `startInvestigation`, `resumeInvestigation`, `correctedFileUrl` |
| `src/App.tsx` | The page and its state: phase (`idle`, `running`, `paused`, `done`), steps, the latest view, the error |
| `src/components/` | `QuestionForm`, `Progress`, `CellChoice`, `Report`, `HypothesisBoard`, `CauseTree`, `EvidencePanel`, `Review`, `Outcome` |
| `src/styles.css` | Colour tokens with a dark theme (`prefers-color-scheme`), one column below 860 px |

## Accessibility

Every control has a visible label; sections are named regions; the pause is a `fieldset` with its question as the legend; progress updates are announced (`aria-live`); errors use `role="alert"`; focus outlines are visible; the spinner stops with `prefers-reduced-motion`.

## Tests

`src/test/app.test.tsx` drives the whole page through a fake API that streams real event shapes (`src/test/fakeApi.ts`), the way a user would: by labels, buttons and visible text. It covers a full investigation with approval and download, the cell choice with an intentional rejection, editing the fix, and a failure message.

# Frontend

The React app (`frontend/`, Vite + TypeScript, CSS Modules) is the face of Model X-Ray. It talks only to the HTTP API (`docs/api.md`). Issues: #74, #128.

## Running it

```
scripts/dev.sh
```

One command: installs the missing dependencies with bun (npm when bun is not on PATH), starts the API on `http://localhost:8000` and the app on `http://localhost:5173`, prints both URLs and which runner it uses, and stops both on Ctrl+C. Running them separately still works: `scripts/serve.sh`, then `cd frontend && bun install` (or `npm --prefix frontend install`) and `bun run dev`. `VITE_API_URL` points the app at another API, e.g. the deployed one. Tests: `cd frontend && bun run test` or `npm --prefix frontend test`; production build: `cd frontend && bun run build`.

## Design system

Three layers, no legacy stylesheet:

| Layer | File | Holds |
|---|---|---|
| Tokens | `src/styles/tokens.css` | Every color as a CSS custom property, the type and spacing scale, radii, motion tokens (`--dur*`, `--ease`), and the glow theme as alternate token values only (`[data-theme="glow"][data-variant=…]`) |
| Base | `src/styles/base.css` | Reset, `body` defaults, focus ring, the `.mono` and `.visually-hidden` utilities, the shared `fade-up` / `grow-x` keyframes, and a global `prefers-reduced-motion` kill switch |
| Components | `src/components/*.module.css` | Everything else, scoped to one component. A component never styles another component's DOM; the two exceptions are `:global([data-theme="glow"])` decoration rules that live in `Hero.module.css` and the forced-light `SheetGrid` island via its `light` prop |

Conventions: sizes in `rem` (hairline `1px` borders and focus outlines excepted), colors only through tokens, motion only through `--dur*`/`--ease` transitions and the two shared keyframes.

Shared primitives in `src/components/`: `Button` (variants `primary`/`secondary`/`ghost`/`danger`; renders a `<button>`, `<label>` with `htmlFor`, or `<a>` with `href`), `Chip` (tones `neutral`/`green`/`red`/`amber`/`blue`, optional `pulse`), `Spinner`, `Alert` (`role="alert"`).

Performance: no new dependencies; the grid, report, detail tabs, progress and the decision panels are wrapped in `React.memo`, and `App` passes stable callbacks (`useCallback`) plus a `useMemo`-ised `Marks` object so streaming `step` events do not re-render them.

## Screen flow

One page follows the investigation. The left column holds what the user does; the right column holds what the agent found.

1. **Home.** "Your Excel models under the X-Ray." with two actions: Upload your model (picks an `.xlsx`, uploads it with `POST /spreadsheets` and starts the check at once) and See it in action (starts a live check of the demo model from `GET /spreadsheets`; no recorded video). Both call `POST /investigations/stream` without a question: the agent decides where to look. Below: "Go beyond the numbers. See the logic." with the four steps (scan, trace, prove, decide) as hairline-separated columns. The example sheet on the right is a static illustration.
2. **Progress.** Each `step` event adds a line with the step labels ("Reading the workbook", ..., "Writing the explanation"); a spinner shows while the stream is open. A retry shows the diagnose, test and verify steps again.
3. **Which cell?** When the view is `needs_cell`, the question and candidate cells appear as buttons, with a box for typing any cell (needed when nothing matched). The choice resumes the stream with `{"ref": ...}`.
4. **Review.** The workspace header shows "Model check", the model name and a status chip (Checking…, Needs your input, Review needed, Done); while the sheet is not loaded yet, an animated placeholder says "Scanning your model…". When the view is `needs_review`:
   - **Report** on top: the outcome chip and a coloured left edge ("Root cause found", "No error found", "No confirmed error"), a headline ("Root cause found in P&L!G5"), the target's movement and its value after the correction, the confidence, and the full report where every `ev-N` opens the Evidence tab at that record.
   - **The sheet** under it, then three **tabs**: Cause tree (each input with a bar for its share of the change, animated on entry), Findings (confirmed, open, rejected), Evidence (count shown on the tab).
   - **Your decision** (right column): the proposed change as Current and Proposed formulas, a reason, "This is intentional, do not flag it again", and Approve fix, Edit fix (a formula box, then Test my fix) or Reject.
5. **Done.** After approval, "Download corrected model" (`GET /investigations/{id}/corrected`); otherwise "Closed without changes. Your decision is saved."

Errors from the API or the stream appear as one short sentence in an alert; the user can ask again.

## Code

| File | Role |
|---|---|
| `src/api.ts` | Types matching the API's JSON, the SSE stream reader (`fetch` + `ReadableStream`, because `EventSource` cannot POST), `listSpreadsheets`, `startInvestigation`, `resumeInvestigation`, `correctedFileUrl` |
| `src/App.tsx` | The page and its state: phase (`idle`, `running`, `paused`, `done`), steps, the latest view, the error |
| `src/theme.ts` | `VITE_THEME` / `VITE_VARIANT` → `data-theme` / `data-variant` on `<html>`; glow is tokens-only |
| `src/components/` | `Hero` (home page, glow decorations), `QuestionForm`, `SheetGrid` (the sheet with menu bar, formula bar and highlighted cells, fed by `GET /investigations/{id}/sheet`), `Progress`, `CellChoice`, `Report`, `HypothesisBoard`, `CauseTree`, `EvidencePanel`, `Review`, `Outcome`, `DetailTabs`; glow-only `AnalysisSummary`, `Waves`; primitives `Button`, `Chip`, `Spinner`, `Alert`; `Logo`, `Icon` |

## Accessibility

Every control has a visible label; sections are named regions; the pause is a `fieldset` with its question as the legend; progress updates are announced (`aria-live`); errors use `role="alert"`; focus outlines are visible; all animation stops under `prefers-reduced-motion` (one global rule in `base.css`).

## Tests

`src/test/app.test.tsx` drives the whole page through a fake API that streams real event shapes (`src/test/fakeApi.ts`), the way a user would: by labels, buttons and visible text. It covers a full investigation with approval and download, the cell choice with an intentional rejection, editing the fix, and a failure message. Because it queries by role and text, it pins the information architecture while the visual layer changes freely.

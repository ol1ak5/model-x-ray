# Frontend

The React app (`frontend/`, Vite + TypeScript) is the face of Model X-Ray. It talks only to the HTTP API (`docs/api.md`). Issues: #74, #128, #209.

The design was agreed on static prototypes first (26 Oct 2026): the landing page and the model check page. The previous workspace (sheet with wiring arrows, step rail, facts bar) was replaced; its code is in git history before #209.

## Running it

```
scripts/dev.sh
```

One command: installs the missing dependencies with bun (npm when bun is not on PATH), starts the API on `http://localhost:8000` and the app on `http://localhost:5173`, and stops both on Ctrl+C. `VITE_API_URL` points the app at another API. A production build calls the API on its own origin (`docs/deployment.md`). Tests: `npm --prefix frontend test`; build: `npm --prefix frontend run build`.

## Design

| File | Holds |
|---|---|
| `src/styles/tokens.css` | The palette as CSS custom properties: ink and greys, the three greens and the `--band` gradient, red for errors, blue for work in progress and for the cells that depend on an error, `--wait` for a step waiting on the reviewer; Geist and Geist Mono |
| `src/styles/base.css` | Reset, focus ring, `.visually-hidden`, `[hidden]`, and a global `prefers-reduced-motion` switch |
| `src/styles/site.css` | What both pages share: the column (`.wrap`, 78rem), the top bar, the brand, the rounded `pill` buttons, the footer, the moving line background (`.live`) and the one-line alert |
| `src/styles/landing.css`, `src/styles/check.css` | One page each, every selector scoped under `.landing` or `.check` |

The rules from the owner: no rounded boxes or cards around blocks; content is separated by spacing, type and thin lines, and a frame is kept only for things that really are separate objects (the spreadsheet window, the dialog). Titles of sections are small green capitals. The page background is a field of thin green lines drawn on a canvas (`components/Wave.tsx`), fixed behind both pages and still under `prefers-reduced-motion`.

## The landing page (`src/landing/`)

Hero ("Your AI agent for financial model analysis.") with Try the demo and Upload your model, and an animated spreadsheet (`HeroSheet`): rows are scanned, D4 turns red as a typed value, its inputs and EBITDA are traced, the fix `=D2+D3` recalculates D4 and then D6, with "Error detected, Checks run, Fixed" lighting up underneath. Below, in order: "Did you know that?" (four real cases whose amounts roll in like a slot machine), Our answer (Nemotron reasons, the engine calculates, three numbers), How it works (four phases that light up in turn), Strengths, Stack (chips that cycle and explain each piece), FAQ, and the closing green band. Blocks fade in as they reach the screen; without `IntersectionObserver` (tests) they are simply shown.

Try the demo starts a live check of `PPA_Model_Europe` (the PPA evaluation model with three planted errors), or of the first model `GET /spreadsheets` lists when that one is not served. Upload your model validates the file with `POST /spreadsheets` and starts the check with the file in hand; a refused file is one red line under the buttons.

## The model check page (`src/check/`)

- **Header.** The file name, its sheets as links, and on the right the state ("Checking the model", "1 error detected", "No errors found", "Review complete") over one line that says what is happening ("Tracing the formulas", "Waiting for your decision", "1 fix saved to a new copy").
- **Progress.** Five phases (`src/progress.ts`): Read, Investigate, Prove, Approve, Review complete. They follow the streamed steps: Read is done after `map_model`, Investigate after `diagnose`, Prove after `explain`. A phase in progress spins blue, Approve pulses blue while the review waits for the reviewer, and done phases are green with a check.
- **Errors detected.** Built from the view by `src/findings.ts`, and shown once Prove is done. Each error is a row (cell, a sentence such as "COGS 2025A has the wrong sign" made from the sheet window's row label, column header and the error type, and its status: Error detected, Fixed, Not an error) that opens into Where (with Open in the sheet), Error (the formula as it is), Solution (the tested formula), Explanation (the report without its `ev-N` citations, with semicolons turned into full stops and arrows into "from ... to ...", the house style the prompts and the engine's own evidence text also follow), and the actions. Rows open independently; type filters appear above the list.

  The agent's seven error types have one name each on the page, used by the filters, the FAQ and the sentence of each error (`TYPES` in `src/findings.ts`); `tests/test_view_contract.py` fails when the agent gains a type the page cannot name or the FAQ drifts:

  | Agent (`error_type`) | Page | Sentence |
  |---|---|---|
  | `typed_value` | Typed value | is a typed number |
  | `wrong_reference` | Wrong reference | points to the wrong cell |
  | `sign_inconsistency` | Flipped sign | has the wrong sign |
  | `range_inconsistency` | Incomplete range | adds up the wrong range |
  | `period_inconsistency` | Wrong period | uses the wrong period |
  | `logic_error` | Logic error | breaks the logic of its line |
  | `input_outlier` | Unusual input | is out of line with the rest |
- **One error after another.** A run investigates one error. When a decision settles it (approve or reject), the page starts the next round on its own: after an approval it sends the corrected file it just received, and it always sends `set_aside` with every cell settled so far (`docs/api.md`). Settled errors stay in the list with their status while the next round runs ("Looking for the next error"). The review is complete when a round finds nothing more, or after six errors; the download then offers the copy from the last approved fix, which carries every fix approved before it.
- **Decisions.** Approve fix (the button says "Testing in a copy…" while the server writes the copy), Edit fix (the reviewer's formula, sent as an `edit` decision and tested again before it can be approved), Reject (then "It's not an error", with "Never flag this cell again" sent as `intentional`). Once every error is settled the page offers the corrected workbook from the view's `corrected_file`.
- **Sheets.** "Sheets in this file" and "Open in the sheet" open the real workbook (`POST /workbook`) in a dialog that looks like Excel: values as Excel shows them in General format, the formula of the selected cell in the formula bar, arrow keys to move, tabs to switch sheets. Opened from an error, the error cell is red and every cell whose value the tested fix changes is blue, with a line saying the marks exist only on screen.
- **Stopped states.** A failed request is one red line under the header; a check cut short by a reload says Interrupted and offers Run again. `components/Boundary.tsx` catches a render error on the check page so the worst case is a sentence and a way back, never a white page.

- **Ask the agent.** Under each open error a one-line field asks the agent about it (`POST /investigations/{id}/ask`). The conversation is a thread of lines, "You:" then "Model X-Ray:" in green, each new question on its own line, with "thinking…" while the answer is on its way; the whole conversation so far is sent with each question. The field goes away once the fix is accepted.

## State in the browser

`src/App.tsx` keeps the run: the streamed steps, the latest view, the sheet window, the phase, the errors settled in earlier rounds, the set-aside cells, the view that wrote the latest corrected copy, and the uploaded (or latest corrected) `File` in memory (re-sent with every request, `docs/api.md`). Runs are stored by `src/storage.ts` (`docs/persistence.md`); a stored run with a view reopens on the check page after a reload.

## Recorded demo runs

`?story=workspace`, `?story=running` and `?story=done` (dev only) open the check page on recorded views from `src/test/recorded/`, exported from a live API by `tools/export_demo_run.py`. `scripts/screenshots.sh` renders `?story=done`.

## Tests

`src/test/app.test.tsx` drives both pages through a fake API that streams real event shapes (`src/test/fakeApi.ts`), by labels, roles and visible text: the landing and the demo start, a refused upload, a full check from upload to the downloaded file (progress states, the error's facts, the explanation without citations, the request bodies with the file), editing the fix, a rejection marked never flag again, a review that moves on to the next error after each decision (the corrected file and the set-aside cells in each new request), a model with nothing to fix, the sheet viewer with its marks and formulas, a failure message, and the way back. `src/test/persistence.test.tsx` covers runs restored after a reload, interrupted runs and the storage budget; `src/test/crash.test.tsx` makes the check page throw and expects a readable way out.

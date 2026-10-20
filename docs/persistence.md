# Where a run lives: the browser

Decision, 18 Oct 2026: an investigation's conversation and state are stored in the visitor's own browser (`localStorage`), and the server keeps no investigation and no database. The API becomes a function of the request: it either runs an investigation or continues one, and answers with the new state for the browser to keep.

This supersedes the Postgres/Supabase direction of #72 and removes persistence as a reason for #75 to depend on Supabase. The measurements behind the decision are in "What this replaces" below.

## What the browser stores

One entry per investigation under a versioned key, `model-x-ray:runs:v1`:

| Field | Why |
|---|---|
| `id`, `spreadsheetId`, `name`, `question`, `startedAt`, `updatedAt` | identify the run and let the UI list it |
| `steps` | the pipeline progress the app already streams |
| `view` | the investigation view the API returns (`InvestigationView`): the whole picture the UI draws |
| `sheet` | the sheet window around the target, so the grid survives a reload |

`id` is minted by the browser (`newRunId`) so a run is stored from its first streamed step; the investigation id the API returns travels inside `view`. A second entry, `current`, points at the run on screen: "Check another model" clears the pointer and keeps the history.

Measured size for the demo model: `view` 11 KB and `sheet` 6 KB, so about 17 KB per run and roughly 300 runs inside the 5 MB per-origin quota. A real model is not the demo model: a 200-row window of copied columns measured 290 KB per run, so 18 such runs already fill the budget below. Rules the code follows (`frontend/src/storage.ts`):

- Keep the newest 25 runs and at most `STORAGE_BYTES` (2 MB) of JSON, leaving room in the ~5 MB quota for the rest of the app. Pruning drops the oldest run that is not the one on screen, one at a time until the payload fits.
- Keep the run on screen whatever happens: when it alone exceeds the budget, its `sheet` goes first (the `view` and the report survive and the reload still restores the facts, refetching the window from the API), then its `view`. A run that fits nothing is dropped from storage rather than losing the write silently.
- A write that still fails with `QuotaExceededError` (another tab, a smaller quota than assumed) prunes further in the same order before giving up, and only removes the key when nothing is left to give up.
- `localStorage` holds strings only: the corrected `.xlsx` is **downloaded** when the visitor approves, never stored. A real model can be 10 MB, base64 would not fit, and keeping it would be a second copy of deal data.
- Write whenever the picture changes (each streamed step, each view, each decision). A run emits a handful of events and the payload grows to a couple of KB, so a synchronous write is cheaper than the bookkeeping a debounce would need.
- A restored run asks the API for a fresh sheet window and keeps the stored one when the API cannot answer, so the grid survives both a reload and a server restart.
- A value with another version, or that is not our shape, is ignored: the app falls back to the home page. A stored run missing `view` or `sheet` is normalized to `null` on read, so a stale entry can never leave the app half-restored. Storage that refuses to work (private mode) leaves the app running without history.

## What the server does

| Endpoint | Change |
|---|---|
| `POST /investigations`, `/investigations/stream` | unchanged: run the graph, answer the view and the steps |
| `POST /investigations/{id}/resume` | keeps its path; its body gains the carried state, and a request with that state continues from it even when this process never saw the id |
| `GET /investigations/{id}/sheet` | still resolved through the process. The browser keeps the window it was shown, so a continuation brings its own sheet |

The continuation is small and fully determined by the decision: `approve` runs only `apply_fix` and answers the corrected file's bytes, `reject` runs no model at all, `edit` runs `test → verify → explain` and pauses again. That is `run_continuation` in `graph.py`: the same nodes and the same checks as the full graph, compiled from an entry point after the review, so nothing needs a live thread and the served app needs no checkpointer at all (tests keep the in-memory one).

The API treats that state as untrusted input: `carried_state` keeps only the fields an investigation carries, requires the spreadsheet id and the question, refuses a list or an object of the wrong shape with `400`, and loads the workbook from the spreadsheet id instead of trusting anything in the state.

Two things a carried state cannot do. The cell-choice pause carries no decision, so it still needs the process that asked the question (#138 removes that pause). An uploaded model is only on the server while its file is, so a continuation needs the upload to still be there (or the file re-sent); a demo model is read from the models folder every time.

Why not the other two obvious carriers:

- **A cookie.** About 4 KB per cookie and silently dropped above that, and auto-attached to every request to the domain, so the run would ride along in headers on calls that do not need it. A run is 17 KB.
- **Handing back the serialized checkpoint.** Works, but it means carrying the checkpoint *and* its pending writes so a fresh saver can be rehydrated, in order to save a few nodes of work. Only worth it if a later change needs true time travel or partial re-runs.

## Uploaded models and the privacy claim

The landing says "Your file stays private". The server now behaves that way (`api.Uploads`, `UPLOAD_TTL` 30 minutes):

- `POST /spreadsheets` writes the `.xlsx` into `uploads/` and registers it as held. The file lives only while its run does: when the run finishes (approve or reject) the upload is deleted, removed from the source so its id stops resolving, and the workbook is no longer readable.
- An abandoned upload — the visitor uploads, starts a run and never returns — is swept once it is older than the TTL. The sweep runs on the requests that matter (`GET /spreadsheets`, the sheet window), so there is no background thread and no scheduler; the injected clock keeps it testable.
- The corrected copy is served once. `GET /investigations/{id}/corrected` answers the file and deletes it when the download finishes, so `corrected/` does not accumulate approved fixes. A copy the visitor never downloads stays until the process restarts; that is the remaining hole and it is filed as an issue.

What the visitor keeps is the run in their own browser (above), and what they get is the corrected workbook in their own downloads. The server keeps neither.

## What this replaces

Measured before the decision, on the real workbook and the real SQLite checkpointer (`tests/test_persistence.py`):

- The checkpointer was **written but never looked up**: `create_app`'s `graphs` dict answered only the ids that process had started, so a second app on the same file answered `404` for the view and for the resume. A paused investigation inside `checkpoints.db` (the dev file: 5.3 MB, 614 checkpoints, 1965 writes) was unreachable after a restart, so #72 as written would have bought nothing.
- Only the long-term memory was durable end to end, and its namespace had no visitor in it, so one visitor's "intentional" rejection suppressed that cell for every later visitor on the same demo model. The dev `memory.db` already held `findings.demo / P&L!G5`.
- Uploads and the usage cap lived in process memory, so a restart forgot them and several instances would each count their own.

## Still open

- Whether the agent's own memory (model maps, overrides, past fixes) also moves into the browser (#144). It would fix the cross-visitor leak above and make memory private by construction, at the cost of the agent no longer learning anything for the next visitor.
- Whether the usage cap moves to the browser as well; it is the only remaining reason for server-side state, and an in-memory cap is enough for one container.
- A way for a visitor to clear their history and their memory from the UI. The store already has `deleteRun` and `clearRuns`; nothing calls them yet.
- Corrected copies that are never downloaded are not swept yet (they depend on the sandbox's wall-clock mtime, not the upload clock).
- `/{id}/sheet` and `/{id}/corrected` still resolve through the process, so a visitor who reloads the sheet (rather than keeping the window the browser stored) needs the process that ran the investigation.

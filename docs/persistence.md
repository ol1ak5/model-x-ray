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

Measured size for the demo model: `view` 11 KB and `sheet` 6 KB (`frontend/src/test/recorded/`), so about 17 KB per run and roughly 300 runs inside the 5 MB per-origin quota. Rules the code follows:

- Keep the newest 25 runs, oldest evicted first, and evict on `QuotaExceededError` before giving up on a write.
- `localStorage` holds strings only: the corrected `.xlsx` is **downloaded** when the visitor approves, never stored. A real model can be 10 MB, base64 would not fit, and keeping it would be a second copy of deal data.
- `localStorage` is synchronous: write on `view` events and on decisions, not on every streamed step.
- A corrupt or foreign value, or storage that refuses to work (private mode), degrades to "no history" and never breaks the app.
- A `version` field inside the value, so a later shape can migrate or be dropped.

## What the server does

| Endpoint | Change |
|---|---|
| `POST /investigations`, `/investigations/stream` | unchanged: run the graph, answer the view and the steps |
| `POST /investigations/{id}/resume` | keeps its path but its body gains the carried state; it no longer resumes a live LangGraph thread, it continues from a state the browser hands back |
| `GET /investigations/{id}/sheet` | comes from the carried state, or from the model the browser names, never from a stored investigation |

The continuation is small and fully determined by the decision: `approve` runs only `apply_fix` and answers the corrected file's bytes, `reject` runs no model at all, `edit` runs `test → verify → explain` and pauses again. The first pause (choosing a cell) continues the same way. That is a handful of nodes over a state the request carries, so nothing needs a live thread and the served app needs no checkpointer at all (tests keep the in-memory one).

The API must treat that state as untrusted input: check its shape before running a node over it.

Why not the other two obvious carriers:

- **A cookie.** About 4 KB per cookie and silently dropped above that, and auto-attached to every request to the domain, so the run would ride along in headers on calls that do not need it. A run is 17 KB.
- **Handing back the serialized checkpoint.** Works, but it means carrying the checkpoint *and* its pending writes so a fresh saver can be rehydrated, in order to save a few nodes of work. Only worth it if a later change needs true time travel or partial re-runs.

## Uploaded models and the privacy claim

The landing says "Your file stays private", and today that is not true: `POST /spreadsheets` writes the `.xlsx` into `uploads/` and nothing ever deletes it (the only `unlink` is cleanup after a parse failure), while every approved fix accumulates in `corrected/`. With the run in the browser the server should hold nothing: delete an upload when the run ends (or after a short TTL), and answer the corrected copy in the response body instead of storing it.

## What this replaces

Measured before the decision, on the real workbook and the real SQLite checkpointer (`tests/test_persistence.py`):

- The checkpointer was **written but never looked up**: `create_app`'s `graphs` dict answered only the ids that process had started, so a second app on the same file answered `404` for the view and for the resume. A paused investigation inside `checkpoints.db` (the dev file: 5.3 MB, 614 checkpoints, 1965 writes) was unreachable after a restart, so #72 as written would have bought nothing.
- Only the long-term memory was durable end to end, and its namespace had no visitor in it, so one visitor's "intentional" rejection suppressed that cell for every later visitor on the same demo model. The dev `memory.db` already held `findings.demo / P&L!G5`.
- Uploads and the usage cap lived in process memory, so a restart forgot them and several instances would each count their own.

## Still open

- Whether the agent's own memory (model maps, overrides, past fixes) also moves into the browser. It would fix the cross-visitor leak above and make memory private by construction, at the cost of the agent no longer learning anything for the next visitor.
- Whether the usage cap moves to the browser as well; it is the only remaining reason for server-side state, and an in-memory cap is enough for one container.
- A way for a visitor to clear their history and their memory from the UI.

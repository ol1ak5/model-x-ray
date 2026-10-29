# HTTP API

Implementation: `src/model_x_ray/api.py`. Tests: `tests/test_api.py`. Issue: #73.

The API wraps the investigation graph so the React app (#74) can start an investigation, show its one pause (approve, edit or reject the fix) and resume it.

## Running it locally

```
uv run tools/generate_dataset.py --output models --per-set 2
scripts/serve.sh
```

The first command fills `models/` with the clean base model and planted-error variants (any `.xlsx` you drop there works too; subfolders become part of the id, e.g. `type1/variant-000`). The second starts the API on `http://localhost:8000`; `http://localhost:8000/docs` is FastAPI's interactive page for trying every endpoint. `models/`, `corrected/` and `checkpoints.db` are git-ignored.

`app_from_env()` (`src/model_x_ray/server.py`) builds the real app from `.env`:

| Setting | Default | Meaning |
|---|---|---|
| `MODEL_X_RAY_MODELS_DIR` | `demo_models` | Folder with the demo models anyone can try (the repo ships `demo_models/PPA_Model_Europe.xlsx`, the PPA evaluation model the web demo checks, with three planted errors, and `demo_models/demo.xlsx`, a synthetic three-sheet model with a sign flip on `P&L!G5` and a typed value on `P&L!I6` that the tests use); point it at `models/` to expose the benchmark set locally |
| `MODEL_X_RAY_UPLOAD_DIR` | `uploads` | Where uploaded models are saved while their run is alive; each file is deleted when the run ends or after the upload TTL |
| `MODEL_X_RAY_OUTPUT_DIR` | `corrected` | Where approved corrected copies are saved |
| `MODEL_X_RAY_COPY_TTL` | `1800` | Seconds a corrected copy waits for its download before the sweep removes it |
| `MODEL_X_RAY_CHECKPOINTS` | `checkpoints.db` | SQLite checkpointer file (Postgres on Supabase in the deployed app, #72) |
| `MODEL_X_RAY_ALLOWED_ORIGINS` | `http://localhost:5173` | Comma-separated web addresses allowed to call the API from a browser (CORS): the React dev server, then the Vercel URL. Any `localhost` port is allowed on top of this list, so a dev server that had to fall back to `5174` (or `4173` after a preview build) still works; the deployed URL must be listed here |
| `MODEL_X_RAY_MEMORY` | `memory.db` | SQLite long-term memory: model maps, intentional overrides, past fixes (Postgres on Supabase in the deployed app, #72) |
| `DEMO_MAX_PER_VISITOR` / `DEMO_MAX_PER_DAY` | `5` / `100` | The usage cap |

Which of these actually survive a restart, and which deployment needs a database, is recorded in `docs/persistence.md`.

Models come from the role registry: Super for the Investigator, Verifier and locate, Lightning for the mapper.

## Building the app

`create_app(source, sandbox, models, checkpointer, cap)` returns a FastAPI app. Everything it needs is passed in, so tests use the demo workbook, scripted models and an in-memory checkpointer, and production passes Token Factory models and the Postgres checkpointer (#72).

- `AgentModels(llm, verifier=None, locator=None, mapper=None)`: one model per role, the same parameters as `run_investigation`.
- `public=False`: the deployed demo sets it, and it changes two things. The API reference (`/docs`, `/redoc`, `/openapi.json`) is not published, and the routes that spend credits (`POST /investigations`, `/investigations/stream`, `/investigations/{id}/resume`, `/resume/stream`, `/ask`) answer only a request whose `Origin` or `Referer` is the deployment's own host (or an entry in `MODEL_X_RAY_ALLOWED_ORIGINS`), with `403 same_origin_required` otherwise. The page keeps working because its requests carry the origin; a bare `curl` does not. This is not a security boundary — a client can forge the header — it removes the accidental and scripted use while the WAF limit and the usage cap do the rest.
- `UsageCap(per_visitor, total)`: investigations per visitor (by client IP) per day, and for everyone per day. The demo must stay open to judges until 15 Dec and every run spends our Token Factory credits, so the cap is checked before the graph runs and counted once the workbook is loaded and the investigation exists (a typo in the spreadsheet id costs nothing; a run that fails halfway still counts, because it already spent credits).

## Endpoints

| Method and path | Body | Answer |
|---|---|---|
| `POST /investigations` | `{"spreadsheet_id", "question", "set_aside"}`; `question` and `set_aside` are optional | `201` and the investigation view. Without a question the agent checks the whole model (see below). `set_aside` lists cells this check must leave alone: the other suspects from `POST /suspects` when the page investigates them in parallel. Each goes into `known_overrides` with its current content and the reason "Settled or checked separately in this review", so the locator skips it and the Investigator does not propose it |
| `GET /health` | | `{"status": "ok"}` for the host's health check |
| `GET /spreadsheets` | | The demo models: `[{"id", "sheets"}]`. Uploads are never listed, so one visitor never sees another's file, and each call first sweeps uploads older than the TTL |
| `POST /spreadsheets?name=My%20model.xlsx` | The raw `.xlsx` bytes | `201` and `{"id", "name", "sheets"}`; `.xlsx` only, up to 10 MB, checked by opening it; the id is `upload-` plus the first 16 hex digits of the file's SHA-256, so the same bytes get the same id on every server instance, and a name like `../x.xlsx` cannot escape the folder. The file is deleted when the run finishes (approve or reject) or after `MODEL_X_RAY_UPLOAD_TTL` seconds, whichever comes first, and its id stops resolving |
| `GET /investigations/{id}` | | The investigation view |
| `POST /investigations/{id}/ask` | `{"question", "state", "history"}`: the reviewer's question (up to 500 characters), the view the browser kept, and the conversation so far as `[{"role": "user" or "agent", "text"}]` (the last 8 turns are used) | `{"answer"}`: one to four plain sentences from the explain model, grounded only in the run's facts (cell, formulas, the tested fix, the numbers it changed named by line and period, evidence, report). Stateless like `resume`; `400` without a state or a question; its own daily limit, `DEMO_MAX_QUESTIONS_PER_VISITOR` (30) and `DEMO_MAX_QUESTIONS_PER_DAY` (500), separate from the checks |
| `POST /suspects` | `{"spreadsheet_id"}`, or the multipart form with the visitor's `file` | `{"cells": [...]}`: up to six cells the free scan flags (row and column patterns, typed values, last-period breaks, table checks), in the order the locator would take them. No AI is called |
| `POST /workbook` | `{"spreadsheet_id"}`, or the multipart form with the visitor's `file` | Every sheet of the workbook for the page's viewer: `{"sheets": [{"name", "rows", "columns", "cells": [{"ref", "value", "formula"}]}]}`. Values are calculated by the engine (`#ERROR` when a formula cannot be), only cells with content are sent, and each sheet is capped at 300 rows and 40 columns |
| `GET /investigations/{id}/sheet` | | The sheet window around the target: header row, rows, before/after values, so the page can draw the model (404 once the workbook is gone) |
| `GET /investigations/{id}/corrected` | | The corrected `.xlsx` after approval, served once: the file is removed from the server when the download finishes, so a second call answers 404. A copy nobody downloads is deleted after `MODEL_X_RAY_COPY_TTL` (1800 s), swept on `GET /spreadsheets` |
| `POST /investigations/{id}/resume` | A cell choice `{"ref": "P&L!H8"}` or a decision `{"action": "approve" \| "edit" \| "reject", "reason", "patch", "intentional"}` (`intentional: true` with `reject` remembers the cell as deliberate, see `docs/agent-architecture.md` §Memory). An `edit` patch is normalized and calculated before it is accepted: `-G4*Assumptions!$C$5` becomes `=-G4*Assumptions!$C$5`, a plain number stays a number, and a formula that cannot be calculated in that cell answers `422` with a sentence naming the cell, leaving the investigation paused at `human_review`. `state` carries the investigation view the browser kept, so a server that never saw this id can still continue it (see below) | The investigation view after the graph continued |
| `POST /investigations/stream` | Same as `POST /investigations` | A live stream of progress events, then the view |
| `POST /investigations/{id}/resume/stream` | Same as `resume` | A live stream of progress events, then the view |

## Live progress

The two `/stream` endpoints run the graph with `graph.stream(..., stream_mode="updates")` and answer with Server-Sent Events (`text/event-stream`), so the app can show each step as it finishes:

```
event: step
data: {"step": "locate", "label": "Finding the cell"}

event: step
data: {"step": "diagnose", "label": "Looking for the root cause"}

event: view
data: {"id": "...", "status": "needs_review", ...}
```

- One `step` event per finished node, with a plain-English label from `STEP_LABELS`. A retry shows `diagnose`, `test` and `verify` again, so the user sees the agent trying again.
- The last event is `view` (the same JSON as the other endpoints) or `error` (`{"status", "detail"}`, see Errors).
- Streaming uses `POST` because starting and resuming carry a body and do the work; the browser reads the stream with `fetch` and a stream reader (`EventSource` only supports `GET`). This replaces the `GET /investigations/{id}/events` sketched in #73.
- Checks that can fail before anything runs (the usage cap, an unknown spreadsheet, an unknown id) answer with a normal HTTP error instead of a stream.

## Checking a model without a question

The main use is "check my model": no question needed. `locate` then calls `check_target` (`agents/locator.py`):

1. `scan_model` (`rules.py`) looks at every cell under a period header with a line label and flags the ones that break their row: a typed number with a formula to its left in the same row (a hardcode among formulas; typed history on the left of the forecasts is normal and never flagged), or a formula whose reference pattern differs from the row's. Side columns without a period (constants, sums, units) are ignored.
2. The flagged cell with the most dependents wins; the target is the closest labelled period cell it moves (a typed Opex is investigated through EBITDA), and the question records why: "Check the model: EBITDA 2027E depends on P&L!H7, which is a typed value where the row uses ...".
3. When nothing breaks a pattern, the target is the model's main output (the calculated line with the most inputs, ratios excluded) in its largest relative move, and a clean model ends with "No error found" and its drivers.

On the planted benchmark models the scan lists exactly the planted cells, including mixed errors. One run investigates one target; the other flagged cells are listed for a follow-up run (see #103).

## The investigation view

Every endpoint answers with the same JSON, built by `investigation_view` from the graph's checkpoint:

- `id`: also the LangGraph `thread_id`, so one investigation is one thread.
- `status`: `needs_review` (paused in `human_review`) or `done`.
- `pause`: the value the graph passed to `interrupt()`: the report and patch to approve. `null` when not paused.
- The public state fields: `spreadsheet_id`, `question`, `target_choice`, `decisions` (the candidates, the chosen cell and why), `model_map`, `known_overrides`, `past_findings`, `target`, `causal_tree`, `contributions`, `hypotheses`, `evidence`, `verifications`, `patch`, `report`, `corrected_copy_id`, `run_log`, `attempts`. LangChain messages are never sent. These are also the fields a browser can hand back as `state` to continue an investigation the server has forgotten.

## Continuing without a thread

`resume` looks the id up in the process that started the investigation. When the request also carries the `state` the browser kept, that lookup is not needed: the server builds a small continuation graph over the carried state and the decision, with the same nodes and the same checks, and runs only the nodes after the review. `approve` runs `apply_fix` alone, `reject` runs no model at all, `edit` runs `test → verify → explain` and pauses for review again. `/{id}/sheet` and `/{id}/corrected` still resolve through the process, which is why the final `view` event of every stream also carries what they would answer (see "Requests that carry the model" below).

The state is untrusted input. `carried_state` keeps only the fields an investigation carries, requires the spreadsheet id and the question, and answers `400` for a list or an object of the wrong shape. The workbook is never taken from the state but loaded from the spreadsheet id, so an uploaded model has to still be on the server. A cell choice is no longer part of the API: `locate` picks the cell itself and records the choice in `target_choice`.

## Requests that carry the model

On Vercel (`docs/deployment.md`) two requests from one visitor can reach two instances that share nothing, so an uploaded model and the corrected copy cannot wait on the server between requests. The two stream endpoints therefore also accept `multipart/form-data` with two fields:

| Field | Content |
|---|---|
| `request` | The JSON body the endpoint takes as JSON (`{"question"}` to start, the decision plus `state` to resume) |
| `file` | The visitor's `.xlsx` |

The server stores the file under its content id (the same `upload-<sha256>` as `POST /spreadsheets`) for the length of the request, so `spreadsheet_id` can be left out when starting. A resume whose file has another content id than the carried state's `spreadsheet_id` is refused with `400` ("This is not the file the review started on"), so a state cannot be replayed against a different workbook. A demo model needs no file: JSON requests work as before.

The final `view` event of both streams adds two fields, so the browser needs no follow-up request:

| Field | Content |
|---|---|
| `sheet` | The sheet window `GET /investigations/{id}/sheet` would answer, or `null` before the target is known |
| `corrected_file` | After an approval, `{"name", "base64"}`: the corrected workbook itself; otherwise `null` |

The daily cap counts visitors by the first address in `x-forwarded-for` when the platform sets it, and by the connection's address otherwise.

## Errors

Users never see a traceback. Every failure is answered as `{"detail": "<one short sentence>", "code": "<stable id>"}`: `friendly_error(error)` turns any exception into a status, a code and the sentence, dedicated handlers answer raised refusals, the request-validation error and unexpected exceptions, and the streams send the same three fields as their `error` event. The page switches on `code` to say what the reader can do — wait a minute, come back tomorrow, send another file, or tell the team — instead of guessing from the prose. Only unexpected errors are logged with the full traceback, for the team.

| Status | Codes | When |
|---|---|---|
| `400` | `missing_model`, `unknown_model`, `upload_rejected`, `workbook_unreadable`, `missing_action`, `missing_question`, `question_too_long`, `bad_state`, `resume_file_mismatch`, `invalid_request`, `bad_request` | The request or the workbook cannot lead to a check |
| `403` | `same_origin_required`, `forbidden` | The public deployment answers only the page it serves |
| `404` | `unknown_investigation`, `no_target`, `no_corrected_copy`, `upload_disabled` | The id, the cell or the file is not here |
| `409` | `finished_investigation` | Resume on a finished investigation |
| `413` | `upload_too_large` | Above the 10 MB body limit |
| `422` | `unsupported_formula`, `formula_error`, `invalid_fix`, `invalid_request` | The engine cannot calculate the formula, or the fix does not work |
| `429` | `usage_cap` | A daily limit is reached |
| `502` | `provider_error`, `provider_malformed` | Token Factory returned an error, or the answer did not fit the expected format |
| `503` | `provider_timeout`, `provider_busy`, `provider_auth`, `provider_unreachable`, `provider_failure` | Token Factory timed out, is overloaded, rejected the key, or cannot be reached |
| `500` | `unexpected` | Anything else |

A start-up check runs before the server binds: a missing `NEBIUS_API_KEY`, a models folder that does not exist or holds no `.xlsx`, and a folder the server cannot write are reported one per line, and the process stops instead of serving requests that would fail later.

## Not yet

- An investigation id belongs to the process that started it, so `GET /investigations/{id}` and `/{id}/sheet` answer `404` for an id this process never saw, even with the checkpoint on disk: the checkpointer is written but never looked up. A browser that kept its state can still finish the review, because `resume` continues from that state when the id is unknown. `docs/persistence.md` records the decision.

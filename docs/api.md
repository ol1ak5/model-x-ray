# HTTP API

Implementation: `src/model_x_ray/api.py`. Tests: `tests/test_api.py`. Issue: #73.

The API wraps the investigation graph so the React app (#74) can start an investigation, show its two pauses (which cell, approve the fix) and resume them.

## Running it locally

```
uv run tools/generate_dataset.py --output models --per-set 2
scripts/serve.sh
```

The first command fills `models/` with the clean base model and planted-error variants (any `.xlsx` you drop there works too; subfolders become part of the id, e.g. `type1/variant-000`). The second starts the API on `http://localhost:8000`; `http://localhost:8000/docs` is FastAPI's interactive page for trying every endpoint. `models/`, `corrected/` and `checkpoints.db` are git-ignored.

`app_from_env()` (`src/model_x_ray/server.py`) builds the real app from `.env`:

| Setting | Default | Meaning |
|---|---|---|
| `MODEL_X_RAY_MODELS_DIR` | `demo_models` | Folder with the demo models anyone can try (the repo ships `demo_models/demo.xlsx`, a synthetic model with three mixed planted errors); point it at `models/` to expose the benchmark set locally |
| `MODEL_X_RAY_UPLOAD_DIR` | `uploads` | Where uploaded models are saved |
| `MODEL_X_RAY_OUTPUT_DIR` | `corrected` | Where approved corrected copies are saved |
| `MODEL_X_RAY_CHECKPOINTS` | `checkpoints.db` | SQLite checkpointer file (Postgres on Supabase in the deployed app, #72) |
| `MODEL_X_RAY_ALLOWED_ORIGINS` | `http://localhost:5173` | Comma-separated web addresses allowed to call the API from a browser (CORS): the React dev server, then the Vercel URL |
| `MODEL_X_RAY_MEMORY` | `memory.db` | SQLite long-term memory: model maps, intentional overrides, past fixes (Postgres on Supabase in the deployed app, #72) |
| `DEMO_MAX_PER_VISITOR` / `DEMO_MAX_PER_DAY` | `5` / `100` | The usage cap |

Models come from the role registry: Super for the Investigator, Verifier and locate, Lightning for the mapper.

## Building the app

`create_app(source, sandbox, models, checkpointer, cap)` returns a FastAPI app. Everything it needs is passed in, so tests use the demo workbook, scripted models and an in-memory checkpointer, and production passes Token Factory models and the Postgres checkpointer (#72).

- `AgentModels(llm, verifier=None, locator=None, mapper=None)`: one model per role, the same parameters as `run_investigation`.
- `UsageCap(per_visitor, total)`: investigations per visitor (by client IP) per day, and for everyone per day. The demo must stay open to judges until 15 Dec and every run spends our Token Factory credits, so the cap is checked before the graph runs and counted once the workbook is loaded and the investigation exists (a typo in the spreadsheet id costs nothing; a run that fails halfway still counts, because it already spent credits).

## Endpoints

| Method and path | Body | Answer |
|---|---|---|
| `POST /investigations` | `{"spreadsheet_id", "question"}`; `question` is optional | `201` and the investigation view. Without a question the agent checks the whole model (see below) |
| `GET /health` | | `{"status": "ok"}` for the host's health check |
| `GET /spreadsheets` | | The demo models: `[{"id", "sheets"}]`. Uploads are never listed, so one visitor never sees another's file |
| `POST /spreadsheets?name=My%20model.xlsx` | The raw `.xlsx` bytes | `201` and `{"id", "name", "sheets"}`; `.xlsx` only, up to 10 MB, checked by opening it; the saved name is generated, so a name like `../x.xlsx` cannot escape the folder |
| `GET /investigations/{id}` | | The investigation view |
| `GET /investigations/{id}/corrected` | | The corrected `.xlsx` after approval (404 before) |
| `POST /investigations/{id}/resume` | A cell choice `{"ref": "P&L!H8"}` or a decision `{"action": "approve" \| "edit" \| "reject", "reason", "patch", "intentional"}` (`intentional: true` with `reject` remembers the cell as deliberate, see `docs/agent-architecture.md` §Memory) | The investigation view after the graph continued |
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

On the planted benchmark models the scan lists exactly the planted cells, including mixed errors. One run investigates one target; the other flagged cells are listed for a follow-up run (see 103).

## The investigation view

Every endpoint answers with the same JSON, built by `investigation_view` from the graph's checkpoint:

- `id`: also the LangGraph `thread_id`, so one investigation is one thread.
- `status`: `needs_cell` (paused in `choose_target`), `needs_review` (paused in `human_review`) or `done`.
- `pause`: the value the graph passed to `interrupt()`: the question and candidate cells, or the report and patch to approve. `null` when not paused.
- The public state fields: `question`, `model_map`, `known_overrides`, `past_findings`, `target`, `causal_tree`, `hypotheses`, `evidence`, `verifications`, `patch`, `report`, `corrected_copy_id`, `run_log`. LangChain messages are never sent.

## Errors

Users never see a traceback. `friendly_error(error)` turns any exception into a status code and one short sentence; an exception handler registered on the app (`@app.exception_handler(Exception)`) uses it for normal requests, and the streams send the same pair as their `error` event. Only unexpected errors are logged with the full traceback, for the team.

| Code | When | Message (short) |
|---|---|---|
| `400` | Unknown spreadsheet or a workbook Model X-Ray cannot read | The `ValueError` message |
| `404` | No investigation with that id | |
| `409` | Resume on a finished investigation | |
| `422` | A formula the engine cannot calculate (e.g. `INDIRECT`) or a formula problem such as division by zero | "This model uses a formula Model X-Ray cannot calculate yet: ..." |
| `429` | A daily limit is reached | |
| `502` | Token Factory returned an error, or the model's answer did not fit the expected format | "The AI service returned an error. Please try again." |
| `503` | Token Factory timed out, is rate limiting, rejected the key, or cannot be reached | e.g. "The AI service took too long to answer. Please try again in a minute." |
| `500` | Anything else | "Something went wrong during the investigation. The team has the details; please try again." |

## Not yet

- Investigation ids live in memory, so a restart forgets them; the Postgres checkpointer and store (#72) fix this.

# HTTP API

Implementation: `src/model_x_ray/api.py`. Tests: `tests/test_api.py`. Issue: #73.

The API wraps the investigation graph so the React app (#74) can start an investigation, show its two pauses (which cell, approve the fix) and resume them.

## Building the app

`create_app(source, sandbox, models, checkpointer, cap)` returns a FastAPI app. Everything it needs is passed in, so tests use the demo workbook, scripted models and an in-memory checkpointer, and production passes Token Factory models and the Postgres checkpointer (#72).

- `AgentModels(llm, verifier=None, locator=None, mapper=None)`: one model per role, the same parameters as `run_investigation`.
- `UsageCap(per_visitor, total)`: investigations per visitor (by client IP) per day, and for everyone per day. The demo must stay open to judges until 15 Dec and every run spends our Token Factory credits, so the cap is checked before the graph runs and counted once the workbook is loaded and the investigation exists (a typo in the spreadsheet id costs nothing; a run that fails halfway still counts, because it already spent credits).

## Endpoints

| Method and path | Body | Answer |
|---|---|---|
| `POST /investigations` | `{"spreadsheet_id", "question"}` | `201` and the investigation view |
| `GET /investigations/{id}` | | The investigation view |
| `POST /investigations/{id}/resume` | A cell choice `{"ref": "P&L!H8"}` or a decision `{"action": "approve" \| "edit" \| "reject", "reason", "patch"}` | The investigation view after the graph continued |
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

## The investigation view

Every endpoint answers with the same JSON, built by `investigation_view` from the graph's checkpoint:

- `id`: also the LangGraph `thread_id`, so one investigation is one thread.
- `status`: `needs_cell` (paused in `choose_target`), `needs_review` (paused in `human_review`) or `done`.
- `pause`: the value the graph passed to `interrupt()`: the question and candidate cells, or the report and patch to approve. `null` when not paused.
- The public state fields: `question`, `target`, `causal_tree`, `hypotheses`, `evidence`, `verifications`, `patch`, `report`, `corrected_copy_id`, `run_log`. LangChain messages are never sent.

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

- The production entry point that builds the app from `.env` and the uploaded models.
- Investigation ids live in memory, so a restart forgets them; the Postgres checkpointer and store (#72) fix this.

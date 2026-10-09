# HTTP API

Implementation: `src/model_x_ray/api.py`. Tests: `tests/test_api.py`. Issue: #73.

The API wraps the investigation graph so the React app (#74) can start an investigation, show its two pauses (which cell, approve the fix) and resume them.

## Building the app

`create_app(source, sandbox, models, checkpointer, cap)` returns a FastAPI app. Everything it needs is passed in, so tests use the demo workbook, scripted models and an in-memory checkpointer, and production passes Token Factory models and the Postgres checkpointer (#72).

- `AgentModels(llm, verifier=None, locator=None, mapper=None)`: one model per role, the same parameters as `run_investigation`.
- `UsageCap(per_visitor, total)`: investigations per visitor (by client IP) per day, and for everyone per day. The demo must stay open to judges until 15 Dec and every run spends our Token Factory credits, so the cap is checked before the graph runs and counted only after an investigation really started.

## Endpoints

| Method and path | Body | Answer |
|---|---|---|
| `POST /investigations` | `{"spreadsheet_id", "question"}` | `201` and the investigation view |
| `GET /investigations/{id}` | | The investigation view |
| `POST /investigations/{id}/resume` | A cell choice `{"ref": "P&L!H8"}` or a decision `{"action": "approve" \| "edit" \| "reject", "reason", "patch"}` | The investigation view after the graph continued |

## The investigation view

Every endpoint answers with the same JSON, built by `investigation_view` from the graph's checkpoint:

- `id`: also the LangGraph `thread_id`, so one investigation is one thread.
- `status`: `needs_cell` (paused in `locate`), `needs_review` (paused in `human_review`) or `done`.
- `pause`: the value the graph passed to `interrupt()`: the question and candidate cells, or the report and patch to approve. `null` when not paused.
- The public state fields: `question`, `target`, `causal_tree`, `hypotheses`, `evidence`, `verifications`, `patch`, `report`, `corrected_copy_id`, `run_log`. LangChain messages are never sent.

## Errors

| Code | When |
|---|---|
| `400` | Unknown spreadsheet or a workbook Model X-Ray cannot read (the `ValueError` message) |
| `404` | No investigation with that id |
| `409` | Resume on a finished investigation |
| `429` | A daily limit is reached |

## Not yet

- `GET /investigations/{id}/events`: streamed progress while the graph runs (next step of #73).
- The production entry point that builds the app from `.env` and the uploaded models.
- Investigation ids live in memory, so a restart forgets them; the Postgres checkpointer and store (#72) fix this.

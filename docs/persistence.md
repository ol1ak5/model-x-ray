# Persistence: what is stored, what survives a restart

Issues #72 (Supabase persistence) and #75 (deploy) both assume the app needs a database. This page records what the code stores today, what each layer buys, and the gap that no storage engine can close on its own, so the hosting decision is made on facts. Implementation: `src/model_x_ray/memory.py`, `src/model_x_ray/server.py`, `src/model_x_ray/api.py`. Evidence: `tests/test_persistence.py`, `tests/test_long_term_memory.py`.

## Four things live outside a single request

| Layer | Where | Read back | Survives a new process |
|---|---|---|---|
| LangGraph checkpoints, the state of one investigation per thread id | `sqlite_checkpointer`, default `checkpoints.db` | only through a compiled graph that this process still holds in `create_app`'s `graphs` dict | the file does, the access does not |
| Long-term memory: model maps, intentional overrides, past fixes (`ModelMemory` over any LangGraph `BaseStore`) | `sqlite_store`, default `memory.db` | at the start of every run, through `store=` | yes |
| Uploaded models | `.xlsx` files under `MODEL_X_RAY_UPLOAD_DIR`, plus an in-memory `uploads` set in `create_app` | the `SpreadsheetSource` | the files do, the ids do not |
| Usage counts | `UsageCap.counts`, process memory | the cap check before a run | no |

Only the long-term memory is durable end to end, and it is the layer that changes what the agent knows: `make_load_sheet_node` feeds the overrides and past findings into every run, `map_model` reuses the cached model map instead of paying the mapper model again, and `remember_decision` writes both back. `tests/test_long_term_memory.py` covers all three.

## The gap: the checkpoint is written but never looked up

`create_app` keeps `graphs: dict[str, CompiledStateGraph]`, and `graph_of()` answers `404` for any id this process has not seen. The checkpoint for the paused thread is written anyway, and nothing ever reads it back.

`tests/test_persistence.py::test_a_restart_forgets_a_paused_investigation_even_with_the_checkpoint_on_disk` runs an investigation to `needs_review`, asserts that its thread id is in `checkpoints.db`, that the same app answers `200`, and that a second app on the same file answers `404` for both the view and the resume.

So swapping SQLite for Postgres or Supabase (#72) as written would change nothing for a restart or a second instance: the missing piece is the app-level lookup, not the storage engine.

## What that means for hosting

- A single long-lived process (a local run, one container with its own disk) can pause and resume, and its SQLite files are enough. No database is necessary.
- Serverless, or more than one instance (`#75` option A), cannot resume with the current code: a request may land on an instance that never saw the id. A shared database is necessary *and* not sufficient — `graph_of` must rebuild the graph for an unknown id from the checkpoint before any of it works.
- A shared database would also have to cover the other two layers to make a multi-instance demo honest: uploads to object storage, and the usage cap to the same database, otherwise each instance counts its own and the cap stops protecting the credits.

## What the check turned up

- `ModelMemory` namespaces are `(kind, spreadsheet_id)` with no visitor in the key, so one visitor marking a cell intentional suppresses that cell in every later visitor's run on the same demo model. On a public demo that is a repeatability hazard.
- `graphs` never evicts, so a long-running demo keeps every investigation's graph.
- `checkpoints.db` and `memory.db` are git-ignored but outlive a demo run, so the same model can behave differently on the second run of the day.

## Options

| Option | What it takes | Cost |
|---|---|---|
| A. One container, no database | record the decision and drop or narrow #72; SQLite files on a disk | smallest, but no restart safety and one instance |
| B. Rebuild the graph from the checkpointer | `graph_of` reads the thread's `spreadsheet_id` through the checkpointer and builds a fresh graph, which flips the test above | a handful of lines, and the precondition for any database being worth its setup |
| C. Fully external state: checkpointer, uploads, cap | Postgres or Supabase plus Storage, and #75's open question about a 30 to 60 second run inside a serverless function limit | largest, most moving parts before the deadline |

Recommendation: B first, because it turns the checkpointer from dead weight into restart safety, then take #75's hosting decision with A as the fallback if the deadline tightens.

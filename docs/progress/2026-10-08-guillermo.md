# Progress: 7 to 8 October 2026 (Guillermo)

Between 7 October 22:00 and 8 October 03:10 UTC, Guillermo merged 17 pull requests. Together with the work merged earlier on 7 October (state, graph skeleton, Investigator, spreadsheet engine), Model X-Ray now runs end to end on a real workbook, except for the nodes listed under "Still open". All 53 offline tests pass.

## What was built

| Area | What changed | PRs |
|---|---|---|
| Spreadsheet engine | Merged the formula parser, dependency graph and patched copies (`spreadsheet/engine.py`, `spreadsheet/xlsx.py`); added cell metadata (font colour, number format) for override judgment | #36 |
| Read-only tools | The Investigator's real tools on top of the engine: `find_cells`, `get_cell`, `trace_precedents`, `trace_dependents`, `compare_formulas`, `find_formula_outliers`, `get_cell_metadata`; a `SpreadsheetSource` protocol with an `.xlsx` implementation | #47 |
| Causal tree | `explain_change` splits a period-on-period change into each input's contribution by recalculating; the `trace` node builds the causal tree from it | #48 |
| Investigator | Runs on the real tools with the causal tree in its briefing; budgets enforced (8 tool calls, 3 open hypotheses across retries); wired as the explicit `diagnose` node; new `run_investigation(...)` entry point builds the whole agent in one call | #41, #43, #46, #49, #53 |
| Evidence | Hypotheses link to evidence records; the patch records the formula it replaces; `trace` writes evidence and `explain` cites evidence ids | #52, #60 |
| Verifier | Deterministic checks first (anomaly resolved, dependents consistent, row pattern restored), then Nemotron as an adversarial second opinion on a fixed evidence package; verdicts can be confirmed, rejected or inconclusive | #57 |
| Sandbox | `Sandbox` interface and a Google Sheets implementation (copy, patch, read Google's recalculation, write a corrected copy with a change log); live use needs the service account (#14) | #55 |
| Human review | Fixed: a fix edited by the human now reaches `test` and `apply_fix`, and its hypothesis is re-tested | #61 |
| Nemotron client | A model per role (investigator, verifier, mapper, locate, explain), overridable from `.env`; timeouts and retries; token and latency records for every call | #66 |
| Benchmark dataset | Seeded generator: a synthetic base model (P&L 2024A to 2028E) plus planted-error variants per error type, blended, overrides and clean, each with ground truth | #65 |
| Docs and housekeeping | Graph picture exported to `docs/investigation-graph.png` with a test that keeps it in sync; AGENTS.md repo state and developer skills refreshed | #44, #54, #63 |

## How the agent runs now

1. `trace` builds the causal tree from the real workbook.
2. The Investigator explores with the real read-only tools and returns hypotheses with evidence and a patch.
3. `test` applies the patch in a sandbox copy and reads the recalculated values.
4. The Verifier runs deterministic checks, then tries to disprove the diagnosis.
5. `explain` writes a report citing evidence.
6. The human approves, edits or rejects; `apply_fix` writes a corrected copy.

## Still open

- `load_sheet`, `map_model` and `locate` are still stubs: `locate` only knows the demo cells `P&L!H8` and `Summary!D10`, so a real question about a new model cannot find its target yet.
- Google service account (#14), then uploading the dataset to Google Sheets (#64).
- Benchmark runner, evaluators and results report (#16, #17, #27).
- Long-term memory (#11), narrative report (#58), clickable evidence (#51, #59), `.xlsx` sandbox (#13).
- README and LICENSE (#62); no issues yet for the demo app, deployment (public demo URL) or the video.
- Error-type names between the agent and the dataset are aligned in #67.

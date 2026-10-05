# Agent architecture

Model X-Ray is an evidence-first Nemotron agent that investigates surprising outputs in financial models. Given a question such as "Why did 2027 EBITDA jump 30%?", it locates the cell, traces its inputs, diagnoses the root cause, tests a fix in a sandbox copy, verifies the result, explains it with clickable evidence, and returns a corrected copy after a human approves.

Roadmap: #2. This document: #3.

## Design principles

1. **Nemotron judges, code computes.** Every number comes from deterministic code or from the spreadsheet's own recalculation. The LLM never does arithmetic and may only quote tool results.
2. **Evidence first.** Every claim in the final answer points to a cell, the expected pattern, and a verified before/after value.
3. **Prove the fix.** A diagnosis counts only after the patched sandbox copy recalculates to a result that resolves the anomaly and stays consistent with the model.
4. **The original is never written.** The LLM has no write tool. Only the `apply_fix` node writes, only after human approval, and only to a new corrected copy.
5. **Honest failure.** If no hypothesis survives verification, the agent says the result is inconclusive instead of guessing.

## Platform

Spreadsheets are read through a `SpreadsheetSource` interface and tested through a `Sandbox` interface.

| Adapter | Status | Read | Recalculate |
|---|---|---|---|
| Google Sheets | First | Sheets API with `valueRenderOption=FORMULA` and `UNFORMATTED_VALUE` | Copy with Drive `files.copy`, write the patch, read the values Google recalculated |
| `.xlsx` | Stretch (#13) | `openpyxl` | Python formula engine (`formulas` or `pycel`) |

Google Sheets is first because its sandbox is exact: the recalculated numbers are the ones the user would see, with no formula re-implementation. Judges can open a demo model from a link with nothing to install. Excel users are still covered: an `.xlsx` file uploaded to Google Drive converts to Google Sheets, and the agent works on the converted copy.

Scope for the hackathon: standard models without scripts or macros. Named ranges, `INDIRECT` and `OFFSET` are out of scope unless the demo model needs them.

## Graph

```mermaid
flowchart TD
  S([START]) --> load_sheet
  load_sheet --> map_model
  map_model --> locate
  locate -->|ambiguous: interrupt| locate
  locate --> trace
  trace --> diagnose
  diagnose --> test
  test --> verify
  verify -->|rejected, suspects left, attempts < 3| diagnose
  verify -->|confirmed| explain
  verify -->|exhausted| explain
  explain --> human_review
  human_review -->|approve| apply_fix
  human_review -->|edit| test
  human_review -->|reject| E([END])
  apply_fix --> E
```

| Node | Kind | What it does | Writes to state |
|---|---|---|---|
| `load_sheet` | Code | Reads values, formulas and labels; builds the dependency graph | (graph cached outside state) |
| `map_model` | Nemotron Nano | Labels rows (revenue, opex, totals) and columns (actuals vs forecast); skipped when the map for this sheet revision is in long-term memory | `model_map_ref` |
| `locate` | Nemotron Super + `find_cells` | Turns the question into a target cell and comparison period; calls `interrupt()` if several cells match | `target`, `messages` |
| `trace` | Code | Precedents of the target, the contribution of each input to the change, and the causal tree built from them | `contributions`, `causal_tree`, `evidence` |
| `diagnose` | Investigator agent (subgraph) | Hypothesis-driven loop over read-only tools (see below), returns ranked hypotheses with evidence and a minimal patch | `hypotheses`, `evidence`, `patch` |
| `test` | Code | Copies the sheet, applies the patch, reads recalculated values | `verifications` (values part) |
| `verify` | Code checks + Verifier agent | Deterministic checks, then an independent attempt to disprove the diagnosis | `verifications`, `hypotheses`, `attempts` |
| `explain` | Nemotron Super | Evidence-linked report, or an honest "inconclusive" | `report` |
| `human_review` | Interrupt | Approve, edit the fix, or reject with a reason | `human_decision` |
| `apply_fix` | Code | Writes a corrected copy with a `Change log` tab | `corrected_copy_id` |

### Routing after `verify`

| Condition | Next node |
|---|---|
| Latest verification is `confirmed` | `explain` |
| `rejected`, untested hypotheses remain, and `attempts < 3` | `diagnose` (with rejected hypotheses in context) |
| Otherwise | `explain`, marked inconclusive |

### Routing after `human_review`

| Decision | Next node | Side effect |
|---|---|---|
| `approve` | `apply_fix` | Finding stored in long-term memory |
| `edit` | `test` | The human's patch replaces the agent's |
| `reject` | `END` | If the reason is "intentional", an override is stored in long-term memory |

## Agents

Three steps need judgment, so three agents. Everything else is a plain Python node.

| Agent | Model | Tools | Job |
|---|---|---|---|
| Investigator | Nemotron 3 Super | Read-only only | Hypothesis-driven loop inside a subgraph with its own private messages. Decides what to investigate next, tells real errors from deliberate overrides, ranks hypotheses, proposes a minimal patch |
| Verifier | Nemotron 3 Super, adversarial prompt | None (receives a fixed evidence package) | Assumes the diagnosis is wrong and looks for evidence that invalidates it. Never sees the Investigator's reasoning |
| Model mapper | Nemotron 3 Nano | None | One structured-output call per sheet revision to build the semantic map |

Model assignment is provisional until the tool-calling spike (#4) reports results. A separate "hypothesis planner" agent is deliberately not added: planning stays inside the Investigator unless the benchmark shows that splitting it improves accuracy.

The system presents itself as one reasoning loop with three capabilities: **understand** (Model mapper), **investigate** (Investigator), **verify** (Verifier), followed by **explain**.

### Investigator loop

The Investigator is the most autonomous part of the system, and its autonomy must be visible, not hidden inside one call.

```
OBSERVE        read the causal tree and contributions from trace
HYPOTHESIZE    list candidate causes (at most 3 open at a time)
SELECT TOOL    choose the read-only tool that best separates the candidates
OBSERVE        read the tool result
UPDATE         raise, lower or reject hypotheses, citing evidence ids
   ... repeat SELECT TOOL to UPDATE ...
PROPOSE        top hypothesis + minimal patch
```

| Budget | Limit | Why |
|---|---|---|
| Tool calls per diagnose run | 8 | Autonomy with a predictable cost and latency |
| Open hypotheses | 3 | Forces ranking instead of listing everything |
| Diagnose-verify attempts | 3 | Bounded retry loop |

Every UPDATE writes to `hypotheses` in the state, so the interface can show a live hypothesis board: candidates appearing, gaining or losing confidence, and being rejected, each linked to the evidence that moved it. When the budget runs out, the Investigator must propose its best hypothesis or declare the case inconclusive.

### Verifier: adversarial second opinion

The two prompts are deliberately incompatible. The Investigator is told to find the most likely explanation and construct a minimal fix. The Verifier is told to assume the diagnosis is wrong and find any evidence that invalidates it.

| The Verifier receives | The Verifier does not receive |
|---|---|
| Original question and target | The Investigator's messages or reasoning |
| The proposed patch | Rejected hypotheses |
| Relevant formulas (patched cell, its neighbours, its dependents) | |
| Sandbox before/after values and the deterministic check results | |

It returns `confirmed` or `rejected` with reasons. Deterministic checks run first (anomaly resolved, no new anomalies in dependents, pattern restored); the Verifier can reject a patch that passes them, but cannot confirm one that fails them.

## State

The graph routes on structured fields and the evidence view displays them, so state is not messages only. Each key has a deliberate reducer: no annotation means the new value overwrites the old one.

```python
class InvestigationState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    spreadsheet_id: str
    question: str
    model_map_ref: str | None
    target: TargetCell | None
    contributions: list[Contribution]
    causal_tree: CausalNode | None
    hypotheses: Annotated[list[Hypothesis], merge_by_id]
    patch: Patch | None
    verifications: Annotated[list[Verification], operator.add]
    evidence: Annotated[list[Evidence], operator.add]
    attempts: int
    report: str | None
    human_decision: HumanDecision | None
    corrected_copy_id: str | None
```

| Key | Reducer | Why |
|---|---|---|
| `messages` | `add_messages` | Conversation with the user only; appends, and replaces by message id |
| `target`, `patch`, `report`, `human_decision`, `corrected_copy_id` | Overwrite | One current value |
| `contributions`, `causal_tree` | Overwrite | Recomputed as a whole by `trace` |
| `hypotheses` | `merge_by_id` (custom) | The Verifier updates a hypothesis status in place; new ids append; never duplicates |
| `verifications`, `evidence` | `operator.add` | Append-only audit trail behind "show me the evidence" |
| `attempts` | Overwrite | Incremented by `verify` |

The Investigator's tool-calling messages live in the subgraph's private state, so they do not clutter the main conversation.

Schemas at the boundary: the graph accepts `spreadsheet_id` and `question` (input schema) and returns `report`, `patch`, `evidence` and `corrected_copy_id` (output schema).

### Records

| Record | Fields |
|---|---|
| `TargetCell` | `sheet`, `cell`, `label`, `period`, `value`, `prior_cell`, `prior_value` |
| `Contribution` | `cell`, `label`, `delta` |
| `CausalNode` | `cell`, `label`, `value_before`, `value_after`, `delta`, `share_of_change`, `suspicious`, `children` |
| `Hypothesis` | `id`, `cell`, `error_type`, `claim`, `evidence_ids`, `confidence`, `status` (`open`, `rejected`, `confirmed`) |
| `Patch` | `cell`, `old_formula`, `new_formula`, `source` (`agent`, `human`) |
| `Verification` | `hypothesis_id`, `before`, `after`, `checks`, `verdict`, `reason` |
| `Evidence` | `id`, `cell`, `kind` (`anomaly`, `expected_pattern`, `verification`), `text` |
| `HumanDecision` | `action` (`approve`, `edit`, `reject`), `reason`, `patch` |

## Tools

| Tool | Access | Used by |
|---|---|---|
| `find_cells(label, period)` | Read-only | `locate`, Investigator |
| `get_cell(ref)` | Read-only | Investigator |
| `trace_precedents(ref, depth)` | Read-only | `trace`, Investigator |
| `trace_dependents(ref, depth)` | Read-only | Investigator, `verify` |
| `explain_change(ref, from_period, to_period)` | Read-only | `trace`, Investigator |
| `compare_formulas(cell, reference_cells)` | Read-only | Investigator, `verify` |
| `find_formula_outliers(range)` | Read-only | Investigator, rules-only baseline |
| `get_cell_metadata(ref)` | Read-only | Investigator |
| `create_copy`, `apply_patch`, `read_values`, `discard` | Sandbox | `test` only |
| `write_corrected_copy` | Write | `apply_fix` only, after approval |

The read-only tools form a small financial-model investigation API, so the LLM never interprets raw formulas on its own:

| Tool | Returns |
|---|---|
| `compare_formulas` | The structure of a formula next to its neighbours' (references normalized relative to each cell) and whether it deviates, e.g. "F27 is `SUM(F20:F24)`, neighbours use rows 20 to 25" |
| `find_formula_outliers` | Every cell in a range that breaks its row pattern, is a typed value inside a formula region, or has an inconsistent reference |
| `get_cell_metadata` | Cell note, font colour and number format. Modelling convention (blue for typed inputs, black for formulas) and notes such as "per budget meeting" are context for telling deliberate overrides from errors; they are signals, never proof on their own |
| `explain_change` | The contribution of each input to a period-on-period change, by recalculating with one input changed at a time |

## Causal tree

`trace` turns contributions into a tree that explains the change before any diagnosis. It is the centre of the demo and the Investigator's starting observation.

```
EBITDA 2027  +30%
├── Revenue  +18%
│   └── Units  +10%
├── COGS     +4%
└── Opex     +8%   suspicious
    └── F27  =SUM(F20:F24), neighbours use rows 20 to 25
```

After a confirmed fix the same tree is shown again with the patched values ("EBITDA +30% becomes +4%, pattern restored"), so the before/after story is visual.

## Error types in scope

1. A typed value replacing a formula
2. A broken or wrong reference
3. An inconsistent range (for example a SUM that skips a row)
4. A sign or period inconsistency

The rule scanner and the tool set are extensible to further model-risk patterns after the hackathon.

## Human in the loop

Both pauses use `interrupt()` inside the node and resume with `Command(resume=...)`, which replaces the older `interrupt_before` and `NodeInterrupt` patterns.

1. **Clarify** in `locate`, only when the question matches more than one cell.
2. **Approve** in `human_review`, always, before anything is written.

## Memory

| Kind | Mechanism | Content |
|---|---|---|
| Short-term | Checkpointer (`SqliteSaver`), one `thread_id` per investigation | Full state after every node: enables pause and resume for the human, and time travel for debugging |
| Long-term | LangGraph Store | `("models", spreadsheet_id)`: model map per sheet revision. `("findings", spreadsheet_id)`: confirmed fixes. `("overrides", spreadsheet_id)`: cells a human marked as intentional, read by the Investigator so they are not flagged again |

Details: #11.

## Models

| Use | Model ID |
|---|---|
| Investigator, Verifier, `locate`, `explain` | `nvidia/nemotron-3-super-120b-a12b` |
| Model mapper | `nvidia/nvidia-nemotron-3-nano-30b-a3b` |

Both run on Nebius Token Factory through LangChain's `ChatOpenAI` with `base_url=https://api.tokenfactory.us-central1.nebius.com/v1/` and `NEBIUS_API_KEY` from `.env`. Confirm IDs in the console before hardcoding (#4).

## Evaluation

Every node is measured against its own metric, and the whole agent runs on generated models: X models per error type, X with blended errors, plus override and clean controls. Accuracy and latency per error type and per step form the project's conclusion. Details: `docs/evaluation.md`.

## Not in scope for the hackathon

- Peer, WACC and terminal-growth assumption checks
- Scripts, macros, `.xls`, external workbooks
- Editing the user's original spreadsheet

## Open questions

- Hosted demo: do users share sheets with the service account, or sign in with OAuth? (#14)
- Where long-term memory lives on the hosted demo (#11)
- Whether Nano is reliable enough for `locate` to cut cost (#4)

# Evaluation

Every step of the investigation graph is measured, and the whole agent is tested on generated models with known errors. The results (accuracy and latency per error type and per step) are the conclusion of the project and the centerpiece of the demo.

Related: design in `docs/agent-architecture.md`, dataset #12, evaluators and runner #16, results report #17.

## Why the ground truth is exact

Every test model is a copy of one clean base model with errors planted by a script. So for each variant we know:

- which cell was broken, and how (the error type)
- the original formula (the correct fix)
- the correct output values: the clean base model itself

A fix is correct when the corrected copy's outputs match the clean base model. This is checked by recalculation, not by an LLM judge.

## Dataset

| Set | Count | Content | What it tests |
|---|---|---|---|
| Type 1 | X | One typed value replacing a formula | Detection of hardcodes |
| Type 2 | X | One wrong reference | Detection of bad links |
| Type 3 | X | One inconsistent range (e.g. a SUM that skips a row) | Detection of aggregation errors |
| Type 4 | X | One sign inconsistency | Detection of flipped signs |
| Type 5 | X | One period inconsistency | Detection of references to the wrong period |
| Blended | X | Two or three errors of mixed types, including cases where the symptom cell is not the cause | Root cause under noise; the retry loop |
| Overrides | X / 2 | Deliberate, documented typed values (e.g. a cell note "per budget meeting") with no real error | False alarms; Nemotron's judgment |
| Clean | X / 2 | No changes | The agent must report that nothing is wrong |

Default `X = 25`, configurable: 174 investigations per full run (25 × six sets: five error types plus blended, and floor-rounded halves for overrides and clean). Each variant comes with one or more questions generated from templates ("Why did {line} {year} change by {pct}%?"), where the asked line is downstream of a planted error. Generation is seeded so runs are reproducible. Ground truth is stored next to each variant as JSON: planted cells, error types, original formulas, expected outputs.

### Output layout

`uv run tools/generate_dataset.py --output dataset --per-set 25 --seed 42` writes:

```
dataset/
  base.xlsx                     the clean base model: P&L (two actual and three forecast years), Assumptions, Summary
  manifest.json                 seed, per-set counts, and the per-variant file map
  <set>/variant-NNN.xlsx        one variant workbook
  <set>/variant-NNN.json        ground truth for that variant
```

Each ground-truth JSON holds `planted` (cell, error type, original formula, new content, comment), `questions` (text, target cell, expected error cells, expected verdict) and `expected_outputs` (the value of every formula cell in the clean base — the target a correct fix must reproduce). The question target is the planted cell's first downstream dependent with a usable prior period, preferring the same-column EBITDA line; the percentage is computed from the variant itself, so the question describes what an analyst would actually see. Typed values are planted as stale prior-period numbers (a real hardcode, outputs shift), while override variants are typed to their own computed value with a cell comment (outputs stay at the base — nothing should be flagged).

With 25 cases per set, an accuracy figure carries roughly ±10 to 20 points of uncertainty, so results are reported with 95% Wilson intervals rather than as bare percentages.

## Metrics per step

The runner computes these today; the table names the evaluator or the row field that produces each number.

| Step | Accuracy metric | Other metrics | Computed by |
|---|---|---|---|
| `load_sheet` | Share of formula cells the engine parses and evaluates; dependency edges compared with the clean base model (precision, recall) | Latency | `load_sheet_metrics` (`parse_share`, `edge_precision`, `edge_recall`) |
| `map_model` | Row and column labels vs ground truth (accuracy) | Latency, tokens | pending: needs label ground truth in the dataset |
| `locate` | Target cell exact match; on questions that match several cells, auto-pick accuracy (the cell the agent chose is the intended one) | Latency, tokens | `locate_metrics`, `auto_pick_accuracy` |
| `trace` | Planted cell present among the contributions or the causal tree (recall) | Latency | `trace_recall` |
| `diagnose` | Planted cell in top 1 and top 3 hypotheses; error type correct; overrides and clean wrongly flagged (false-alarm rate); confidence calibration (share of `high`, `medium` and `low` hypotheses later confirmed, which should fall from high to low) | Latency, tokens, tool calls used out of the budget of 8, hypothesis revisions, runs that hit the budget | `diagnose_metrics`, `calibration` |
| `test` | Sandbox ran and produced before/after values; the value match itself is checked end to end as fix accuracy | Latency | `sandbox_ok`, `fix_accuracy` |
| `verify` | Verdict accuracy: confirms correct patches, rejects wrong ones (precision, recall on deliberately wrong patches too) | Latency, tokens | `verdict_metrics` |
| `explain` | Every cited evidence id resolves in state (quoted numbers pending) | Latency, tokens | `explain_metrics` |

The `verify` step is also fed deliberately wrong patches, so its ability to reject is measured, not assumed. Every run row also carries `node_latencies` (per-node latency) and `run_log` (per LLM call: role, model, tokens, latency), so the report can build the per-step table without LangSmith.

## End-to-end metrics

| Metric | Definition |
|---|---|
| Root-cause accuracy | Correct cell and correct error type |
| Fix accuracy | Corrected copy matches the clean base on all outputs |
| False-alarm rate | Errors reported on override and clean models |
| Inconclusive rate | Honest "no verified root cause" answers |
| Attempts | Diagnose-verify loops used |
| Latency | p50 and p95 per investigation, and per step |
| Cost | Tokens and dollars per investigation |

## Comparisons

The same dataset runs through four set-ups. The graph receives its models as parameters, so switching set-ups is configuration, not new code; the only extra code is the rules-only diagnose.

| Set-up | Diagnose step | What it shows |
|---|---|---|
| Rules only | `find_formula_outliers` ranks suspicious cells; no LLM | The baseline plain code achieves |
| Small Nemotron | Investigator on `NVIDIA-Nemotron-3-Nano-30B-A3B` | Whether a small model is enough |
| Nemotron Super | Investigator and Verifier on `Nemotron-3.5-Super-VL` (main system; `nemotron-3-super-120b-a12b` before 21 Oct 2026, kept as set-up `super-3`) | The full agent |
| Super without tools | Nemotron reads the sheet as plain text | What the tools add |

Results are reported per set, because the expected winner differs by set and the comparison must not be rigged. Rules should do well on single, clean errors such as a typed value replacing a formula. Nemotron is expected to earn its place on the override set (fewer false alarms, by reading notes and context) and the blended set (symptom is not the cause). The headline is stated in those terms, for example "rules handle the easy cases; Nemotron cuts false alarms by X points and solves Y% of the blended cases rules miss", with the measured numbers whatever they turn out to be.

## How it runs

- Each node records its latency in `node_log` and each LLM call its role, model, tokens and latency in `run_log`; the runner needs no LangSmith.
- The benchmark isolates the diagnose step: in every set-up `map_model` is the code stub and `locate` runs without an LLM.
- `uv run tools/benchmark.py --setups rules` runs the rules baseline offline and for free, generating the dataset first if it is missing.
- `scripts/benchmark.sh` (zero flags) runs all four set-ups with six parallel workers and writes `docs/benchmark-results.json`, the rendered `docs/benchmark.md` and the chart `docs/benchmark.svg`; the three LLM set-ups spend Token Factory credits.
- `uv run tools/benchmark.py --render-only` re-renders the report and chart from an existing results file — the re-run-and-refresh workflow needs no new measurements.
- Unit tests for the evaluators use fixed fake outputs; the full four-way run is a separate, opt-in invocation.

## Report

`docs/benchmark.md` is rendered by the benchmark run itself (or re-rendered with `--render-only`) and contains:

1. A results table per set (type 1 to 4, blended, overrides, clean): root-cause accuracy with 95% Wilson intervals, fix accuracy, false alarms, latency p50 and p95, cost
2. A per-step table with the metrics above, plus per-node latency p50 and per-role token and cost totals
3. A confusion matrix of predicted vs planted error types
4. The four-way comparison, per set
5. A short conclusion in plain language with intervals, quoted in the README and the demo video
6. `docs/benchmark.svg`, one bar per set-up and set, for the demo video

## Enron Errors Corpus: false alarms on the corrected files

`tools/enron_benchmark.py run --controls` also runs each case's corrected file. A confirmed fix there is a false alarm, with one exception: when the fixed cell is listed in the corpus index as an error in the same spreadsheet and its content is identical in the faulty and the corrected file, the "correction" did not touch that error (the index itself records several such cases, for example `Sheet1!I34 = SUM(I9:I33)` in spreadsheet 28). Those rows are reported as `known_errors_kept`, next to `false_alarms`, and never hidden. A fix on a listed cell whose content changed between the two files still counts as a false alarm.

Two caveats when reading `fix_matches_correction`: some corrected files are a later version of the workbook with different input values (spreadsheet 1 is the next day's file), so a fix with exactly the corrected formula can still produce a different value; and files on which the agent finds nothing to check currently end with an error instead of "no error found", so they show up as skipped.

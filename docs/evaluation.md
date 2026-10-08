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
| Type 2 | X | One broken or wrong reference | Detection of bad links |
| Type 3 | X | One inconsistent range (e.g. a SUM that skips a row) | Detection of aggregation errors |
| Type 4 | X | One sign or period inconsistency | Detection of sign and period slips |
| Blended | X | Two or three errors of mixed types, including cases where the symptom cell is not the cause | Root cause under noise; the retry loop |
| Overrides | X / 2 | Deliberate, documented typed values (e.g. a cell note "per budget meeting") with no real error | False alarms; Nemotron's judgment |
| Clean | X / 2 | No changes | The agent must report that nothing is wrong |

Default `X = 25`, configurable: 149 investigations per full run (25 × five single-purpose sets, plus floor-rounded halves for overrides and clean). Each variant comes with one or more questions generated from templates ("Why did {line} {year} change by {pct}%?"), where the asked line is downstream of a planted error. Generation is seeded so runs are reproducible. Ground truth is stored next to each variant as JSON: planted cells, error types, original formulas, expected outputs.

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

| Step | Accuracy metric | Other metrics |
|---|---|---|
| `load_sheet` | Share of formulas parsed; dependency edges vs ground truth (precision, recall) | Latency |
| `map_model` | Row and column labels vs ground truth (accuracy) | Latency, tokens |
| `locate` | Target cell exact match; clarification asked only when truly ambiguous (precision, recall) | Latency, tokens |
| `trace` | Planted cell present among precedents (recall, expected 100%); contributions sum to the observed change | Latency |
| `diagnose` | Planted cell in top 1 and top 3 hypotheses; error type correct; overrides wrongly flagged (false-alarm rate); confidence calibration (share of `high`, `medium` and `low` hypotheses later confirmed, which should fall from high to low) | Latency, tokens, tool calls used out of the budget of 8, hypothesis revisions, runs that hit the budget |
| `test` | Sandbox runs succeed; recalculated values match the clean base for correct patches | Latency (Google API) |
| `verify` | Verdict accuracy: confirms correct patches, rejects wrong ones (precision, recall on deliberately wrong patches too) | Latency, tokens |
| `explain` | Every cited cell exists and every quoted number matches the sheet (automatic check) | Latency, tokens |

The `verify` step is also fed deliberately wrong patches, so its ability to reject is measured, not assumed.

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
| Rules only | `find_formula_outliers` picks the most suspicious precedent; no LLM | The baseline plain code achieves |
| Small Nemotron | Investigator on `NVIDIA-Nemotron-3-Nano-30B-A3B` or `Nemotron-3_5-Lightning` (whichever wins #4) | Whether a small model is enough |
| Nemotron Super | Investigator on `nemotron-3-super-120b-a12b` (main system) | The full agent |
| Super without tools | Nemotron reads the sheet as plain text | What the tools add |

Results are reported per set, because the expected winner differs by set and the comparison must not be rigged. Rules should do well on single, clean errors such as a typed value replacing a formula. Nemotron is expected to earn its place on the override set (fewer false alarms, by reading notes and context) and the blended set (symptom is not the cause). The headline is stated in those terms, for example "rules handle the easy cases; Nemotron cuts false alarms by X points and solves Y% of the blended cases rules miss", with the measured numbers whatever they turn out to be.

## How it runs

- Each node records its own timing and token use. LangSmith traces are used when available; the runner does not depend on them.
- `scripts/benchmark.sh` (zero flags) runs the full set and writes `docs/benchmark.md`.
- Unit tests for the evaluators use fixed fake outputs; the full benchmark is a separate, opt-in run because it calls Token Factory and the Google APIs.

## Report

`docs/benchmark.md` contains, generated by the runner:

1. A results table per set (type 1 to 4, blended, overrides, clean): root-cause accuracy, fix accuracy, false alarms, latency p50 and p95, cost
2. A per-step table with the metrics above
3. A confusion matrix of predicted vs planted error types
4. The four-way comparison, per set
5. A short conclusion in plain language, quoted in the README and the demo video

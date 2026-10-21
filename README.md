# Model X-Ray

**The debugger for financial models.** Model X-Ray is an evidence-first Nemotron agent that investigates surprising outputs in financial spreadsheets. Given a question such as "Why did EBITDA jump in 2030E?", it locates the cell behind the question, traces the dependency graph, diagnoses the root cause, tests a fix in a sandbox copy of the workbook, verifies the result, explains it with clickable evidence, and returns a corrected copy only after a human approves the change.

Every number it reports comes from deterministic code or from the spreadsheet's own recalculation. The LLM never does arithmetic and may only quote tool results; a wrong hypothesis is shown, rejected with evidence, and replaced rather than quietly dropped.

## Demo scenario

The repository ships the model the app serves by default, `demo_models/demo.xlsx`: a three-sheet deal model (P&L, Assumptions, Summary; EUR m, 2024A–2028E) with two planted mistakes:

- `P&L!G5` (COGS, 2025A) reads `=G4*Assumptions!$C$5` where the row uses `=-G4*…`, so COGS flips sign and gross profit shows 285.8 instead of 84.7.
- `P&L!I6` (gross profit, 2027E) is a typed `95.65` (the 2026E figure) where the row adds revenue and COGS.

Run the API and investigate it:

```bash
scripts/serve.sh                # http://localhost:8000/docs
```

```json
POST /investigations
{"spreadsheet_id": "demo", "question": "Why did gross profit jump in 2025A?"}
```

The graph locates `P&L!G5`, traces the 2025A gross profit to it, proposes `=-G4*Assumptions!$C$5`, tests it in a sandbox copy and pauses for approval; approving writes a corrected workbook that `GET /investigations/{id}/corrected` returns once and then deletes, and an uploaded model is deleted from the server as soon as its run ends.

`demo/nvidia-pnl.xlsx` and `demo/nvidia-pnl-error.xlsx` are the second pair the docs and tests use (two sheets, FY2025–FY2032, one typed `45.0` at `P&L!G11` where the row sums `G7:G10`, which lifts the 2030E EBITDA margin); point the API at it with `MODEL_X_RAY_MODELS_DIR=demo`. Regenerate both files any time with `uv run tools/generate_demo_model.py`.

## How it works

![Investigation graph](docs/investigation-graph.png)

Ten nodes over a LangGraph state machine: **load** opens the workbook and **map** labels its lines and periods, **locate** resolves the question to a cell (code first, Nemotron only when several cells match; the choice is recorded for the report), **trace** walks the dependency graph and records causal contributions as evidence, **diagnose** runs a hypothesis loop with an evidence budget, **test** applies the proposed patch in a sandbox copy and compares before/after values, **verify** has an adversarial Nemotron Verifier try to break the diagnosis with a fixed evidence package, and **explain** renders the narrative report citing the recorded evidence ids. **human_review** pauses for the decision and **apply_fix** writes the corrected copy after approval. Design details: [`docs/agent-architecture.md`](docs/agent-architecture.md).

## Built on Nebius × NVIDIA

All LLM calls run on **Nebius Token Factory** (OpenAI-compatible) through LangChain's `ChatOpenAI`, using NVIDIA open-source **Nemotron** models:

| Role | Model |
|---|---|
| Investigator, Verifier | `nvidia/Nemotron-3.5-Super-VL` (1M context, $0.30 / $0.90 per 1M tokens) |
| Model mapper, locate | `nvidia/nemotron-3-super-120b-a12b` (256K context, $0.30 / $0.90) |
| Report writer (`explain`) | `nvidia/Nemotron-3_5-Lightning` (1M context, $0.06 / $0.24) |
| Benchmark comparison set-up `super-3` | `nvidia/nemotron-3-super-120b-a12b` |
| Benchmark small-model set-up | `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` ($0.06 / $0.24) |
| Benchmark hardest-verification set-up | `nvidia/Nemotron-3-Ultra-550b-a55b` (1M context, $1.00 / $3.00) |

- Base URL: `https://api.tokenfactory.nebius.com/v1/`, key in `NEBIUS_API_KEY` (`.env`, never committed); every role is overridable via `NEBIUS_MODEL_<ROLE>`.
- Token Factory docs: <https://docs.tokenfactory.nebius.com/> (model list, function calling, structured output, rate limits).
- Model IDs were verified live with `GET /v1/models` on 6 Oct 2026, and Nemotron 3.5 Super on 21 Oct 2026; prices and context windows come from the [Token Factory model catalog](https://tokenfactory.nebius.com/model-catalog.md) and are pinned in [`docs/agent-architecture.md`](docs/agent-architecture.md) §Models.
- Nebius credits: the hackathon Token Factory allocation for the Nebius × NVIDIA Global AI Hackathon ([devpost](https://nebiusglobalaihackathon.devpost.com/)).

## Setup

```bash
uv sync                       # Python 3.13, installs the package
cp .env.example .env          # then fill in NEBIUS_API_KEY
uv run model-x-ray            # smoke check: prints the banner
```

Optional in `.env`: `GOOGLE_APPLICATION_CREDENTIALS` (Google Sheets), `LANGSMITH_API_KEY` (tracing, off by default), model overrides and demo rate limits. The API serves `.xlsx` today; the Google Sheets source and sandbox sit behind the same `SpreadsheetSource` / `Sandbox` interface but are not wired into the server yet (#13, #14). The app ships with `demo_models/demo.xlsx`; the benchmark set is generated with `uv run tools/generate_dataset.py --output models --per-set 2`.

## Tests

```bash
uv run pytest                 # offline, no credits: deep end-to-end tests
uv run pytest -m live         # live: calls Token Factory / Google APIs, spends credits
```

The suite runs realistic scenarios end to end (a whole formula trace, a full investigation against a planted error, a benchmark scenario) on scripted models, so it proves the system works rather than that functions return defaults.

## Supported Excel functions

Deliberately the small set real financial models use; an unsupported function is reported by name on the cell that uses it (and on anything downstream), never guessed or silently skipped.

- Maths: `SUM`, `AVERAGE`, `MIN`, `MAX`, `ROUND`, `ROUNDDOWN`, `INT`, `MOD`, `POWER`, `ABS`, `EXP`, `LN`, `SUMPRODUCT`, `LARGE`, `SMALL`
- Logic and information: `IF`, `IFERROR`, `AND`, `OR`, `NOT`, `CHOOSE`, `ISERROR`, `ISNUMBER`, `ISTEXT`, `ISBLANK`
- Counting and conditional: `COUNT`, `COUNTA`, `SUMIF`, `SUMIFS`, `COUNTIF`, `COUNTIFS`
- Lookups: `INDEX`, `MATCH`, `VLOOKUP`, `HLOOKUP`, `XLOOKUP`
- Dates: `EOMONTH`, `EDATE`, `YEAR`, `MONTH`, `DAY`, `DATE`
- Valuation, debt and statistics: `NPV`, `XNPV`, `IRR`, `XIRR`, `PMT`, `PPMT`, `NORMSDIST` / `NORM.S.DIST`
- References: `OFFSET`

Plus references (`A1`, `$C$7`, ranges, whole rows and columns such as `70:70`, other sheets, quoted names, workbook defined names), operators (`+ - * / ^ &`, comparisons), percentages, `_xlfn.` prefixes, and Excel-faithful error semantics (`IF` evaluates only the branch it returns, `IFERROR` never hides an unsupported function). Full spec: [`docs/spreadsheet-core.md`](docs/spreadsheet-core.md).

Circular references (interest on average debt, cash sweeps) are calculated iteratively, like Excel, when the file has iterative calculation switched on, with the file's own iteration limit and precision.

Not supported: links to other workbooks (`=[1]May!J10`; the values live in another file, so open it and paste its values), Data Tables and VBA functions. Each is reported by name instead of computed wrongly.

## Why these Nemotron models

The agent never asks a model to calculate: the Excel engine produces every number. What the model must do is judge a formula the way an expert analyst would and drive tools over several steps. So we chose by the benchmarks that measure those two skills, then checked the choice on our own task.

| Skill the agent needs | Benchmark (NVIDIA model cards) | Nemotron 3 Super | Nemotron 3.5 Super |
|---|---|---|---|
| Expert reasoning: is this formula right? | GPQA Diamond | 79.2 | **89.5** |
| Hard expert questions | HLE, text only, no tools | 18.3 | **31.8** |
| Multi-step tool use | τ²-bench retail / airline / telecom | 62.8 / 56.3 / 64.4 | **69.2 / 76.5 / 73.2** |
| Following instructions and formats | IFBench | **72.6** | 70.9 |

Both cost the same on Token Factory ($0.30 / $0.90 per 1M tokens), and 3.5 Super reads four times more context (1M tokens). The decisive test was ours: a five-year SaaS subscription forecast the agent had never seen, with five planted logic errors (churned customers added instead of subtracted, a contribution margin that skips support costs, revenue on 10 months a year, a margin divided by costs instead of revenue, a price typed 100 times too large) and a clean copy.

| On the unseen SaaS forecast | Nemotron 3 Super | Nemotron 3.5 Super |
|---|---|---|
| Errors fixed and verified | 0 of 5 | **4 of 5** |
| Errors seen | 1 of 5 | **5 of 5** (the price typo is flagged for a person, never fixed with an invented value) |
| False alarms on the clean copy | 0 | 0 |
| Tokens for the whole set | 307,000 | 442,000 |

Nemotron 3 Super read "Closing customers = Opening customers + New customers + Churned customers" and answered that every line matched its label; 3.5 Super caught it in all three votes and fixed the whole line. It spends more tokens only because it goes on to test, verify and correct what it finds; on a clean file both spend about the same. The Investigator and the Verifier run on 3.5 Super; 3 Super stays available as the `super-3` benchmark set-up.

The mapper (the one call that labels every line and period of a sheet) and `locate` stay on 3 Super, for a measured reason. 3.5 Super passes every tool-calling check (40 of 40, with a faster slowest call than 3 Super), but as the mapper of a real 436-line Damodaran DCF it spent its whole 8,192-token output reasoning and never returned the map, the failure Lightning showed before: on a real 63-line project-finance model Lightning wrote its reasoning as text and hit the same limit without calling the tool, while Nemotron 3 Super returned all 63 lines and 24 periods in 7 seconds (about 1,900 output tokens, 0.3 cents), cached per file revision (PR #97). A failed map never stops an investigation.

The report writer is the exception. `explain` is the last step, has no tools and no structured output, and Super spent about 9 s and 2,000 output tokens on a three-to-six-sentence report, the largest wait left after the Investigator; it runs on Lightning with a 1,400-token cap. The narrative is checked against the brief before it is shown (plain prose, the patched cell named, only evidence ids that exist), and the deterministic report is used when that check fails, so a faster writer can never lose a citation.

## How we evaluate it

The proof of value is planted errors: the generated models carry 75 known mistakes (hardcoded numbers where the row uses formulas, broken references, sign flips, range errors, period slips), and the Enron Errors Corpus adds real spreadsheets with known corrections. Every diagnosis is scored against the known answer (cell, cause and fix) per step, through four set-ups that differ only in configuration: rules alone, Nano with the tools, Super with the tools (what the app runs), and Super with the whole sheet pasted as text and no tools.

174 variants, 696 investigations, run on 21 Oct 2026 with Nemotron 3 Super, before the Investigator and the Verifier moved to Nemotron 3.5 Super and before the logic review of #181; 31 failed with errors and are excluded:

| Set-up | Root cause top-1 | Fix accuracy | False alarms | Latency p50 | Cost / investigation |
|---|---|---|---|---|---|
| rules only | 22% | 0% | 100% | 0.0 s | $0.0000 |
| Nano + tools | 82% | 81% | 7% | 97 s | $0.0072 |
| Super + tools (the app) | 75% | 74% | 4% | 20 s | $0.0123 |
| Super, sheet in the prompt, no tools | 92% | 92% | 25% | 15 s | $0.0068 |

The tools are not what finds the cell on a 63-line model: a strong model with the whole sheet in its prompt does better on planted errors. It is also wrong about models that are fine: it invents a root cause in one of four healthy or deliberately hardcoded models, where the tool loop leaves them alone. The tools are also the only thing that scales to a workbook the context window cannot hold, and what produces the clickable evidence. The gap is measured and open in #179, not smoothed over. The per-type table, the per-step metrics (locate, trace, verdict) and the confusion matrix are in the generated report, `docs/benchmark.md`, which `scripts/benchmark.sh` writes together with the raw `docs/benchmark-results.json` and the chart (`--render-only` re-renders; none of the three is committed). Metrics and scoring rules: [`docs/evaluation.md`](docs/evaluation.md). The held-out splits are frozen in `docs/damodaran-split.json` and `docs/enron-split.json`.

## Links

- Devpost submission: <https://nebiusglobalaihackathon.devpost.com/>
- Architecture and design: [`docs/agent-architecture.md`](docs/agent-architecture.md)
- Roadmap: [GitHub issues](https://github.com/ol1ak5/model-x-ray/issues)

## License

Apache 2.0 – see [LICENSE](LICENSE).

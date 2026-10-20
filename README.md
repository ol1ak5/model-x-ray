# Model X-Ray

**The debugger for financial models.** Model X-Ray is an evidence-first Nemotron agent that investigates surprising outputs in financial spreadsheets. Given a question such as "Why did EBITDA jump in 2030E?", it locates the cell behind the question, traces the dependency graph, diagnoses the root cause, tests a fix in a sandbox copy of the workbook, verifies the result, explains it with clickable evidence, and returns a corrected copy — only after a human approves the change.

Every number it reports comes from deterministic code or from the spreadsheet's own recalculation. The LLM never does arithmetic and may only quote tool results; a wrong hypothesis is shown, rejected with evidence, and replaced rather than quietly dropped.

## Demo scenario

The repository ships the model the app serves by default, `demo_models/demo.xlsx`: a three-sheet deal model (P&L, Assumptions, Summary; EUR m, 2024A–2028E) with two planted mistakes:

- `P&L!G5` (COGS, 2025A) reads `=G4*Assumptions!$C$5` where the row uses `=-G4*…`, so COGS flips sign and gross profit shows 285.8 instead of 84.7.
- `P&L!I6` (gross profit, 2027E) is a typed `95.65` — the 2026E figure — where the row adds revenue and COGS.

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

Ten nodes over a LangGraph state machine: **load** opens the workbook and **map** labels its lines and periods, **locate** resolves the question to a cell (code first, Nemotron only when several cells match — the user picks in a pause), **trace** walks the dependency graph and records causal contributions as evidence, **diagnose** runs a hypothesis loop with an evidence budget, **test** applies the proposed patch in a sandbox copy and compares before/after values, **verify** has an adversarial Nemotron Verifier try to break the diagnosis with a fixed evidence package, and **explain** renders the narrative report citing the recorded evidence ids. **human_review** pauses for the decision and **apply_fix** writes the corrected copy after approval. Design details: [`docs/agent-architecture.md`](docs/agent-architecture.md).

## Built on Nebius × NVIDIA

All LLM calls run on **Nebius Token Factory** (OpenAI-compatible) through LangChain's `ChatOpenAI`, using NVIDIA open-source **Nemotron** models:

| Role | Model |
|---|---|
| Investigator, Verifier, model mapper, locate | `nvidia/nemotron-3-super-120b-a12b` (262K context, $0.30 / $0.90 per 1M tokens) |
| Report writer (`explain`) | `nvidia/Nemotron-3_5-Lightning` (1M context, $0.06 / $0.24) |
| Benchmark small-model set-up | `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` ($0.06 / $0.24) |
| Benchmark hardest-verification set-up | `nvidia/Nemotron-3-Ultra-550b-a55b` (1M context, $1.00 / $3.00) |

- Base URL: `https://api.tokenfactory.nebius.com/v1/` — key in `NEBIUS_API_KEY` (`.env`, never committed); every role is overridable via `NEBIUS_MODEL_<ROLE>`.
- Token Factory docs: <https://docs.tokenfactory.nebius.com/> (model list, function calling, structured output, rate limits).
- Model IDs, context windows and prices were verified live with `GET /v1/models` on 6 Oct 2026 and are pinned in [`docs/agent-architecture.md`](docs/agent-architecture.md) §Models.
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

The suite runs realistic scenarios end to end — a whole formula trace, a full investigation against a planted error, a benchmark scenario — on scripted models, so it proves the system works rather than that functions return defaults.

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

The mapper (the one call that labels every line and period of a sheet) started on the fastest candidate, `Nemotron-3_5-Lightning`, which passed every tool-calling check. On a real 63-line project-finance model, however, Lightning wrote its reasoning as text and hit its 8,192-token output limit without ever calling the tool — while **Nemotron 3 Super** returned all 63 lines and 24 periods in 7 seconds (~1,900 output tokens ≈ 0.3 cents), cached per file revision, so the cost is paid once per file. The mapper role moved to Super (PR #97). The Investigator, Verifier and locator stay on Super for the same reason: one strong model keeps the structured-output contracts (diagnosis, verdict, target choice) in one place.

The report writer is the exception. `explain` is the last step, has no tools and no structured output, and Super spent about 9 s and 2,000 output tokens on a three-to-six-sentence report, the largest wait left after the Investigator; it runs on Lightning with a 1,400-token cap. The narrative is checked against the brief before it is shown — plain prose, the patched cell named, only evidence ids that exist — and the deterministic report is used when that check fails, so a faster writer can never lose a citation.

## How we evaluate it

The proof of value is planted errors: the generated Damodaran models carry 75 known mistakes (hardcoded numbers where the row uses formulas, broken references, sign flips, range errors, period slips), and the Enron Errors Corpus adds real spreadsheets with known corrections. The agent's diagnosis is scored against the known answer — cell, cause, and fix — per step, in a four-way benchmark (rules baseline vs three Nemotron set-ups). Metrics and scoring rules: [`docs/evaluation.md`](docs/evaluation.md); regenerate with `scripts/benchmark.sh`, which writes `docs/benchmark-results.json`, `docs/benchmark.md` and `docs/benchmark.svg` (generated, not committed; the only committed run is `docs/benchmark-before101.md`). The held-out splits are frozen in `docs/damodaran-split.json` and `docs/enron-split.json`.

## Links

- Devpost submission: <https://nebiusglobalaihackathon.devpost.com/>
- Architecture and design: [`docs/agent-architecture.md`](docs/agent-architecture.md)
- Roadmap: [GitHub issues](https://github.com/ol1ak5/model-x-ray/issues)

## License

Apache 2.0 — see [LICENSE](LICENSE).

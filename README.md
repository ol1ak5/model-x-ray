# Model X-Ray

![License](https://img.shields.io/badge/License-Apache%202.0-blue)
![Python](https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white)
![NVIDIA Nemotron](https://img.shields.io/badge/NVIDIA-Nemotron%203.5%20Super-76B900?logo=nvidia&logoColor=white)
![Nebius](https://img.shields.io/badge/Runs%20on-Nebius%20Token%20Factory-0055FF)
![LangGraph](https://img.shields.io/badge/Built%20with-LangGraph-1C3C3C)

An AI agent built for financial model auditing, powered by NVIDIA Nemotron, that uncovers hidden errors, reasons through financial logic, and verifies every proposed fix through independent workbook recalculation. Every correction is evidence-based, and no changes are made without the user’s approval.

## Try it Live


## The Problem

Financial models drive billion-dollar decisions, yet a single broken formula can distort an entire valuation without anyone noticing. In 2012, an error in JPMorgan’s Value-at-Risk model understated the bank’s risk exposure leading to the so-called “London Whale” scandal, that resulted in approximately $6Bn in trading losses for the bank.

Even if AI looks like the obvious reviewer for errors that escape from the human's eyes, LLMs struggle with numerical precision and nested logic, and can produce convincing explanations while getting the number wrong. Financial models don’t need plausible explanations. They need verifiable results.

## The Solution
Model X-Ray that pairs NVIDIA Nemotron with a deterministic calculation engine, just as an experienced financial analyst combines expertise with reliable tools. Nemotron reasons through the model, interpreting formulas, distinguishing real errors from deliberate choices, and proposing fixes. The engine independently maps formula dependencies and recalculates values, grounding every conclusion in verifiable calculations rather than AI-generated numbers.

> [!IMPORTANT]
> Nemotron never does arithmetic. Every number in a report comes from the calculation engine, and nothing changes in your workbook until you approve it.

## Setup

```bash
uv sync                       # Python 3.13, installs the package
cp .env.example .env          # then fill in NEBIUS_API_KEY
uv run model-x-ray            # smoke check: prints the banner
```

> [!TIP]
> Want to see it work in a minute? Upload any file from [`demo/simple-errors`](demo/simple-errors) or [`demo/saas-errors`](demo/saas-errors): each one has a single planted error, and `00-clean.xlsx` has none.

## Tests

```bash
uv run pytest                 # offline, no credits: deep end-to-end tests
uv run pytest -m live         # live: calls Token Factory / Google APIs, spends credits
```

## How it Works

The agent is a LangGraph state machine. Each step uses the NVIDIA Nemotron model that fits its job. The steps that compute use the engine and no model at all.

```mermaid
flowchart TD
    __start__([Excel workbook]) --> load_sheet["load_sheet<br/>engine"]
    load_sheet --> map_model["map_model<br/>Nemotron 3 Super"]
    map_model --> locate["locate<br/>code, Nemotron 3 Super if needed"]
    locate --> trace["trace<br/>engine"]
    trace --> diagnose["diagnose · Investigator<br/>Nemotron 3.5 Super"]
    diagnose --> test["test<br/>engine, sandbox copy"]
    test --> verify["verify · Verifier<br/>engine checks + Nemotron 3.5 Super"]
    verify -. "rejected, retry" .-> diagnose
    verify -. "confirmed" .-> explain["explain<br/>Nemotron 3.5 Lightning"]
    explain --> human_review{"human_review<br/>you"}
    human_review -. "edit the fix" .-> test
    human_review -. "approve" .-> apply_fix["apply_fix<br/>engine, corrected copy"]
    human_review -. "reject" .-> __end__([End])
    apply_fix --> __end__
```
| Step | What it does | Model |
|---|---|---|
| `load_sheet` | Opens the workbook and reads every formula | Engine |
| `map_model` | Labels every line and period (revenue, cost, ratio) | Nemotron 3 Super |
| `locate` | Picks the cell to investigate; checks the whole model when there is no question | Code, Nemotron 3 Super only if needed |
| `trace` | Follows the dependency graph and measures what drives each change | Engine |
| `diagnose` | The Investigator. Rules propose suspects and the engine tests each fix on a copy; Nemotron judges whether each one is an error or a deliberate choice, and when none is, it reviews the model's logic line by line, three times, keeping what a majority finds | Nemotron 3.5 Super |
| `test` | Applies the fix to a sandbox copy and recalculates | Engine |
| `verify` | Engine checks, then the Verifier tries to break the fix; the engine re-checks every objection. A rejected fix goes back to `diagnose` | Nemotron 3.5 Super |
| `explain` | Writes the report in plain language, checked by code before it is shown | Nemotron 3.5 Lightning |
| `human_review` | Shows the cell, the cause, the evidence and the numbers before and after, and waits for you | You |
| `apply_fix` | Writes the corrected copy; the original workbook never changes | Engine |

## Built on Nebius × NVIDIA

All LLM calls run on **Nebius Token Factory** (OpenAI-compatible) through LangChain's `ChatOpenAI`, using NVIDIA open-source **Nemotron** models:

| Model | Used for | Context | Price per 1M tokens (in / out) |
|---|---|---|---|
| `nvidia/Nemotron-3.5-Super-VL` | Investigator, Verifier | 1M | $0.30 / $0.90 |
| `nvidia/nemotron-3-super-120b-a12b` | Mapper, locate; benchmark comparison | 256K | $0.30 / $0.90 |
| `nvidia/Nemotron-3_5-Lightning` | Report writer | 1M | $0.06 / $0.24 |
| `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` | Benchmark only: does a small model suffice? | 256K | $0.06 / $0.24 |
| `nvidia/Nemotron-3-Ultra-550b-a55b` | Benchmark only: the largest model | 1M | $1.00 / $3.00 |

## Supported Excel functions

| Family | Functions |
|---|---|
| Maths | `SUM` `AVERAGE` `MIN` `MAX` `ROUND` `ROUNDDOWN` `INT` `MOD` `POWER` `ABS` `EXP` `LN` `SUMPRODUCT` `LARGE` `SMALL` |
| Logic and information | `IF` `IFERROR` `AND` `OR` `NOT` `CHOOSE` `ISERROR` `ISNUMBER` `ISTEXT` `ISBLANK` |
| Counting and conditional | `COUNT` `COUNTA` `SUMIF` `SUMIFS` `COUNTIF` `COUNTIFS` |
| Lookups and references | `INDEX` `MATCH` `VLOOKUP` `HLOOKUP` `XLOOKUP` `OFFSET` |
| Dates | `EOMONTH` `EDATE` `YEAR` `MONTH` `DAY` `DATE` |
| Valuation, debt, statistics | `NPV` `XNPV` `IRR` `XIRR` `PMT` `PPMT` `NORMSDIST` |
| Other | Cross-sheet references, ranges, whole rows and columns, defined names, circular references (solved iteratively) |

**Not supported:** links to other workbooks, Data Tables and VBA. Each is reported by name on the cell that uses it, never guessed.

Full spec: [`docs/spreadsheet-core.md`](docs/spreadsheet-core.md).

### The Models We Built It On

Model X-Ray was developed and tuned on three sets of workbooks, keeping part of the real models aside for the final score:

| Set | What it is | Errors |
|---|---|---|
| **Damodaran valuation models** | 26 public spreadsheets by Aswath Damodaran (NYU Stern): DCFs, cost of capital, capital budgeting; a median of 125 rows and 218 formulas | 95 planted (typed values, wrong references, flipped signs, period slips); 21 models for tuning, 5 held out |
| **Synthetic deal models** | A three-sheet deal model (assumptions, five-year P&L, summary) and 174 copies of it, each with one planted error, plus clean copies and copies with deliberate, documented values | 150 planted, 24 controls |
| **Logic test models** | A five-year budget and a SaaS subscription forecast the agent had never seen, in [`demo/`](demo) | 15 planted, including 7 logic errors where a formula contradicts its own label |

## What Nemotron Adds

Measured on the synthetic deal models (12 variants per error type plus 24 controls, one run each).

| Error type | Rules only | Rules + Nemotron 3.5 Super |
|---|---|---|
| Typed number in place of a formula | 12 of 12 | **12 of 12** |
| Formula pointing to the wrong cell | 8 of 12 | **11 of 12** |
| SUM over the wrong range | 10 of 12 | **12 of 12** |
| Flipped sign | 11 of 12 | **12 of 12** |
| Formula pointing to the wrong period | 8 of 12 | **12 of 12** |
| Blended error (the symptom is not the cause) | 11 of 12 | **11 of 12** |
| **Planted errors fixed** | 72 of 84 (86%) | **82 of 84 (98%)** |
| False alarms on deliberate values | 12 of 12 ❌ | **0 of 12** ✅ |
| False alarms on clean models | 0 of 12 ✅ | **0 of 12** ✅ |

> [!NOTE]
> Single runs on small test models (12 per error type). They show the difference between rules and Nemotron, not a final accuracy on real-world workbooks.

## How Nemotron and Token Factory Power It

- **Nemotron 3.5 Super** is the Investigator and the Verifier: it judges every formula, reviews the model's logic and tries to break every fix.
- **Nemotron 3 Super** labels every line and period of the workbook.
- **Nemotron 3.5 Lightning** writes the final report.
- One Token Factory endpoint gave us all five models, so moving the reasoning steps to 3.5 Super was a one-line change, measured the same day.

| | Nemotron 3 Super | Nemotron 3.5 Super |
|---|---|---|
| GPQA Diamond, expert reasoning (NVIDIA) | 79.2 | **89.5** |
| τ²-bench airline, tool use (NVIDIA) | 56.3 | **76.5** |
| Unseen SaaS model, errors fixed (ours) | 0 of 5 | **4 of 5** |
| Price per 1M tokens (in / out) | $0.30 / $0.90 | $0.30 / $0.90 |

## How we evaluate it

## How We Evaluate It

- **Known answers.** Every test model carries errors we planted ourselves, so each diagnosis is scored against the truth: the right cell, the right cause, and a fix that restores the original value.
- **Controls count as much as errors.** Clean models and values a modeller typed on purpose must be left alone; "fixing" one is a false alarm.
- **Three test sets.** 174 synthetic deal models (one planted error each, plus clean and deliberate copies), Damodaran's public valuation models with planted errors, and two logic test models in [`demo/`](demo).
- **Held-out models.** Part of the Damodaran models is kept aside and used only for the final score, so the agent is never tuned on the models that grade it.
- **Rules alone vs rules + Nemotron.** The same models are checked with the language model switched off and on; the results are in [What Nemotron Adds](#what-nemotron-adds).
- **Reproducible.** `scripts/benchmark.sh` reruns the benchmark; metrics and scoring rules are in [`docs/evaluation.md`](docs/evaluation.md).

## Feedback on Token Factory and the NVIDIA models

**What worked well**

- One OpenAI-compatible endpoint and one key gave us five Nemotron models, so each step of the agent uses the model that fits it.
- Switching the reasoning steps from Nemotron 3 Super to 3.5 Super was a one-line change: fixed errors on an unseen model went from 0 of 5 to 4 of 5, at the same price.
- With Nemotron, the agent fixed 98% of planted errors against 86% for rules alone, with no false alarm on deliberate values (rules alone broke 12 of 12).
- A full check of a model costs one to three cents.

**What would help**

- **Errors returned as answers:** long calls sometimes came back as HTTP 200 with `[ERROR: Agent failed ... timed out after 90 seconds]` as the reply. A non-200 status would let clients retry safely.
- **Reasoning that never reaches the tool call:** Nemotron 3.5 Super sometimes used its whole output budget reasoning and returned no tool call. A per-request way to cap reasoning would help.
- **Model metadata in the API:** prices, context windows and output limits are only in the web catalogue, not in `GET /v1/models`.
- **New models announced in the API:** a changelog or deprecation field would help teams notice new models like Nemotron 3.5 Super.

## Links

- Devpost submission: <https://nebiusglobalaihackathon.devpost.com/>
- Architecture and design: [`docs/agent-architecture.md`](docs/agent-architecture.md)
- Roadmap: [GitHub issues](https://github.com/ol1ak5/model-x-ray/issues)

## License

Apache 2.0 – see [LICENSE](LICENSE).

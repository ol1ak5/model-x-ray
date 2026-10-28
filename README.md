# Model X-Ray

<p align="center">
  <img alt="License" src="https://img.shields.io/badge/License-Apache%202.0-blue">
  <img alt="Python" src="https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white">
  <img alt="NVIDIA Nemotron" src="https://img.shields.io/badge/NVIDIA-Nemotron%203.5%20Super-76B900?logo=nvidia&logoColor=white">
  <img alt="Nebius" src="https://img.shields.io/badge/Runs%20on-Nebius%20Token%20Factory-0055FF">
  <img alt="LangGraph" src="https://img.shields.io/badge/Built%20with-LangGraph-1C3C3C">
</p>

The debugger for financial models. An AI agent powered by NVIDIA Nemotron that hunts down the errors hiding in Excel workbooks and proves every fix before a single cell changes.

- 🌐 Live demo: <https://model-x-ray.vercel.app>
- 🏆 Devpost submission:
- 🎬 Demo video (YouTube):

> **Track:** Best Apps and Agents – Nebius x NVIDIA Global AI Hackathon 2026

## Try It Live

Open the [live demo](https://model-x-ray.vercel.app) and press **Try the demo** to watch the agent check a European power purchase agreement model with 2,400 formulas and three planted errors, or upload your own `.xlsx`.

<p align="center"><img src="docs/screenshot-start.png" alt="The opening screen" width="800"></p>

## The Problem

Every big financial decision starts in a spreadsheet. And one wrong cell is enough.

> **$6,000,000,000** – JPMorgan, 2012<br>
> A risk model that divided by a sum instead of an average understated the risk, and the "London Whale" trades lost $6 billion

> **$2,600,000,000** – Fidelity Magellan, 1995<br>
> One missing minus sign turned a $1.3 billion loss into a gain, and the fund's reported figures were $2.6 billion off

A real model has thousands of formulas across dozens of tabs, and nobody has time to trace every one by hand. AI looks like the obvious reviewer, but language models are built to reason, not to calculate. They can explain a number convincingly and still get it wrong. A financial model doesn't need a plausible answer. It needs a proven one.

## The Solution

Model X-Ray checks your model the way an experienced financial analyst does. **Nemotron reasons. The engine calculates.**

- **NVIDIA Nemotron** reads the model, judges every suspect cell, tells a real error from a deliberate choice, and argues against its own fix.
- **A calculation engine** maps every formula and recalculates the whole workbook, so no number in the answer is guessed by AI.
- **You, the human in the loop,** approve, edit or reject every fix before anything changes in your file, and can ask the agent about any error or fix you are unsure of.

<p align="center"><img src="docs/screenshot-review.png" alt="The three planted errors in the PPA model, found at once and waiting for approval" width="800"></p>

Designed with M&A and deal teams, investment bankers, corporate finance and FP&A analysts in mind, it works for anyone who needs to trust the numbers in a spreadsheet.

## What It Checks

- **Seven error types:** typed values, wrong references, flipped signs, incomplete ranges, wrong periods, logic errors (a formula that contradicts its own label) and unusual inputs.
- **52 Excel functions,** from `SUM` and `XLOOKUP` to `NPV`, `IRR` and `OFFSET`, plus cross-sheet references, defined names and circular references. Full list: [`docs/spreadsheet-core.md`](docs/spreadsheet-core.md).
- **Links to other workbooks, Data Tables and VBA** are not supported yet. When a check needs one of them, the agent stops and tells you which cell and which formula it could not calculate, instead of guessing a number.

## Architecture

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
| Step | What it does |
|---|---|
| `load_sheet` | Opens the workbook and reads every formula |
| `map_model` | Labels every line and period (revenue, cost, ratio) |
| `locate` | Picks the cell to investigate, checks the whole model when there is no question |
| `trace` | Follows the dependency graph and measures what drives each change |
| `diagnose` | The Investigator. Rules propose suspects and the engine tests each fix on a copy. Nemotron judges whether each one is an error or a deliberate choice, and when none is, it reviews the model's logic line by line, three times, keeping what a majority finds |
| `test` | Applies the fix to a sandbox copy and recalculates |
| `verify` | Engine checks, then the Verifier tries to break the fix; the engine re-checks every objection. A rejected fix goes back to `diagnose` |
| `explain` | Writes the report in plain language, checked by code before it is shown |
| `human_review` | Shows the cell, the cause, the evidence and the numbers before and after, and waits for you |
| `apply_fix` | Writes the corrected copy, the original workbook never changes |

## Built on NVIDIA Nemotron and Nebius Token Factory

Every language-model call runs on **Nebius Token Factory**, through one OpenAI-compatible endpoint and one key. Each step uses the Nemotron model that fits its job:

| Model | Its job |
|---|---|
| **Nemotron 3.5 Super** | Investigator and Verifier: judges every suspect and tries to break every fix |
| **Nemotron 3 Super** | Mapper: labels every line and period of the workbook |
| **Nemotron 3.5 Lightning** | Writer: turns the evidence into a plain-language report |

Why Nemotron 3.5 Super:

| | Nemotron 3 Super | Nemotron 3.5 Super |
|---|---|---|
| GPQA Diamond, expert reasoning (NVIDIA) | 79.2 | **89.5** ✅ |
| τ²-bench airline, tool use (NVIDIA) | 56.3 | **76.5** ✅ |
| Unseen SaaS model, errors fixed (ours) | 0 of 5 | **4 of 5** ✅ |
| Price per 1M tokens (in / out) | $0.30 / $0.90 | $0.30 / $0.90 |

## How We Tested It

### The Workbooks We Tuned It On

The agent's rules and prompts were developed and tuned on three sets of workbooks:

| Set | Explanation | Errors |
|---|---|---|
| **Damodaran valuation models** | 26 public spreadsheets by Aswath Damodaran (NYU Stern): DCFs, cost of capital, capital budgeting; a median of 125 rows and 218 formulas | 95 planted (typed values, wrong references, flipped signs, period slips) |
| **Synthetic models** | A three-sheet model (assumptions, five-year P&L, summary) and 174 copies of it, each with one planted error, plus clean copies and copies with numbers typed on purpose and explained in a note, which must be left alone | 150 planted, 24 controls |
| **Logic test models** | A five-year budget and a SaaS subscription forecast, in [`demo/`](demo) | 15 planted, including 7 logic errors |

### Results

Every test model carries errors we planted ourselves, so each answer is scored against a known correct value. Measured on 21 and 22 Oct 2026 on the synthetic workbooks above (12 variants per error type plus 24 controls). Method and scoring rules: [`docs/evaluation.md`](docs/evaluation.md).

| | Rules only | Rules + Nemotron 3.5 Super |
|---|---|---|
| Typed number in place of a formula | 12 of 12 | **12 of 12** |
| Formula pointing to the wrong cell | 8 of 12 | **11 of 12** |
| SUM over the wrong range | 10 of 12 | **12 of 12** |
| Flipped sign | 11 of 12 | **12 of 12** |
| Formula pointing to the wrong period | 8 of 12 | **12 of 12** |
| Blended error (the symptom is not the cause) | 11 of 12 | **11 of 12** |
| Formula that contradicts its own label | 12 of 12 | **12 of 12** |
| **Planted errors fixed** | 72 of 84 (86%) | **82 of 84 (98%)** |
| False alarms on values set on purpose | 12 of 12 ❌ | **0 of 12** ✅ |
| False alarms on clean models | 0 of 12 ✅ | **0 of 12** ✅ |

### Final Test on Unseen Workbooks

Five of the Damodaran models were kept aside from the start and never used to tune the agent. They were used only for the final score:

| | Rules + Nemotron 3.5 Super |
|---|---|
| Planted errors found and fixed | **18 of 20 (90%)** |
| Planted errors the agent pointed at | **20 of 20** |
| False alarms on the clean originals | **0 of 5** ✅ |
| Cost and time per check (median, model with an error) | **1.4 cents, 65 seconds** |

A model with no error takes longer, up to about 4 minutes, because Nemotron reviews every line before calling it clean.

## Tech Stack

| Stack | Used for |
|---|---|
| NVIDIA Nemotron 3.5 Super, 3 Super and 3.5 Lightning | Investigating, verifying, mapping the model and writing the report |
| Nebius Token Factory | Every model call, through one OpenAI-compatible endpoint |
| LangGraph | The agent graph, its retry loop and the pause for your decision |
| Our own calculation engine (Python) | Parsing formulas, the dependency graph and recalculating the workbook |
| openpyxl | Reading the `.xlsx` and writing the corrected copy |
| FastAPI | The API and the live progress stream |
| React, TypeScript and Vite | The web app |
| Vercel | Hosting the web app and the API on one address |
| uv, pytest and Vitest | Packaging and tests |

## Quick Start

You need Python 3.13 with [uv](https://docs.astral.sh/uv/), Node.js (or bun) and a Nebius Token Factory key.

```bash
git clone https://github.com/ol1ak5/model-x-ray.git && cd model-x-ray
uv sync                       # installs the Python package
cp .env.example .env          # then set NEBIUS_API_KEY to your Token Factory key
scripts/dev.sh                # starts the API and the web app together
```

Open <http://localhost:5173>, press **Try the demo**, or upload your own `.xlsx`. The API docs are on <http://localhost:8000/docs>.

```bash
uv run pytest                 # offline tests, no credits spent
uv run pytest -m live         # live tests on Token Factory, spends credits
```

## Feedback on Token Factory and the NVIDIA models

**What worked well**

- One OpenAI-compatible endpoint and one key gave us every Nemotron model we needed, so each step of the agent uses the model that fits it.
- Switching the reasoning steps from Nemotron 3 Super to 3.5 Super was a one-line change: fixed errors on an unseen model went from 0 of 5 to 4 of 5, at the same price.
- With Nemotron, the agent fixed 98% of planted errors against 86% for rules alone, with no false alarm on deliberate values (rules alone broke 12 of 12).
- A check of a model with an error costs about 1.4 cents and takes about a minute (medians on models the agent never saw).

**What would help**

- **"System is overloaded" during peak hours:** some calls ended with HTTP 529 even after retries; we now wait 5, 15 and 30 seconds before giving up. A `Retry-After` header would let clients wait exactly as long as needed.
- **Errors returned as answers:** long calls sometimes came back as HTTP 200 with `[ERROR: Agent failed ... timed out after 90 seconds]` as the reply. A non-200 status would let clients retry safely.
- **Reasoning that never reaches the tool call:** Nemotron 3.5 Super sometimes used its whole output budget reasoning and returned no tool call. We now ask once more with `chat_template_kwargs.enable_thinking=false`, which answers at once with no reasoning tokens; a per-request way to cap reasoning, rather than switch it off, would help.
- **Model metadata in the API:** prices, context windows and output limits are only in the web catalogue, not in `GET /v1/models`.
- **New models announced in the API:** a changelog or deprecation field would help teams notice new models like Nemotron 3.5 Super.

## License

Copyright © 2026 Olga Aksenova and Guillermo Martín-Coello. Licensed under the [Apache License 2.0](LICENSE).

*Built for the Nebius x NVIDIA Global AI Hackathon 2026*

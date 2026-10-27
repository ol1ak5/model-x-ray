# 🩻 Model X-Ray

<p align="center">
  <img alt="License" src="https://img.shields.io/badge/License-Apache%202.0-blue">
  <img alt="Python" src="https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white">
  <img alt="NVIDIA Nemotron" src="https://img.shields.io/badge/NVIDIA-Nemotron%203.5%20Super-76B900?logo=nvidia&logoColor=white">
  <img alt="Nebius" src="https://img.shields.io/badge/Runs%20on-Nebius%20Token%20Factory-0055FF">
  <img alt="LangGraph" src="https://img.shields.io/badge/Built%20with-LangGraph-1C3C3C">
</p>

The debugger for financial models: an AI agent powered by NVIDIA Nemotron that hunts down the errors hiding in Excel workbooks and proves every fix before a single cell changes.

- 🌐 Live demo: <https://model-x-ray.vercel.app>
- 🏆 Devpost submission:
- 🎬 Demo video (YouTube):

## ▶️ Try It Live

Open the [live demo](https://model-x-ray.vercel.app) and press **Try the demo** to watch the agent check a European power purchase agreement model with 2,400 formulas and three planted errors, or upload your own `.xlsx`.

![The opening screen](docs/screenshot-start.png)

## 🎯 The Problem

Every big financial decision starts in a spreadsheet. And one wrong cell is enough.

| | |
|---|---|
| **$6,000,000,000** | JPMorgan, 2012: an error in its Value-at-Risk model hid the risk before the "London Whale" losses. |
| **$2,600,000,000** | Fidelity Magellan, 1995: one missing minus sign turned a loss into a gain. |

A real model has thousands of formulas across dozens of tabs, and nobody has time to trace every one by hand.

AI looks like the obvious reviewer, but language models are built to reason, not to calculate. They can explain a number convincingly and still get it wrong. A financial model doesn't need a plausible answer. It needs a proven one.

## 💡 The Solution

Model X-Ray checks your model the way an experienced financial analyst does. **Nemotron reasons. The engine calculates.**

- **NVIDIA Nemotron** reads the model, judges every suspect cell, tells a real error from a deliberate choice, and argues against its own fix.
- **A calculation engine** maps every formula and recalculates the whole workbook, so no number in the answer is guessed by AI.

Designed with M&A and deal teams, investment bankers, corporate finance and FP&A analysts in mind, it works for anyone who needs to trust the numbers in a spreadsheet.

## 🧠 How It Works

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

## 📊 Results

Every test model carries errors we planted ourselves, so each answer is scored against a known correct value. Measured on 21 and 22 Oct 2026 on the synthetic models below (12 variants per error type plus 24 controls). Method and scoring rules: [`docs/evaluation.md`](docs/evaluation.md).

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

## 🧪 The Models We Built It On

Model X-Ray was developed and tuned on three sets of workbooks:

| Set | What it is | Errors |
|---|---|---|
| **Damodaran valuation models** | 26 public spreadsheets by Aswath Damodaran (NYU Stern): DCFs, cost of capital, capital budgeting; a median of 125 rows and 218 formulas | 95 planted (typed values, wrong references, flipped signs, period slips) |
| **Synthetic models** | A three-sheet model (assumptions, five-year P&L, summary) and 174 copies of it, each with one planted error, plus clean copies and copies with deliberate, documented values | 150 planted, 24 controls |
| **Logic test models** | A five-year budget and a SaaS subscription forecast, in [`demo/`](demo) | 15 planted, including 7 logic errors where a formula contradicts its own label |

### Tested on Models It Never Saw

Five of the Damodaran models were kept aside from the start and never used to tune the agent. They were used only for the final score:

| | Rules + Nemotron 3.5 Super |
|---|---|
| Planted errors found and fixed | **18 of 20 (90%)** |
| Planted errors the agent pointed at | **20 of 20** |
| False alarms on the clean originals | **0 of 5** |
| Cost and time per check (median, model with an error) | **1.4 cents, 65 seconds** |

A model with no error takes longer, up to about 4 minutes, because Nemotron reviews every line before calling it clean.

## 🟩 Built on NVIDIA Nemotron and Nebius Token Factory

Every language-model call runs on **Nebius Token Factory**, through one OpenAI-compatible endpoint and one key. Each step uses the Nemotron model that fits its job:

| Model | Its job |
|---|---|
| **Nemotron 3.5 Super** | Investigator and Verifier: judges every suspect and tries to break every fix |
| **Nemotron 3 Super** | Mapper: labels every line and period of the workbook |
| **Nemotron 3.5 Lightning** | Writer: turns the evidence into a plain-language report |

Why Nemotron 3.5 Super:

| | Nemotron 3 Super | Nemotron 3.5 Super |
|---|---|---|
| GPQA Diamond, expert reasoning (NVIDIA) | 79.2 | **89.5** |
| τ²-bench airline, tool use (NVIDIA) | 56.3 | **76.5** |
| Unseen SaaS model, errors fixed (ours) | 0 of 5 | **4 of 5** |
| Price per 1M tokens (in / out) | $0.30 / $0.90 | $0.30 / $0.90 |

## 📐 What It Checks

- **Seven error types:** typed values, wrong references, flipped signs, incomplete ranges, wrong periods, logic errors (a formula that contradicts its own label) and unusual inputs.
- **52 Excel functions,** from `SUM` and `XLOOKUP` to `NPV`, `IRR` and `OFFSET`, plus cross-sheet references, defined names and circular references. Full list: [`docs/spreadsheet-core.md`](docs/spreadsheet-core.md).
- **Links to other workbooks, Data Tables and VBA** are not supported yet. When a check needs one of them, the agent stops and tells you which cell and which formula it could not calculate, instead of guessing a number.

## 🚀 Quick Start

You need Python 3.13 with [uv](https://docs.astral.sh/uv/), Node.js (or bun) and a Nebius Token Factory key.

```bash
uv sync                       # installs the Python package
cp .env.example .env          # then set NEBIUS_API_KEY to your Token Factory key
scripts/dev.sh                # starts the API and the web app together
```

Open <http://localhost:5173>, press **Try the demo**, or upload your own `.xlsx`. The API docs are on <http://localhost:8000/docs>.

```bash
uv run pytest                 # offline tests, no credits spent
uv run pytest -m live         # live tests on Token Factory, spends credits
```

## 💬 Feedback on Token Factory

**What worked well:** one endpoint and one key gave us every Nemotron model we needed, and upgrading a step to a newer model was a one-line change, measured the same day.

**What would help:**

- A `Retry-After` header on "System is overloaded" (HTTP 529), so clients wait exactly as long as needed.
- A non-200 status for errors that now come back as HTTP 200 answers, such as `[ERROR: Agent failed ... timed out]`.
- A per-request cap on reasoning: Nemotron 3.5 Super sometimes spends its whole output budget thinking and returns no tool call. We now ask once more with thinking switched off; a cap would be better than a switch.
- Prices, context windows and output limits in `GET /v1/models`, and a changelog for new models.

More: [architecture](docs/agent-architecture.md) · [roadmap](https://github.com/ol1ak5/model-x-ray/issues)

## 📄 License

Copyright © 2026 Olga Aksenova and Guillermo Martín-Coello. Licensed under the [Apache License 2.0](LICENSE).

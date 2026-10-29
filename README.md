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

## The Agent

It finds the error, tests the fix on a copy and waits for your approval.

- **7 error types:** typed values, wrong references, flipped signs, incomplete ranges, wrong periods, logic errors and unusual inputs.
- **52 Excel functions:** `SUM`, `SUMIF`, `XLOOKUP`, `NPV`, `IRR`, plus cross-sheet references, defined names and circular references ([full list](docs/spreadsheet-core.md)).
- **Not supported yet:** links to other workbooks, Data Tables and VBA.

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

## How We Tested It

We built and tuned it on 217 financial models (26 Damodaran valuation models, 174 synthetic models and 17 logic test models in [`demo/`](demo)). Results on the synthetic set ([method](docs/evaluation.md)):

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

## Final Test

We ran the final test on five Damodaran models that were never used to tune the agent.

| | Rules + Nemotron 3.5 Super |
|---|---|
| Planted errors found and fixed | **18 of 20 (90%)** |
| Planted errors the agent pointed at | **20 of 20** |
| False alarms on the clean originals | **0 of 5** ✅ |
| Cost and time per check (median, model with an error) | **1.4 cents, 65 seconds** |

## Built on NVIDIA Nemotron and Nebius Token Factory

| Model | Its job |
|---|---|
| **Nemotron 3.5 Super** | Investigator and Verifier: judges every suspect and tries to break every fix |
| **Nemotron 3 Super** | Mapper: labels every line and period of the workbook |
| **Nemotron 3.5 Lightning** | Writer: turns the evidence into a plain-language report and answers your questions about any error or fix |

## What Token Factory Accelerated

- **One endpoint, every model.** One OpenAI-compatible API and one key serve all three Nemotron models.
- **The right model for each step.** 3.5 Super reasons, 3 Super maps, 3.5 Lightning writes.
- **Upgrades in one line.** Moving to Nemotron 3.5 Super was a config change. Fixed errors on an unseen SaaS model went from 0 of 5 to 4 of 5.
- **No new price.** 3.5 Super costs the same as 3 Super: $0.30 / $0.90 per million tokens.
- **Our stack worked as is.** LangGraph and LangChain's OpenAI client connected with no adapter.
- **Cheap enough for a public demo.** About 1.4 cents per error checked.
- **Fast enough to run live.** About a minute per error, with every suspect checked at the same time.

## License

Copyright © 2026 Olga Aksenova and Guillermo Martín-Coello. Licensed under the [Apache License 2.0](LICENSE).

*Built for the Nebius x NVIDIA Global AI Hackathon 2026*

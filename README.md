# Model X-Ray

The debugger for financial models. An AI agent powered by NVIDIA Nemotron that finds the errors hiding in Excel workbooks and proves every fix. Designed for everyone who needs their numbers to be right.

- **Live demo:** <https://model-x-ray.vercel.app>
- **Devpost submission:** <https://devpost.com/software/model-x-ray>
- **Demo video (YouTube):** <https://youtu.be/jmA4NN_MMyY>

> **Track:** Best Apps and Agents – Nebius x NVIDIA Global AI Hackathon 2026

<p align="center"><img src="docs/screenshot-start.png" alt="Model X-Ray: the opening screen" width="800"></p>

## Try It

Open the [live demo](https://model-x-ray.vercel.app) and press **Try the demo**. It checks a European power purchase agreement model with 2,400 formulas and three planted errors, and stops for your approval before it writes anything. You can also upload your own `.xlsx`, up to 4.5 MB.

## What It Does

Model X-Ray finds the errors in your Excel model, tests each fix on a copy and waits for your approval. If you are not sure, you can ask about any error or fix.

- **Seven error types:** typed values, wrong references, flipped signs, incomplete ranges, wrong periods, logic errors (a formula that contradicts its own label) and unusual inputs.
- **52 Excel functions**, cross-sheet references, defined names and circular references ([full list](docs/spreadsheet-core.md)).
- **Not supported yet:** links to other workbooks, Data Tables and VBA. When a check needs one of them, the agent names the cell and the formula and stops instead of guessing.

## Why It Matters

A wrong cell moves real money and stays invisible. In 2012 a JPMorgan risk model divided by a sum instead of an average, and the "London Whale" trades lost $6.2 billion. In 1995 a missing minus sign turned Fidelity Magellan's $1.3 billion capital loss into a gain.

A real model has thousands of formulas across dozens of tabs. AI looks like the obvious reviewer, but a language model explains a number convincingly and still gets it wrong. Model X-Ray keeps the two jobs apart: **Nemotron reasons, the engine calculates.** Every claim is recalculated, and nothing changes without your approval.

## How It Works

```mermaid
flowchart LR
    A([Excel workbook]) --> B["Understand<br/>engine + Nemotron 3 Super"]
    B --> C["Diagnose<br/>Nemotron 3.5 Super"]
    C --> D["Test and verify<br/>engine + Nemotron 3.5 Super"]
    D -. "rejected" .-> C
    D --> E["Explain<br/>Nemotron 3.5 Lightning"]
    E --> F{"You decide"}
    F -. "edit" .-> D
    F -- "approve" --> G([Corrected copy])
```

Dotted arrows are the loops: the Verifier sends a rejected fix back to Diagnose, and an edited fix is tested again. The full graph with its ten steps, the retry budget and the time limits are in [`docs/agent-architecture.md`](docs/agent-architecture.md).

## How We Tested the Agent

We built and tuned the agent on 217 workbooks: 26 public valuation models by Aswath Damodaran (NYU Stern), 174 synthetic models with one planted error each plus clean and deliberate-value controls, and 17 logic test models in [`demo/`](demo). Every model carries a known correct answer, so each run is scored against it ([method](docs/evaluation.md)).

| Synthetic set, 12 variants per type | Rules only | Rules + Nemotron 3.5 Super |
|---|---|---|
| Typed number in place of a formula | 12 of 12 | **12 of 12** |
| Formula pointing to the wrong cell | 8 of 12 | **11 of 12** |
| SUM over the wrong range | 10 of 12 | **12 of 12** |
| Flipped sign | 11 of 12 | **12 of 12** |
| Formula pointing to the wrong period | 8 of 12 | **12 of 12** |
| Blended error (the symptom is not the cause) | 11 of 12 | **11 of 12** |
| Formula that contradicts its own label | 12 of 12 | **12 of 12** |
| **Planted errors fixed** | 72 of 84 (86%) | **82 of 84 (98%)** |
| False alarms on deliberate values | 12 of 12 ❌ | **0 of 12** ✅ |
| False alarms on clean models | 0 of 12 ✅ | **0 of 12** ✅ |

On five Damodaran models kept aside and never used for tuning, it fixed 18 of 20 planted errors (90%), pointed at 20 of 20, and raised no false alarm on the five clean originals. A check on a model with an error takes a median of 65 seconds and 1.4 cents.

## Built on NVIDIA Nemotron and Nebius Token Factory

| Model | Its job |
|---|---|
| **Nemotron 3.5 Super** | Investigator and Verifier: judges every suspect and tries to break every fix |
| **Nemotron 3 Super** | Mapper: labels every line and period of the workbook |
| **Nemotron 3.5 Lightning** | Writer: explains each error in plain language and answers your questions |

All three are served on Nebius Token Factory through one OpenAI-compatible endpoint (`NEBIUS_BASE_URL`, by default `https://api.tokenfactory.nebius.com/v1/`) and one key. No other Nebius service is used: the web app and the API are hosted on Vercel.

## What Token Factory Accelerated

- **One endpoint, every model.** One key and one OpenAI-compatible API serve all three Nemotron models. LangChain's OpenAI client (`langchain-openai`) needed no adapter.
- **The right model for each step.** 3.5 Super reasons, 3 Super maps, 3.5 Lightning explains.
- **Upgrades in one line.** Moving the Investigator to Nemotron 3.5 Super was a config change: on an unseen SaaS model, fixed errors went from 0 of 5 to 4 of 5.
- **No new price.** 3.5 Super costs the same as 3 Super, $0.30 / $0.90 per million tokens.
- **Cheap and fast enough for a public demo.** About 1.4 cents and about a minute per check of a model with an error, with every suspect checked at the same time.

## Run It Locally

You need Python 3.13 with [uv](https://docs.astral.sh/uv/), Node 20.19+ or [bun](https://bun.sh), and a Nebius Token Factory key.

```bash
git clone https://github.com/ol1ak5/model-x-ray.git
cd model-x-ray
uv sync
cp .env.example .env
```

In `.env`, set `NEBIUS_API_KEY`. The models folder already points at `demo_models`, the two workbooks that ship with the repository. Point `MODEL_X_RAY_MODELS_DIR` somewhere else to check your own files. Then start both servers:

```bash
scripts/dev.sh
```

Open <http://localhost:5173> and press **Try the demo**. The rest of `.env.example` is optional: model overrides, file paths and cleanup, CORS, the public demo limits and LangSmith tracing.

The web app is one client of an HTTP API, so a check can also run without the browser. The API reference is on <http://localhost:8000/docs>, and every route is in [`docs/api.md`](docs/api.md).

## Docs

| | |
|---|---|
| [Agent architecture](docs/agent-architecture.md) | the ten nodes, the models, the retry loop |
| [API](docs/api.md) | every route, the payloads, the limits |
| [Spreadsheet core](docs/spreadsheet-core.md) | the 52 functions, the parser, circular references |
| [Evaluation](docs/evaluation.md) | the workbooks, the scoring rules, the numbers |
| [Deployment](docs/deployment.md) | Vercel, the environment, the owner's steps |
| [Frontend](docs/frontend.md) | the two screens and the run kept in the browser |
| [Persistence](docs/persistence.md) | checkpointer, memory, what survives a reload |
| [Financial formulas](docs/financial-formulas.md) | the reference definitions the agent checks against |
| [Demo video](docs/video.md) | the Remotion project, the voice, the music and the subtitles |

## Development

```bash
uv run pytest           # 261 offline tests, no credits spent
uv run pytest -m live   # 26 live tests against Token Factory, spends credits
```

`scripts/serve.sh` runs the API alone, `scripts/export_graph.sh` refreshes the graph picture, and `scripts/screenshots.sh` renders the page at two sizes. The working contract for changes is in [`AGENTS.md`](AGENTS.md): branches, draft PRs, issue format and commit naming.

## Feedback on Token Factory and the NVIDIA Models

**What worked well**

- One OpenAI-compatible endpoint and one key for every Nemotron model, with no adapter for LangChain's OpenAI client.
- Switching the reasoning steps from Nemotron 3 Super to 3.5 Super was a one-line change, measured the same day, at the same price.

**What would help**

- **"System is overloaded" during peak hours.** Some calls ended with HTTP 529 even after retries. We now wait 5, 15 and 30 seconds before giving up. A `Retry-After` header would let clients wait exactly as long as needed.
- **Errors returned as answers.** Long calls sometimes came back as HTTP 200 with `[ERROR: Agent failed ... timed out after 90 seconds]` as the reply. A non-200 status would let clients retry safely.
- **Reasoning that never reaches the tool call.** Nemotron 3.5 Super sometimes spent its whole output budget reasoning and returned no tool call. We now ask once more with `chat_template_kwargs.enable_thinking=false`, which answers at once. A per-request cap on reasoning, rather than an on/off switch, would help.
- **Model details in the API.** `GET /v1/models` returns only the model IDs. Prices, context windows and output limits are only in the web catalogue.
- **New models announced in the API.** A changelog or deprecation field would help teams notice new models like Nemotron 3.5 Super.

## License

Copyright © 2026 Olga Aksenova and Guillermo Martín-Coello. Licensed under the [Apache License 2.0](LICENSE).

*Built for the Nebius x NVIDIA Global AI Hackathon 2026.*

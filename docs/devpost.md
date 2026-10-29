# Devpost submission draft

Everything below is for the Devpost form. Fill the links once the video is public and the repository is open.

| Field | Value |
|---|---|
| Project name | Model X-Ray |
| Track | Best Apps and Agents |
| Elevator pitch | An AI agent that finds the errors hiding in Excel financial models, explains the cause with evidence, and proves every fix in a copy before you approve it. |
| Live demo | <https://model-x-ray.vercel.app> |
| Repository | <https://github.com/ol1ak5/model-x-ray> |
| Demo video | YouTube link, under three minutes |
| License | Apache 2.0 |
| Built with | Python, FastAPI, LangGraph, React, TypeScript, Vite, openpyxl, NVIDIA Nemotron 3.5 Super, NVIDIA Nemotron 3 Super, NVIDIA Nemotron 3.5 Lightning, Nebius Token Factory, Vercel |

## Project story

### Inspiration

Every big financial decision starts in a spreadsheet, and one wrong cell is enough. In 2012 a JPMorgan risk model divided by a sum instead of an average, and the London Whale trades lost $6.2 billion. In 1995 a missing minus sign turned Fidelity Magellan's $1.3 billion capital loss into a capital gain. Neither error was exotic. Both survived review by people who were in a hurry.

We wanted to build the reviewer that does not get tired and does not get fooled. A language model alone cannot do it: it explains a number convincingly and still gets the arithmetic wrong. A rules engine alone cannot do it either, because most real errors are not a broken pattern, they are a formula that contradicts what its own label says.

### What it does

Open the demo and press one button. Model X-Ray reads a European corporate power purchase agreement model with ten renewable offers and 2,400 formulas, finds three errors planted in it, explains each cause with the cells that prove it, and stops. Nothing is written to your file until you approve.

It checks seven kinds of error: typed values where a formula belongs, formulas pointing at the wrong cell, flipped signs, sums over the wrong range, formulas pointing at the wrong period, formulas that contradict their own label, and unusual inputs. It calculates 52 Excel functions, cross-sheet references, defined names and circular references. It does not support VBA, Data Tables or links to other workbooks yet, and when a check needs one of them it says which cell and which formula it could not calculate instead of guessing.

You can upload your own `.xlsx`, and you can ask the agent about any finding it made or any fix it proposed.

### How it works

Four steps, each with one job.

1. **Understand.** The agent reads the workbook and works out what each sheet, line and period is, so it does not have to guess from cell addresses.
2. **Investigate.** It locates the cell behind the question, traces where the number comes from through the formulas and the dependency graph, and judges every suspect cell, separating a real error from a deliberate choice. It is asked to argue both ways, and three independent reviews vote when no rule has flagged anything.
3. **Prove.** The fix is written to a copy of the workbook and the whole model is recalculated by our own engine. Three deterministic checks then ask whether the anomaly is gone, whether the cells downstream still agree, and whether the formula matches its row again. A separate Verifier model reads the result and tries to break the fix. If any check fails, the run goes back and tries another cause.
4. **Approve.** You approve, edit or reject the fix, and download the corrected workbook. The original never changes.

### Built with NVIDIA Nemotron and Nebius Token Factory

Three Nemotron models share the work, each chosen for what it is good at:

- **Nemotron 3.5 Super** is the Investigator and the Verifier. It judges every suspect cell, proposes the fix, and then attacks that fix as an adversary.
- **Nemotron 3 Super** maps the workbook, labelling every line and period. It stays on this role because it answers the mapping tool call reliably, while 3.5 Super can spend its output budget reasoning instead.
- **Nemotron 3.5 Lightning** writes the plain-language report and answers the reviewer's questions.

All three are served on Nebius Token Factory through one OpenAI-compatible endpoint and one key. LangGraph connected with no adapter. Moving the Investigator from 3 Super to 3.5 Super was a configuration change, and on an unseen SaaS forecast fixed errors went from 0 of 5 to 4 of 5 at the same price, $0.30 and $0.90 per million tokens.

Two things about Token Factory shaped the design. First, a reasoning model can spend its entire output budget on thinking; when the structured conclusion does not arrive, the agent asks once more with thinking disabled, and that is what keeps a check inside one browser request. Second, an overloaded or rejected call can answer HTTP 200 with an error string in the body, so every answer is parsed and retried rather than trusted, with waits of 5, 15 and 30 seconds on overload.

### How we tested it

We tuned the agent on 217 workbooks: 26 public Damodaran valuation models, 174 synthetic models with one planted error each plus clean copies and copies with deliberately typed values that must be left alone, and 17 logic test models. Every model carries a known correct answer, so every run is scored.

On the synthetic set, with 12 variants per error type:

| | Rules only | Rules + Nemotron 3.5 Super |
|---|---|---|
| Planted errors fixed | 72 of 84 (86%) | 82 of 84 (98%) |
| False alarms on deliberately typed values | 12 of 12 | 0 of 12 |
| False alarms on clean models | 0 of 12 | 0 of 12 |

The important row is the middle one. Rules alone produce a plausible finding on every deliberate value, which is exactly the noise that makes a reviewer stop reading. The model turns that into zero false alarms while finding more real errors.

Five Damodaran models were kept aside and never used for tuning. On them the agent fixed 18 of 20 planted errors, pointed at 20 of 20, and raised no false alarm on the five clean originals. A check on a model with an error takes a median of 65 seconds and costs 1.4 cents.

### Design decisions that were not obvious

- **The model never produces a number that is shown as fact.** Any value in the answer was recalculated by the engine.
- **Rules and the model are separate votes.** Rules find patterns; the model judges intent. When both agree the run is short; when only one speaks, the other is asked to justify it.
- **The adversarial Verifier is a second conversation,** not another prompt to the same one, so it does not inherit the Investigator's confidence.
- **Every check has a time budget.** A full review stops at 210 seconds of model time so one browser request can finish, and it says so in the report rather than pretending there was nothing to find.
- **The deployment is stateless.** The run travels in the browser, so the server holds no session between requests and a reload does not lose the review.

### What is next

- Table mode and the model profile reach the report and the page, so the agent explains what kind of model it is looking at instead of only the cell.
- The financial formula library grows: recognised definitions of WACC, terminal value, FCFF and similar lines, checked against the engine.
- The Enron Errors Corpus evaluation is finished, to measure the agent on real-world errors rather than planted ones.
- Support for links between workbooks and Data Tables.

### What we learned

The hard part of auditing a model is not finding suspicious formulas, it is deciding which suspicious formula is wrong. A rule can tell you a cell breaks its row. Only something that reads the label can tell you the cell is right and the row is mislabelled. Separating those two judgements, and proving the answer with recalculation, is the whole product.

## Feedback on Nebius Token Factory, AI Cloud and the NVIDIA models

- **One endpoint for every model, OpenAI compatible.** One key served all three Nemotron models, and LangGraph's client needed no adapter. Model IDs, context and prices come from `GET /v1/models` and are stable enough to pin in configuration.
- **Reasoning is a budget, not a free feature.** Nemotron 3.5 Super spends output tokens on thinking when it is asked for structured output. Disabling thinking for that one call made the difference between a check that finishes and one that times out.
- **Errors can arrive as 200s.** An overloaded or rejected call can return a normal 200 with an error string in the body. A client that trusts the status code will present that string as an answer, so parsing the body mattered more than handling 429.
- **Same price across the two Super generations.** Moving up to 3.5 Super changed quality, not cost, which made the upgrade an easy call.
- **What we did not use.** Nebius AI Cloud and Serverless Endpoints would be the natural home for a larger deployment, and we kept the hackathon demo on Vercel for time.

## Links

- Live demo: <https://model-x-ray.vercel.app>
- Repository, Apache 2.0: <https://github.com/ol1ak5/model-x-ray>
- Architecture, API, evaluation method and benchmark numbers: `docs/` in the repository

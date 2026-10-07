# Nemotron tool calling on Token Factory

Research issue #4. Question: can Nemotron on Nebius Token Factory, called through LangChain's `ChatOpenAI`, reliably request our tools, pick the right one, use a tool result to choose its next call, and return structured output? The whole agent design depends on it.

**Answer: yes.** All three candidate models passed every check. The repeated-run reliability measurement is deferred to the real tool schemas (follow-up below), because measuring toy tools ten times would mostly confirm what these results already show.

## Setup

- Client: `build_chat_model(model)` in `src/model_x_ray/llm.py`, a `ChatOpenAI` with `base_url=https://api.tokenfactory.nebius.com/v1/`, `NEBIUS_API_KEY` from `.env`, `temperature=0`.
- Tools: three fakes with the shapes of the real read-only tools: `get_cell`, `trace_precedents`, `compare_formulas`. Each returns fixed text.
- Date: 6 to 7 October 2026. Libraries: langgraph 1.2.14, langchain-openai 1.6.7.

## Models

Confirmed with `GET /v1/models`. IDs are case-sensitive; the lowercase Nano ID in the Nebius cookbook does not exist in the live catalog.

| Model ID | Active / total parameters | Context | Price per 1M tokens (in / out) | Region |
|---|---|---|---|---|
| `nvidia/nemotron-3-super-120b-a12b` | 12B / 120B | 262K | $0.30 / $0.90 | us-central1 |
| `nvidia/Nemotron-3_5-Lightning` | 3B / 30B | 1M | $0.06 / $0.24 | eu-north1 |
| `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` | 3B / 30B | 262K | $0.06 / $0.24 | eu-north1 |
| `nvidia/Nemotron-3-Ultra-550b-a55b` | 55B / 550B | 1M | $1.00 / $3.00 | us-central1 |

The global base URL lists 25 models; the regional `us-central1` URL lists 18. We use the global one.

## Results: live tests

`tests/test_tool_calling.py`, run with `uv run pytest -m live -v`. 15 of 15 pass.

| Test | What it proves | Super | Lightning | Nano |
|---|---|---|---|---|
| One tool, one question | The model requests a tool instead of guessing, with the right argument | Pass | Pass | Pass |
| Choose 1 of 3 tools, 3 questions | It picks the right tool from the descriptions alone | 3/3 | 3/3 | 3/3 |
| Two-step loop | It reads a `ToolMessage` result and uses it to choose the next call (`get_cell("H6")` after `trace_precedents` returned H6, H7) | Pass | Pass | Pass |

## Results: one measured run per scenario

`tools/measure_tool_calling.py --runs 1`. The script adds a structured-output scenario (classify five P&L rows as revenue, cost, subtotal or other via `with_structured_output(..., method="function_calling")`), which is what the Model mapper needs.

| Scenario | Super | Lightning | Nano |
|---|---|---|---|
| One tool | Pass, 0.96 s | Pass, 0.41 s | Pass, 1.13 s |
| Choose 1 of 3 tools (3 calls) | Pass, 2.04 s | Pass, 0.92 s | Pass, 4.26 s |
| Two-step loop (2 calls) | Pass, 1.53 s | Pass, 0.72 s | Pass, 3.10 s |
| Structured output | Pass, 1.63 s | Pass, 1.84 s | Pass, 4.32 s |

One run per cell is a signal, not a statistic. The consistent pattern is that Lightning is the fastest model and Nano the slowest, despite identical size and price.

## Decisions

| Use | Model | Status |
|---|---|---|
| Investigator, Verifier, `locate`, `explain` | Nemotron 3 Super | Confirmed for building |
| Model mapper and the small-model benchmark set-up | Nemotron 3.5 Lightning | Provisional: passed all checks and was fastest; confirm on the real tools |
| Fallback small model | Nemotron 3 Nano | Kept as fallback |
| Optional heavy verifier | Nemotron 3 Ultra | Not tested; only if the Verifier needs it |

Structured output works through tool calling (`method="function_calling"`). `supported_features` lists `tools` and `reasoning` but no JSON-schema mode, so we do not rely on `response_format` with a JSON schema.

## Cost

The 15 live tests plus the one-run measurement cost well under one US cent. A ten-run measurement of all scenarios is about 210 calls, roughly 3 cents, mostly Super.

## Limits

- Toy tools with clear, distinct descriptions and easy questions. Real tool schemas, ambiguous questions and real spreadsheets are harder.
- One run per scenario; no variance estimate yet.
- Reasoning tokens are billed as output and were not measured separately.

## Follow-ups

- Benchmark: tool-calling reliability on the real tool schemas, ten runs per scenario. The fake tools were swapped for the real investigation API in #33 (a one-run smoke passed on all three models); the ten-run re-measurement itself is #27 (`scripts/measure_tool_calling.sh` ready).
- Engine: production client factory (model registry from config, retries, timeouts, token and latency logging for the evaluators in #16).

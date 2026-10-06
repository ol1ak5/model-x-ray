---
name: nebius
description: Nebius Token Factory API — endpoint facts, docs map, model discovery, function calling and structured output with Nemotron through LangChain
---

# Nebius Token Factory

OpenAI-compatible inference API used for every LLM call in Model X-Ray (hackathon requirement: ≥1 NVIDIA open-source model on Nebius).

## Endpoint facts

- Base URL: `https://api.tokenfactory.nebius.com/v1/` (verified with a live `GET /v1/models` on 2026-10-06: 25 models). The regional `https://api.tokenfactory.us-central1.nebius.com/v1/` also works but lists only 18.
- Auth: `Authorization: Bearer $NEBIUS_API_KEY` (key from https://tokenfactory.nebius.com/project/api-keys, stored in `.env`, never committed).
- Standard OpenAI client: `OpenAI(base_url=..., api_key=...)` or LangChain `ChatOpenAI(base_url=..., api_key=...)` (`base_url` verified as a constructor param, langchain-openai 1.6.7).

## Docs map (read `llms.txt` first — it is the full page index)

- Index: https://docs.tokenfactory.nebius.com/llms.txt  (note: NOT docs.nebius.com — that 404s for token-factory paths)
- Intro/auth: https://docs.tokenfactory.nebius.com/api-reference/introduction
- Function calling: https://docs.tokenfactory.nebius.com/ai-models-inference/function-calling
- Structured output: https://docs.tokenfactory.nebius.com/ai-models-inference/json
- Rate limits: https://docs.tokenfactory.nebius.com/ai-models-inference/rate-limits
- Deprecations: https://docs.tokenfactory.nebius.com/june-2026-deprecation-notice.md (check before hardcoding a model id)
- Cookbook: https://github.com/nebius/token-factory-cookbook (tool-calling dir, `guided_json.ipynb`)

## Discover models and pricing (do this instead of guessing IDs)

```sh
curl -s https://api.tokenfactory.nebius.com/v1/models \
  -H "Authorization: Bearer $NEBIUS_API_KEY" | jq '.data[] | select(.id | test("nemotron"; "i"))'
```

`GET /v1/models` returns `RichModel` entries with `context_length`, `pricing` (prompt/completion per unit), `supported_features`, `regions`, `status`. Model cards carry a "JSON mode" tag for structured-output support.

## Model IDs (verified 2026-10-06 with `GET /v1/models`; IDs are case-sensitive)

| Use | ID | Price per 1M (in / out) |
|---|---|---|
| Investigator, Verifier, `locate`, `explain` | `nvidia/nemotron-3-super-120b-a12b` | $0.30 / $0.90 |
| Model mapper (candidate) | `nvidia/Nemotron-3_5-Lightning` | $0.06 / $0.24 |
| Model mapper (fallback) | `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` | $0.06 / $0.24 |
| Optional heavy verifier | `nvidia/Nemotron-3-Ultra-550b-a55b` | $1.00 / $3.00 |

The lowercase Nano ID `nvidia/nvidia-nemotron-3-nano-30b-a3b` from the Nebius cookbook does not exist in the live catalog.

## Function calling — what matters

- Model emits OpenAI-format `tool_calls`; **it never executes them** — we parse and run.
- `tool_choice: "auto"` (default) or forced `{"type":"function","function":{"name":"..."}}`.
- Feeds `ToolNode` in LangGraph unchanged. Reliability per model is what issue #4 measures (valid tool-call rate, correct tool choice, valid argument JSON, 2-step chains, latency over ≥20 prompts).

## Structured output — what matters

- `response_format={"type": "json_schema", "json_schema": {...}}` for strict, `{"type":"json_object"}` for loose.
- Docs' own advice: **also put the schema in the system/user prompt** — schema in the parameter alone underperforms.
- Not all models support it; check the "JSON mode" tag on the model card (i.e. check `supported_features` from `/v1/models`).
- This is what `InvestigationState` hypotheses, `map_model` labels, and Verifier verdicts depend on.

## Cost/latency discipline

- Per-model pricing comes from `/v1/models`; benchmark reports cost per investigation (`docs/evaluation.md`).
- Free credits: promo `NEBIUS-DEVPOST-GLOBAL26` (~$25) + Builder Program ($25) + LangSmith ($100), per issue #18. Small calls: Nemotron on Token Factory is cheap enough that the full 150-run benchmark costs a few dollars.

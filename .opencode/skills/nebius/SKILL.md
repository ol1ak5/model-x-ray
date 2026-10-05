---
name: nebius
description: Nebius Token Factory API — endpoint facts, docs map, model discovery, function calling and structured output with Nemotron through LangChain
---

# Nebius Token Factory

OpenAI-compatible inference API used for every LLM call in Model X-Ray (hackathon requirement: ≥1 NVIDIA open-source model on Nebius).

## Endpoint facts

- Base URL in current docs: `https://api.tokenfactory.nebius.com/v1/`
- Our `AGENTS.md` and `docs/agent-architecture.md` say `https://api.tokenfactory.us-central1.nebius.com/v1/` — **possibly stale; confirm with a live call in issue #4 and fix both docs in the same change.**
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

## Model IDs used by the design (confirm before hardcoding — issue #4)

| Use | ID |
|---|---|
| Investigator, Verifier, `locate`, `explain` | `nvidia/nemotron-3-super-120b-a12b` |
| Model mapper | `nvidia/nvidia-nemotron-3-nano-30b-a3b` |

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

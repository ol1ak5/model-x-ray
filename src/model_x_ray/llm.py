import os
import time
from typing import Any

from dotenv import load_dotenv
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import AIMessage, AnyMessage
from langchain_core.outputs import LLMResult
from langchain_core.runnables import Runnable
from langchain_openai import ChatOpenAI

from model_x_ray.state import RunLog

SUPER = "nvidia/Nemotron-3.5-Super-VL"
SUPER_3 = "nvidia/nemotron-3-super-120b-a12b"
LIGHTNING = "nvidia/Nemotron-3_5-Lightning"

ROLE_MODELS: dict[str, str] = {
    "investigator": SUPER,
    "verifier": SUPER,
    "mapper": SUPER_3,
    "locate": SUPER_3,
    "explain": LIGHTNING,
}
ROLE_MAX_TOKENS: dict[str, int] = {"explain": 1400}
DEFAULT_TIMEOUT = 120.0
DEFAULT_MAX_RETRIES = 3


def model_for_role(role: str) -> str:
    if role not in ROLE_MODELS:
        raise ValueError(f"Unknown role {role!r}; known roles: {', '.join(sorted(ROLE_MODELS))}")
    return os.environ.get(f"NEBIUS_MODEL_{role.upper()}") or ROLE_MODELS[role]


def model_name_of(llm: Any) -> str | None:
    return getattr(llm, "model_name", None) or getattr(llm, "_llm_type", None)


def build_chat_model(model: str | None = None, *, role: str | None = None) -> ChatOpenAI:
    load_dotenv()
    if model is not None:
        chosen = model
    elif role is not None:
        chosen = model_for_role(role)
    else:
        raise ValueError("build_chat_model needs a model id or a role")
    api_key = os.environ.get("NEBIUS_API_KEY")
    if not api_key:
        raise ValueError("NEBIUS_API_KEY is not set; copy .env.example to .env and add your Nebius Token Factory key")
    base_url = os.environ.get("NEBIUS_BASE_URL")
    if not base_url:
        raise ValueError("NEBIUS_BASE_URL is not set; copy .env.example to .env and set https://api.tokenfactory.nebius.com/v1/")
    return ChatOpenAI(
        model=chosen,
        base_url=base_url,
        api_key=api_key,
        temperature=0,
        max_tokens=ROLE_MAX_TOKENS.get(role) if role else None,
        timeout=DEFAULT_TIMEOUT,
        max_retries=DEFAULT_MAX_RETRIES,
    )


class UsageRecorder(BaseCallbackHandler):
    def __init__(self) -> None:
        self._started: dict[Any, float] = {}
        self.entries: list[dict[str, float | int | None]] = []

    def on_llm_start(self, serialized: dict, prompts: list[str], *, run_id: Any, **kwargs: Any) -> None:
        self._started[run_id] = time.perf_counter()

    def on_llm_end(self, response: LLMResult, *, run_id: Any, **kwargs: Any) -> None:
        started = self._started.pop(run_id, None)
        latency = (time.perf_counter() - started) * 1000 if started is not None else 0.0
        input_tokens, output_tokens, reasoning_tokens = _token_counts(response)
        self.entries.append(
            {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "reasoning_tokens": reasoning_tokens,
                "latency_ms": latency,
            }
        )


def _token_counts(response: LLMResult) -> tuple[int | None, int | None, int | None]:
    usage: dict = {}
    llm_output = response.llm_output or {}
    for key in ("usage", "token_usage"):
        if llm_output.get(key):
            usage = llm_output[key]
            break
    if not usage:
        for generation in response.generations:
            for candidate in generation:
                metadata = getattr(getattr(candidate, "message", None), "usage_metadata", None)
                if metadata:
                    usage = metadata
                    break
            if usage:
                break
    input_tokens = usage.get("prompt_tokens", usage.get("input_tokens"))
    output_tokens = usage.get("completion_tokens", usage.get("output_tokens"))
    details = usage.get("completion_tokens_details") or usage.get("output_token_details") or {}
    reasoning = details.get("reasoning_tokens", details.get("reasoning"))
    return _as_int(input_tokens), _as_int(output_tokens), _as_int(reasoning)


def _as_int(value: Any) -> int | None:
    return int(value) if value is not None else None


PROVIDER_ERROR_PREFIX = "[ERROR:"
PROVIDER_ATTEMPTS = 3


class ProviderFailure(RuntimeError):
    pass


def provider_error(result: Any) -> str | None:
    if not isinstance(result, AIMessage) or result.tool_calls:
        return None
    text = result.content if isinstance(result.content, str) else ""
    return text.strip() if text.strip().startswith(PROVIDER_ERROR_PREFIX) else None


def invoke_with_usage(
    runnable: Runnable,
    messages: list[AnyMessage],
    *,
    role: str,
    model: str | None,
) -> tuple[Any, list[RunLog]]:
    recorder = UsageRecorder()
    for _ in range(PROVIDER_ATTEMPTS):
        result = runnable.invoke(messages, config={"callbacks": [recorder]})
        failure = provider_error(result)
        if failure is None:
            break
    else:
        raise ProviderFailure(f"The AI service failed to answer the {role} after {PROVIDER_ATTEMPTS} attempts: {failure[:200]}")
    records: list[RunLog] = [
        {
            "role": role,
            "model": model,
            "input_tokens": entry["input_tokens"],
            "output_tokens": entry["output_tokens"],
            "reasoning_tokens": entry["reasoning_tokens"],
            "latency_ms": round(entry["latency_ms"], 3),
        }
        for entry in recorder.entries
    ]
    return result, records

import argparse
import statistics
import time
from collections.abc import Callable
from typing import Literal

from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.tools import tool
from pydantic import BaseModel

from model_x_ray.llm import build_chat_model

MODELS = [
    "nvidia/nemotron-3-super-120b-a12b",
    "nvidia/Nemotron-3_5-Lightning",
    "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B",
]


@tool
def get_cell(ref: str) -> str:
    """Return the value and formula of one spreadsheet cell, for example ref='P&L!H8'."""
    return "P&L!H8 = 52.0, formula =H6+H7"


@tool
def trace_precedents(ref: str) -> str:
    """List the cells that a cell's formula depends on (its inputs), for example ref='P&L!H8'."""
    return "P&L!H8 depends on P&L!H6, P&L!H7"


@tool
def compare_formulas(ref: str) -> str:
    """Compare a cell's formula with the formulas in the neighbouring cells of the same row and report whether it breaks the pattern, for example ref='P&L!F27'."""
    return "P&L!F27 =SUM(F20:F24); neighbours use rows 20 to 25; F27 deviates from the pattern"


TOOLS = {t.name: t for t in [get_cell, trace_precedents, compare_formulas]}

CHOICE_QUESTIONS = [
    ("What is the value of cell H8 on the P&L sheet?", "get_cell"),
    ("Which cells feed into the formula in P&L!H8?", "trace_precedents"),
    ("Does the formula in P&L!F27 follow the same pattern as its neighbouring cells?", "compare_formulas"),
]

SHEET_EXCERPT = """Row 4: Revenue | 185.2 | 200.0 | 216.0
Row 5: COGS | (101.9) | (110.0) | (118.8)
Row 6: Gross profit | 83.3 | 90.0 | 97.2
Row 7: Opex | (47.6) | (50.0) | (45.2)
Row 8: EBITDA | 35.7 | 40.0 | 52.0"""

EXPECTED_KINDS = {4: "revenue", 5: "cost", 6: "subtotal", 7: "cost", 8: "subtotal"}


class RowLabel(BaseModel):
    row: int
    label: str
    kind: Literal["revenue", "cost", "subtotal", "other"]


class RowLabels(BaseModel):
    rows: list[RowLabel]


def run_single_tool(model: str) -> bool:
    llm = build_chat_model(model).bind_tools([get_cell])
    response = llm.invoke("What is in cell H8 on the P&L sheet?")
    calls = response.tool_calls
    return len(calls) == 1 and calls[0]["name"] == "get_cell" and "H8" in calls[0]["args"].get("ref", "")


def run_tool_choice(model: str) -> bool:
    llm = build_chat_model(model).bind_tools(list(TOOLS.values()))
    for question, expected in CHOICE_QUESTIONS:
        response = llm.invoke(question)
        if not response.tool_calls or response.tool_calls[0]["name"] != expected:
            return False
    return True


def run_two_step_loop(model: str) -> bool:
    llm = build_chat_model(model).bind_tools(list(TOOLS.values()))
    messages = [HumanMessage(content="Which cells feed into P&L!H8? Then tell me what is in the first of them.")]
    first = llm.invoke(messages)
    if not first.tool_calls or first.tool_calls[0]["name"] != "trace_precedents":
        return False
    call = first.tool_calls[0]
    result = TOOLS[call["name"]].invoke(call["args"])
    messages += [first, ToolMessage(content=result, tool_call_id=call["id"])]
    second = llm.invoke(messages)
    return bool(second.tool_calls) and second.tool_calls[0]["name"] == "get_cell" and "H6" in second.tool_calls[0]["args"].get("ref", "")


def run_structured_output(model: str) -> bool:
    llm = build_chat_model(model).with_structured_output(RowLabels, method="function_calling")
    prompt = (
        "Classify every row of this P&L excerpt. kind is one of: revenue, cost, subtotal, other. "
        "Return one entry per row with its row number.\n\n" + SHEET_EXCERPT
    )
    result = llm.invoke(prompt)
    if not isinstance(result, RowLabels):
        return False
    kinds = {r.row: r.kind for r in result.rows}
    return kinds == EXPECTED_KINDS


SCENARIOS: dict[str, Callable[[str], bool]] = {
    "single tool": run_single_tool,
    "choose 1 of 3 tools (3 questions)": run_tool_choice,
    "two-step loop": run_two_step_loop,
    "structured output (row labels)": run_structured_output,
}


def measure(model: str, scenario: Callable[[str], bool], runs: int) -> tuple[int, list[float], list[str]]:
    passes = 0
    latencies: list[float] = []
    errors: list[str] = []
    for _ in range(runs):
        start = time.perf_counter()
        try:
            ok = scenario(model)
        except Exception as error:
            ok = False
            errors.append(type(error).__name__)
        latencies.append(time.perf_counter() - start)
        passes += int(ok)
    return passes, latencies, errors


def percentile(values: list[float], share: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, round(share * (len(ordered) - 1)))
    return ordered[index]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=10)
    parser.add_argument("--output", default="docs/research/nemotron-tool-calling-results.md")
    args = parser.parse_args()

    lines = [
        f"| Model | Scenario | Passed | Median latency (s) | p95 latency (s) | Errors |",
        "|---|---|---|---|---|---|",
    ]
    for model in MODELS:
        for name, scenario in SCENARIOS.items():
            passes, latencies, errors = measure(model, scenario, args.runs)
            row = (
                f"| `{model}` | {name} | {passes}/{args.runs} | "
                f"{statistics.median(latencies):.2f} | {percentile(latencies, 0.95):.2f} | "
                f"{', '.join(sorted(set(errors))) or '-'} |"
            )
            print(row, flush=True)
            lines.append(row)

    with open(args.output, "w") as file:
        file.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()

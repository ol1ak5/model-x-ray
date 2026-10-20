import pytest
from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.tools import tool

from model_x_ray.llm import build_chat_model

MODELS = [
    "nvidia/Nemotron-3.5-Super-VL",
    "nvidia/nemotron-3-super-120b-a12b",
    "nvidia/Nemotron-3_5-Lightning",
    "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B",
]

QUESTIONS = [
    ("What is the value of cell H8 on the P&L sheet?", "get_cell"),
    ("Which cells feed into the formula in P&L!H8?", "trace_precedents"),
    ("Does the formula in P&L!F27 follow the same pattern as its neighbouring cells?", "compare_formulas"),
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


@pytest.mark.live
@pytest.mark.parametrize("model", MODELS)
def test_model_calls_get_cell_with_the_right_reference(model: str) -> None:
    llm = build_chat_model(model).bind_tools([get_cell])

    response = llm.invoke("What is in cell H8 on the P&L sheet?")

    assert len(response.tool_calls) == 1
    call = response.tool_calls[0]
    assert call["name"] == "get_cell"
    assert "H8" in call["args"]["ref"]


@pytest.mark.live
@pytest.mark.parametrize("model", MODELS)
@pytest.mark.parametrize(("question", "expected_tool"), QUESTIONS)
def test_model_picks_the_right_tool_out_of_three(model: str, question: str, expected_tool: str) -> None:
    llm = build_chat_model(model).bind_tools([get_cell, trace_precedents, compare_formulas])

    response = llm.invoke(question)

    assert len(response.tool_calls) >= 1
    assert response.tool_calls[0]["name"] == expected_tool


@pytest.mark.live
@pytest.mark.parametrize("model", MODELS)
def test_model_uses_a_tool_result_to_choose_the_next_call(model: str) -> None:
    tools = {t.name: t for t in [get_cell, trace_precedents, compare_formulas]}
    llm = build_chat_model(model).bind_tools(list(tools.values()))
    messages = [HumanMessage(content="Which cells feed into P&L!H8? Then tell me what is in the first of them.")]

    first = llm.invoke(messages)
    assert first.tool_calls[0]["name"] == "trace_precedents"

    call = first.tool_calls[0]
    result = tools[call["name"]].invoke(call["args"])
    messages += [first, ToolMessage(content=result, tool_call_id=call["id"])]

    second = llm.invoke(messages)
    assert len(second.tool_calls) >= 1
    assert second.tool_calls[0]["name"] == "get_cell"
    assert "H6" in second.tool_calls[0]["args"]["ref"]

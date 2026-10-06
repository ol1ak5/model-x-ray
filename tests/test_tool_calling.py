import pytest
from langchain_core.tools import tool

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


@pytest.mark.live
@pytest.mark.parametrize("model", MODELS)
def test_model_calls_get_cell_with_the_right_reference(model: str) -> None:
    llm = build_chat_model(model).bind_tools([get_cell])

    response = llm.invoke("What is in cell H8 on the P&L sheet?")

    assert len(response.tool_calls) == 1
    call = response.tool_calls[0]
    assert call["name"] == "get_cell"
    assert "H8" in call["args"]["ref"]

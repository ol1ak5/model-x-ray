from collections.abc import Sequence
from typing import Any

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import tool

from model_x_ray.agents.investigator import build_investigator
from model_x_ray.llm import build_chat_model


@tool
def get_cell(ref: str) -> str:
    """Return the value and formula of one spreadsheet cell, for example ref='P&L!H8'."""
    return f"{ref} = 52.0, formula =H6+H7" if ref.endswith("H8") else f"{ref} = 97.2, formula =H4+H5"


@tool
def trace_precedents(ref: str) -> str:
    """List the cells that a cell's formula depends on (its inputs), for example ref='P&L!H8'."""
    return "P&L!H8 depends on P&L!H6, P&L!H7"


class AlwaysCallsATool(BaseChatModel):
    calls: int = 0

    @property
    def _llm_type(self) -> str:
        return "always-calls-a-tool"

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> "AlwaysCallsATool":
        return self

    def _generate(self, messages: list[BaseMessage], stop: list[str] | None = None, **kwargs: Any) -> ChatResult:
        self.calls += 1
        message = AIMessage(content="", tool_calls=[{"name": "get_cell", "args": {"ref": "P&L!H8"}, "id": f"call-{self.calls}"}])
        return ChatResult(generations=[ChatGeneration(message=message)])


def test_investigator_stops_at_the_tool_budget() -> None:
    investigator = build_investigator(AlwaysCallsATool(), [get_cell, trace_precedents], max_tool_calls=8)

    result = investigator.invoke({"messages": [HumanMessage(content="Why did EBITDA 2027 jump?")]})

    assert result["tool_calls_used"] == 8
    assert sum(1 for m in result["messages"] if m.type == "tool") == 8


@pytest.mark.live
def test_investigator_chains_tools_and_answers_with_nemotron() -> None:
    llm = build_chat_model("nvidia/nemotron-3-super-120b-a12b")
    investigator = build_investigator(llm, [get_cell, trace_precedents])

    result = investigator.invoke({"messages": [HumanMessage(content="Which cells feed into P&L!H8, and what is the value of the first one?")]})

    used = [m.name for m in result["messages"] if m.type == "tool"]
    assert used[:2] == ["trace_precedents", "get_cell"]
    assert result["messages"][-1].tool_calls == []
    assert "97.2" in result["messages"][-1].content

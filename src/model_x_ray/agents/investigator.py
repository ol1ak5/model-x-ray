from typing import Annotated, TypedDict

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AnyMessage
from langchain_core.tools import BaseTool
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode

MAX_TOOL_CALLS = 8


class InvestigatorState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    tool_calls_used: int


def build_investigator(llm: BaseChatModel, tools: list[BaseTool], max_tool_calls: int = MAX_TOOL_CALLS) -> CompiledStateGraph:
    model = llm.bind_tools(tools)
    tool_node = ToolNode(tools)

    def think(state: InvestigatorState) -> dict:
        return {"messages": [model.invoke(state["messages"])]}

    def act(state: InvestigatorState) -> dict:
        calls = state["messages"][-1].tool_calls
        results = tool_node.invoke({"messages": state["messages"]})
        return {"messages": results["messages"], "tool_calls_used": state.get("tool_calls_used", 0) + len(calls)}

    def next_step(state: InvestigatorState) -> str:
        last = state["messages"][-1]
        wants_tool = isinstance(last, AIMessage) and bool(last.tool_calls)
        if wants_tool and state.get("tool_calls_used", 0) < max_tool_calls:
            return "act"
        return END

    builder = StateGraph(InvestigatorState)
    builder.add_node("think", think)
    builder.add_node("act", act)
    builder.add_edge(START, "think")
    builder.add_conditional_edges("think", next_step, {"act": "act", END: END})
    builder.add_edge("act", "think")
    return builder.compile()

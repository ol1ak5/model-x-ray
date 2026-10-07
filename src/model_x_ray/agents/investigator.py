from typing import Annotated, Literal, TypedDict

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode
from pydantic import BaseModel

from model_x_ray.prompts import load_prompt

MAX_TOOL_CALLS = 8


class ProposedHypothesis(BaseModel):
    cell: str
    error_type: Literal["typed_value", "broken_reference", "inconsistent_range", "sign_or_period"]
    claim: str
    confidence: Literal["high", "medium", "low"]


class ProposedPatch(BaseModel):
    cell: str
    new_formula: str


class Diagnosis(BaseModel):
    hypotheses: list[ProposedHypothesis]
    patch: ProposedPatch | None


class InvestigatorState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    tool_calls_used: int
    diagnosis: Diagnosis | None


def build_investigator(llm: BaseChatModel, tools: list[BaseTool], max_tool_calls: int = MAX_TOOL_CALLS) -> CompiledStateGraph:
    model = llm.bind_tools(tools)
    structured = llm.with_structured_output(Diagnosis, method="function_calling")
    tool_node = ToolNode(tools)
    system = SystemMessage(content=load_prompt("investigator"))

    def think(state: InvestigatorState) -> dict:
        return {"messages": [model.invoke([system, *state["messages"]])]}

    def act(state: InvestigatorState) -> dict:
        calls = state["messages"][-1].tool_calls
        results = tool_node.invoke({"messages": state["messages"]})
        return {"messages": results["messages"], "tool_calls_used": state.get("tool_calls_used", 0) + len(calls)}

    def next_step(state: InvestigatorState) -> str:
        last = state["messages"][-1]
        wants_tool = isinstance(last, AIMessage) and bool(last.tool_calls)
        if wants_tool and state.get("tool_calls_used", 0) < max_tool_calls:
            return "act"
        return "conclude"

    def conclude(state: InvestigatorState) -> dict:
        messages = list(state["messages"])
        last = messages[-1]
        if isinstance(last, AIMessage) and last.tool_calls:
            messages += [ToolMessage(content="Tool budget exhausted.", tool_call_id=call["id"]) for call in last.tool_calls]
        diagnosis = structured.invoke([system, *messages, HumanMessage(content=load_prompt("investigator_conclude"))])
        return {"diagnosis": diagnosis}

    builder = StateGraph(InvestigatorState)
    builder.add_node("think", think)
    builder.add_node("act", act)
    builder.add_node("conclude", conclude)
    builder.add_edge(START, "think")
    builder.add_conditional_edges("think", next_step, {"act": "act", "conclude": "conclude"})
    builder.add_edge("act", "think")
    builder.add_edge("conclude", END)
    return builder.compile()

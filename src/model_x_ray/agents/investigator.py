from collections.abc import Callable
from typing import Annotated, Literal, TypedDict

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode
from pydantic import BaseModel

from model_x_ray.causal import render_causal_tree
from model_x_ray.prompts import load_prompt
from model_x_ray.state import InvestigationState

MAX_TOOL_CALLS = 8
MAX_OPEN_HYPOTHESES = 3


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
        remaining = max_tool_calls - state.get("tool_calls_used", 0)
        executed, overflow = calls[:remaining], calls[remaining:]
        answered = state["messages"][-1].model_copy(update={"tool_calls": executed})
        results = tool_node.invoke({"messages": [*state["messages"][:-1], answered]})
        budget_messages = [ToolMessage(content="Tool budget exhausted.", tool_call_id=call["id"]) for call in overflow]
        return {"messages": results["messages"] + budget_messages, "tool_calls_used": state.get("tool_calls_used", 0) + len(executed)}

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


def investigation_brief(state: InvestigationState) -> str:
    target = state["target"]
    lines = [
        f"Question: {state['question']}",
        f"Target: {target['sheet']}!{target['cell']} ({target['label']} {target['period']}) = {target['value']}, prior period {target['prior_cell']} = {target['prior_value']}",
    ]
    lines += [f"Contribution: {c['cell']} {c['label']} {c['delta']:+}" for c in state.get("contributions", [])]
    tree = state.get("causal_tree")
    if tree:
        lines.append("Cause tree (suspicious cells marked):")
        lines += [f"  {line}" for line in render_causal_tree(tree)]
    lines += [f"Already rejected, do not propose again: {h['cell']} ({h['error_type']})" for h in state.get("hypotheses", []) if h["status"] == "rejected"]
    return "\n".join(lines)


def make_diagnose_node(investigator: CompiledStateGraph) -> Callable[[InvestigationState], dict]:
    def diagnose(state: InvestigationState) -> dict:
        result = investigator.invoke({"messages": [HumanMessage(content=investigation_brief(state))]})
        diagnosis = result["diagnosis"]
        proposed = diagnosis.hypotheses[:MAX_OPEN_HYPOTHESES]
        first_number = len(state.get("hypotheses", [])) + 1
        hypotheses = [
            {
                "id": f"hyp-{first_number + i}",
                "cell": h.cell,
                "error_type": h.error_type,
                "claim": h.claim,
                "evidence_ids": [],
                "confidence": h.confidence,
                "status": "open",
            }
            for i, h in enumerate(proposed)
        ]
        patch = None
        if diagnosis.patch is not None:
            patch = {"cell": diagnosis.patch.cell, "old_formula": "", "new_formula": diagnosis.patch.new_formula, "source": "agent"}
        return {"hypotheses": hypotheses, "patch": patch}

    return diagnose

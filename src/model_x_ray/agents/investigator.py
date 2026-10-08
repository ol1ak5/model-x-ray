import operator
from collections.abc import Callable
from typing import Annotated, Literal, TypedDict

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AnyMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode
from pydantic import BaseModel

from model_x_ray.causal import render_causal_tree
from model_x_ray.llm import invoke_with_usage, model_name_of
from model_x_ray.prompts import load_prompt
from model_x_ray.spreadsheet.engine import Workbook, normalize_ref
from model_x_ray.state import Evidence, InvestigationState, RunLog

MAX_TOOL_CALLS = 8
MAX_OPEN_HYPOTHESES = 3


class ProposedHypothesis(BaseModel):
    cell: str
    error_type: Literal["typed_value", "wrong_reference", "inconsistent_range", "sign_inconsistency", "period_inconsistency"]
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
    run_log: Annotated[list[RunLog], operator.add]
    diagnosis: Diagnosis | None


def build_investigator(llm: BaseChatModel, tools: list[BaseTool], max_tool_calls: int = MAX_TOOL_CALLS) -> CompiledStateGraph:
    model = llm.bind_tools(tools)
    structured = llm.with_structured_output(Diagnosis, method="function_calling")
    tool_node = ToolNode(tools)
    system = SystemMessage(content=load_prompt("investigator"))
    model_name = model_name_of(llm)

    def think(state: InvestigatorState) -> dict:
        response, records = invoke_with_usage(
            model, [system, *state["messages"]], role="investigator", model=model_name
        )
        return {"messages": [response], "run_log": records}

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
        diagnosis, records = invoke_with_usage(
            structured,
            [system, *messages, HumanMessage(content=load_prompt("investigator_conclude"))],
            role="investigator",
            model=model_name,
        )
        return {"diagnosis": diagnosis, "run_log": records}

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
    open_count = sum(1 for h in state.get("hypotheses", []) if h["status"] == "open")
    lines.append(f"Open hypotheses: {open_count}/{MAX_OPEN_HYPOTHESES}")
    lines += [f"Already rejected, do not propose again: {h['cell']} ({h['error_type']})" for h in state.get("hypotheses", []) if h["status"] == "rejected"]
    return "\n".join(lines)


ANOMALY_MARKERS = ("breaks the pattern", "typed value where the row uses", "reference pattern differs from the row")


def full_ref(ref: str, sheet: str) -> str:
    return normalize_ref(ref) if "!" in ref else normalize_ref(f"{sheet}!{ref}")


def old_formula(book: Workbook, cell: str) -> str:
    raw = book.raw(cell)
    if raw is None:
        return ""
    if isinstance(raw, str) and raw.startswith("="):
        return raw
    return str(raw)


def evidence_cells(name: str, args: dict, content: str, sheet: str) -> list[str]:
    if name == "find_formula_outliers":
        cells = []
        for line in content.splitlines():
            cell = line.split(":", 1)[0].strip()
            if "!" in cell:
                cells.append(normalize_ref(cell))
        return cells
    if name == "find_cells":
        return [full_ref(cell.strip(), sheet) for cell in content.split(",") if cell.strip()]
    ref = args.get("ref")
    return [full_ref(ref, sheet)] if isinstance(ref, str) else []


def collect_evidence(messages: list[BaseMessage], sheet: str, existing: list[Evidence], start: int) -> list[Evidence]:
    calls = {call["id"]: call for message in messages if isinstance(message, AIMessage) for call in message.tool_calls}
    records: list[Evidence] = []
    seen = {(e["cell"], e["text"]) for e in existing}
    for message in messages:
        if not isinstance(message, ToolMessage):
            continue
        call = calls.get(message.tool_call_id)
        if call is None:
            continue
        text = message.content if isinstance(message.content, str) else str(message.content)
        kind = "anomaly" if any(marker in text for marker in ANOMALY_MARKERS) else "expected_pattern"
        for cell in evidence_cells(call["name"], call.get("args", {}), text, sheet):
            if (cell, text) in seen:
                continue
            seen.add((cell, text))
            records.append({"id": f"ev-{start + len(records) + 1}", "cell": cell, "kind": kind, "text": text})
    return records


def make_diagnose_node(investigator: CompiledStateGraph, book: Workbook) -> Callable[[InvestigationState], dict]:
    def diagnose(state: InvestigationState) -> dict:
        result = investigator.invoke({"messages": [HumanMessage(content=investigation_brief(state))]})
        diagnosis = result["diagnosis"]
        sheet = state["target"]["sheet"]
        existing = state.get("evidence", [])
        new_evidence = collect_evidence(result["messages"], sheet, existing, len(existing))
        all_evidence = [*existing, *new_evidence]
        currently_open = sum(1 for h in state.get("hypotheses", []) if h["status"] == "open")
        budget = max(0, MAX_OPEN_HYPOTHESES - currently_open)
        proposed = diagnosis.hypotheses[:budget]
        first_number = len(state.get("hypotheses", [])) + 1
        hypotheses = []
        for i, h in enumerate(proposed):
            cell = full_ref(h.cell, sheet)
            hypotheses.append({
                "id": f"hyp-{first_number + i}",
                "cell": cell,
                "error_type": h.error_type,
                "claim": h.claim,
                "evidence_ids": [e["id"] for e in all_evidence if e["cell"] == cell],
                "confidence": h.confidence,
                "status": "open",
            })
        patch = None
        if diagnosis.patch is not None:
            patch_cell = full_ref(diagnosis.patch.cell, sheet)
            patch = {"cell": patch_cell, "old_formula": old_formula(book, patch_cell), "new_formula": diagnosis.patch.new_formula, "source": "agent"}
        return {"hypotheses": hypotheses, "evidence": new_evidence, "patch": patch, "run_log": result.get("run_log", [])}

    return diagnose

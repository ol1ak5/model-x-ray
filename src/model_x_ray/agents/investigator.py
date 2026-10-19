import operator
import re
from collections import Counter
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
from model_x_ray.rules import breaks_row_pattern
from model_x_ray.spreadsheet.engine import CellAddress, FormulaError, Workbook, make_ref, normalize_ref, split_ref
from model_x_ray.state import Evidence, InvestigationState, RunLog

MAX_TOOL_CALLS = 8
MAX_OPEN_HYPOTHESES = 3


class ProposedHypothesis(BaseModel):
    cell: str
    error_type: Literal["typed_value", "wrong_reference", "range_inconsistency", "sign_inconsistency", "period_inconsistency"]
    claim: str
    confidence: Literal["high", "medium", "low"]


class ProposedPatch(BaseModel):
    cell: str
    new_formula: str


class Diagnosis(BaseModel):
    hypotheses: list[ProposedHypothesis]
    patch: ProposedPatch | None
    choice: int | None = None
    reason: str = ""


class InvestigatorState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    tool_calls_used: int
    run_log: Annotated[list[RunLog], operator.add]
    diagnosis: Diagnosis | None


def build_investigator(llm: BaseChatModel, tools: list[BaseTool], max_tool_calls: int = MAX_TOOL_CALLS) -> CompiledStateGraph:
    model = llm.bind_tools(tools) if tools else llm
    structured = llm.with_structured_output(Diagnosis, method="function_calling")
    tool_node = ToolNode(tools, handle_tool_errors=True)
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


def target_line(target: dict) -> str:
    ref = f"{target['sheet']}!{target['cell']}"
    if target.get("mode") == "review":
        return f"Target: {ref} ({target['label']}) = {target['value']}. This is the model's main result and no rule flagged a cell. Review the logic of the formulas behind it (signs, missing or extra terms, wrong inputs, units) and propose a fix only if one is clearly wrong."
    if target.get("mode") == "table":
        line = f"Target: {ref} ({target['label']}) = {target['value']}. This block is a table, not a time series: compare the cell with the cells around it, not with a prior period. Finding: {target['finding']}."
        if target.get("expected_formula"):
            line += f" The pattern suggests {target['expected_formula']}, which gives {target['prior_value']}."
        return line
    return f"Target: {ref} ({target['label']} {target['period']}) = {target['value']}, prior period {target['prior_cell']} = {target['prior_value']}"


def investigation_brief(state: InvestigationState) -> str:
    target = state["target"]
    lines = [
        f"Question: {state['question']}",
        target_line(target),
    ]
    lines += [f"Marked intentional by a reviewer, do not propose: {o['cell']} ({o['reason']})" for o in state.get("known_overrides", [])]
    lines += [f"Fixed before on this model: {f['cell']} {f['error_type']}, {f['old_formula']} -> {f['new_formula']}" for f in state.get("past_findings", [])]
    model_map = state.get("model_map")
    if model_map:
        lines.append("Model map: " + ", ".join(f"{r['label']} ({r['kind']})" for r in model_map["rows"]))
        lines.append("Periods: " + ", ".join(f"{c['period']} ({c['kind']})" for c in model_map["columns"]))
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


def readable_ref(ref: str, sheet: str) -> bool:
    try:
        full_ref(ref, sheet)
    except FormulaError:
        return False
    return True


def old_formula(book: Workbook, cell: str) -> str:
    raw = book.raw(cell)
    if raw is None:
        return ""
    if isinstance(raw, str) and raw.startswith("="):
        return raw
    return str(raw)


def row_formula_suggestion(book: Workbook, cell: str) -> str | None:
    cell = normalize_ref(cell)
    sheet, address = split_ref(cell)
    by_pattern: dict[str, list[str]] = {}
    for ref in book.cells():
        ref_sheet, ref_address = split_ref(ref)
        if ref_sheet != sheet or ref_address.row != address.row or ref == cell:
            continue
        pattern = book.formula_pattern(ref)
        if pattern is None:
            continue
        by_pattern.setdefault(pattern, []).append(ref)
    if not by_pattern:
        return None
    counts = {pattern: len(refs) for pattern, refs in by_pattern.items()}
    best = max(counts.values())
    winners = [pattern for pattern, count in counts.items() if count == best]
    if len(winners) != 1:
        return None
    return book.shifted_formula(sorted(by_pattern[winners[0]])[0], cell)


def as_formula(content: object) -> object:
    if isinstance(content, str) and not content.startswith("=") and re.search(r"[A-Za-z]{1,3}\$?[0-9]+|[A-Za-z_]+\(", content):
        return "=" + content.lstrip()
    return content


def column_formula_suggestion(book: Workbook, cell: str) -> str | None:
    sheet, address = split_ref(normalize_ref(cell))
    for offset in (1, -1, 2, -2):
        neighbour = make_ref(sheet, CellAddress(address.column, address.row - offset))
        above_or_below = make_ref(sheet, CellAddress(address.column, address.row + offset))
        pattern = book.formula_pattern(neighbour) if book.formula(neighbour) else None
        if pattern is not None and book.formula(above_or_below) and book.formula_pattern(above_or_below) == pattern:
            return book.shifted_formula(neighbour, cell)
    return None


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


def sheet_as_text(book: Workbook) -> str:
    lines: list[str] = []
    for sheet in book.sheets:
        lines.append(f"Sheet {sheet}:")
        for ref in book.cells():
            if not ref.startswith(f"{sheet}!"):
                continue
            label = book.row_label(ref)
            header = book.column_header(ref)
            formula = book.formula(ref)
            value = book.value(ref)
            if label is None and header is None and formula is None:
                continue
            parts = [ref]
            if label is not None:
                parts.append(label)
            if header is not None:
                parts.append(header)
            parts.append(f"value {value}")
            if formula is not None:
                parts.append(f"formula {formula}")
            lines.append("  " + ", ".join(parts))
    return "\n".join(lines)


MAX_CANDIDATES = 6


def tested_candidates(book: Workbook, state: InvestigationState) -> list[dict]:
    target = state["target"]
    tried = {h["cell"] for h in state.get("hypotheses", []) if h["status"] != "open"}
    intentional = {o["cell"] for o in state.get("known_overrides", [])}
    own = [{"cell": f"{target['sheet']}!{target['cell']}", "reason": target["finding"], "fix": target.get("expected_formula")}] if target.get("mode") == "table" else []
    candidates: list[dict] = []
    for finding in [*own, *target.get("other_findings", [])]:
        cell, fix = finding["cell"], finding.get("fix")
        if not fix or cell in tried or cell in intentional or any(c["cell"] == cell for c in candidates):
            continue
        try:
            before, after = book.value(cell), book.with_patch(cell, fix).value(cell)
        except (FormulaError, RecursionError):
            continue
        candidates.append({"number": len(candidates) + 1, "cell": cell, "reason": finding["reason"], "fix": fix, "before": before, "after": after})
        if len(candidates) == MAX_CANDIDATES:
            break
    return candidates


def candidates_brief(candidates: list[dict]) -> str:
    if not candidates:
        return ""
    lines = ["Engine-tested candidate fixes (each was applied to a copy and recalculated). Choose the one that fixes a genuine error by its number, or none if every difference is intentional:"]
    lines += [f"  {c['number']}. {c['cell']}: {c['reason']} -> {c['fix']} (value {c['before']} -> {c['after']})" for c in candidates]
    return "\n".join(lines)


def make_diagnose_node(investigator: CompiledStateGraph, book: Workbook, plain_text: bool = False) -> Callable[[InvestigationState], dict]:
    def diagnose(state: InvestigationState) -> dict:
        candidates = tested_candidates(book, state)
        brief = "\n".join(part for part in (investigation_brief(state), candidates_brief(candidates)) if part)
        if plain_text:
            brief = f"{brief}\n\nThe whole model, read as text:\n{sheet_as_text(book)}"
        result = investigator.invoke({"messages": [HumanMessage(content=brief)]})
        diagnosis = result["diagnosis"]
        sheet = state["target"]["sheet"]
        existing = state.get("evidence", [])
        new_evidence = collect_evidence(result["messages"], sheet, existing, len(existing))
        all_evidence = [*existing, *new_evidence]
        currently_open = sum(1 for h in state.get("hypotheses", []) if h["status"] == "open")
        budget = max(0, MAX_OPEN_HYPOTHESES - currently_open)
        intentional = {o["cell"] for o in state.get("known_overrides", [])}
        proposed = [h for h in diagnosis.hypotheses if readable_ref(h.cell, sheet) and full_ref(h.cell, sheet) not in intentional][:budget]
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
        rule = candidates[0] if candidates else None
        decision = {"cell": None, "decided_by": "none", "fix": None, "model_fix": None, "rule_would_have": f"{rule['cell']} {rule['fix']}" if rule else None, "reason": diagnosis.reason, "candidates": len(candidates)}
        chosen = next((c for c in candidates if c["number"] == diagnosis.choice), None)
        if chosen is not None:
            patch = {"cell": chosen["cell"], "old_formula": old_formula(book, chosen["cell"]), "new_formula": chosen["fix"], "source": "agent"}
            decision |= {"cell": chosen["cell"], "decided_by": "model", "fix": chosen["fix"]}
            if chosen["cell"] not in {h["cell"] for h in [*state.get("hypotheses", []), *hypotheses]}:
                hypotheses.append({
                    "id": f"hyp-{first_number + len(hypotheses)}", "cell": chosen["cell"], "error_type": "wrong_reference", "claim": chosen["reason"],
                    "evidence_ids": [e["id"] for e in all_evidence if e["cell"] == chosen["cell"]], "confidence": "high", "status": "open",
                })
        elif diagnosis.patch is not None and readable_ref(diagnosis.patch.cell, sheet) and full_ref(diagnosis.patch.cell, sheet) not in intentional:
            patch_cell = full_ref(diagnosis.patch.cell, sheet)
            model_formula = as_formula(diagnosis.patch.new_formula)
            new_formula = model_formula
            if book.formula(patch_cell) is None or breaks_row_pattern(book, patch_cell):
                new_formula = row_formula_suggestion(book, patch_cell) or column_formula_suggestion(book, patch_cell) or new_formula
            patch = {"cell": patch_cell, "old_formula": old_formula(book, patch_cell), "new_formula": new_formula, "source": "agent"}
            decision |= {"cell": patch_cell, "decided_by": "model_own" if new_formula == model_formula else "rule_corrected", "fix": new_formula, "model_fix": str(model_formula)}
        target = state["target"]
        if patch is None and (target.get("mode") == "table" or target.get("other_findings")):
            tried = {h["cell"] for h in state.get("hypotheses", []) if h["status"] != "open"}
            own = [{"cell": f"{target['sheet']}!{target['cell']}", "reason": target["finding"], "fix": target.get("expected_formula")}] if target.get("mode") == "table" else []
            findings = [*own, *target.get("other_findings", [])]
            untried = [f for f in findings if f.get("fix") and f["cell"] not in tried and f["cell"] not in intentional]
            if untried:
                proposed_cells = {h["cell"] for h in hypotheses}
                open_cells = {h["cell"] for h in state.get("hypotheses", []) if h["status"] == "open"}
                for finding in untried[:budget]:
                    if finding["cell"] in proposed_cells or finding["cell"] in open_cells:
                        continue
                    hypotheses.append({
                        "id": f"hyp-{first_number + len(hypotheses)}", "cell": finding["cell"], "error_type": "wrong_reference",
                        "claim": finding["reason"], "evidence_ids": [e["id"] for e in all_evidence if e["cell"] == finding["cell"]], "confidence": "medium", "status": "open",
                    })
                first = untried[0]
                patch = {"cell": first["cell"], "old_formula": old_formula(book, first["cell"]), "new_formula": first["fix"], "source": "agent"}
                decision |= {"cell": first["cell"], "decided_by": "rule", "fix": first["fix"]}
        return {"hypotheses": hypotheses, "evidence": new_evidence, "patch": patch, "decisions": [decision], "run_log": result.get("run_log", []), "tool_call_counts": [result.get("tool_calls_used", 0)]}

    return diagnose

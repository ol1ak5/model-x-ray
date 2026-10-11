import re

from model_x_ray.spreadsheet.engine import FormulaError, Workbook
from model_x_ray.state import InvestigationState

CITATIONS = re.compile(r"evidence:\s*([^\)]+)\)")
RANK = {"confirmed": 0, "open": 1, "rejected": 2}


def same_cell(left: str, right: str) -> bool:
    if left == right:
        return True
    return left.endswith(f"!{right}") or right.endswith(f"!{left}")


def rank_hypotheses(state: InvestigationState) -> list[dict]:
    hypotheses = state.get("hypotheses", [])
    return sorted(hypotheses, key=lambda h: RANK.get(h.get("status", "open"), 1))


def diagnose_metrics(state: InvestigationState, question: dict, planted: list[dict]) -> dict:
    expected = question.get("expected_error_cells", [])
    ranked = rank_hypotheses(state)
    top1 = bool(ranked) and any(same_cell(ranked[0]["cell"], ref) for ref in expected)
    top3 = any(same_cell(h["cell"], ref) for h in ranked[:3] for ref in expected)
    planted_type = next((p["error_type"] for p in planted if any(same_cell(p["cell"], ref) for ref in expected)), None)
    predicted_type = ranked[0]["error_type"] if ranked else None
    error_type_correct = bool(top1) and predicted_type == planted_type
    false_alarm = question.get("expected_verdict") == "no_error" and bool(ranked)
    return {
        "top1": bool(top1),
        "top3": bool(top3),
        "error_type_correct": bool(error_type_correct),
        "false_alarm": bool(false_alarm),
        "revisions": max(0, len(state.get("hypotheses", [])) - 1),
        "confusion": f"{predicted_type}|{planted_type}" if predicted_type and planted_type else None,
    }


def explain_metrics(state: InvestigationState) -> dict:
    report = state.get("report") or ""
    known = {e["id"] for e in state.get("evidence", [])}
    match = CITATIONS.search(report)
    citations = [c.strip() for c in match.group(1).split(",")] if match else []
    return {"citations": len(citations), "citations_valid": all(c in known for c in citations)}


def locate_metrics(state: InvestigationState, question: dict, asked: bool) -> dict:
    target = state.get("target")
    exact = bool(target) and same_cell(f"{target['sheet']}!{target['cell']}", question["target"])
    return {"exact": bool(exact), "exact_unassisted": bool(exact) and not asked}


def tree_cells(node: dict) -> set[str]:
    cells = {node["cell"]}
    for child in node.get("children", []):
        cells |= tree_cells(child)
    return cells


def trace_recall(state: InvestigationState, question: dict) -> float | None:
    expected = question.get("expected_error_cells", [])
    if not expected:
        return None
    seen = {c["cell"] for c in state.get("contributions", [])}
    tree = state.get("causal_tree")
    if tree:
        seen |= tree_cells(tree)
    return sum(1 for ref in expected if ref in seen) / len(expected)


def verdict_metrics(events: list[tuple[str, bool]]) -> dict:
    confirmed = [(verdict, correct) for verdict, correct in events if verdict == "confirmed"]
    precision = sum(1 for _, correct in confirmed if correct) / len(confirmed) if confirmed else None
    positives = [correct for _, correct in events]
    recall = (
        sum(1 for verdict, correct in events if verdict == "confirmed" and correct) / sum(positives)
        if any(positives)
        else None
    )
    return {"verdict_precision": precision, "verdict_recall": recall}


def graph_edges(book: Workbook) -> set[tuple[str, str]]:
    edges: set[tuple[str, str]] = set()
    for ref in book.cells():
        if book.formula(ref) is None:
            continue
        try:
            edges.update((ref, precedent) for precedent in book.precedents(ref))
        except FormulaError:
            continue
    return edges


def load_sheet_metrics(book: Workbook, base: Workbook | None = None) -> dict:
    formulas = [ref for ref in book.cells() if book.formula(ref) is not None]
    parsed = 0
    for ref in formulas:
        try:
            book.value(ref)
            parsed += 1
        except FormulaError:
            continue
    result = {
        "parse_share": parsed / len(formulas) if formulas else None,
        "edge_precision": None,
        "edge_recall": None,
    }
    if base is None:
        return result
    variant_edges = graph_edges(book)
    base_edges = graph_edges(base)
    shared = len(variant_edges & base_edges)
    result["edge_precision"] = shared / len(variant_edges) if variant_edges else None
    result["edge_recall"] = shared / len(base_edges) if base_edges else None
    return result


def calibration(state: InvestigationState) -> dict[str, float]:
    outcomes: dict[str, list[bool]] = {}
    for hypothesis in state.get("hypotheses", []):
        outcomes.setdefault(hypothesis.get("confidence", "medium"), []).append(hypothesis.get("status") == "confirmed")
    return {confidence: sum(flags) / len(flags) for confidence, flags in sorted(outcomes.items())}

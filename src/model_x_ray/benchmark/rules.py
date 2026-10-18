from collections.abc import Callable
from collections import deque

from model_x_ray.rules import find_formula_outliers
from model_x_ray.spreadsheet.engine import Workbook, column_letters, normalize_ref, split_ref
from model_x_ray.state import InvestigationState

TOP_N = 3


def precedent_depths(book: Workbook, start: str) -> dict[str, int]:
    depths = {normalize_ref(start): 0}
    queue = deque([normalize_ref(start)])
    while queue:
        current = queue.popleft()
        for precedent in book.precedents(current):
            ref = normalize_ref(precedent)
            if ref not in depths:
                depths[ref] = depths[current] + 1
                queue.append(ref)
    return depths


def sheet_extent(book: Workbook, sheet: str) -> str | None:
    rows, columns = [], []
    for ref in book.cells():
        if not ref.startswith(f"{sheet}!"):
            continue
        _, address = split_ref(ref)
        rows.append(address.row)
        columns.append(address.column)
    if not rows:
        return None
    return f"{sheet}!A1:{column_letters(max(columns))}{max(rows)}"


def stale_copy(book: Workbook, ref: str) -> bool:
    _, address = split_ref(ref)
    if address.column <= 1:
        return False
    prior = f"{split_ref(ref)[0]}!{column_letters(address.column - 1)}{address.row}"
    value, prior_value = book.value(ref), book.value(prior)
    return (
        isinstance(value, (int, float))
        and isinstance(prior_value, (int, float))
        and abs(value - prior_value) <= 1e-6 * max(1.0, abs(prior_value))
    )


def kind_rank(book: Workbook, ref: str, reason: str) -> int:
    if "differs" in reason:
        return 2
    return 0 if stale_copy(book, ref) else 1


def make_rules_diagnose_node(book: Workbook) -> Callable[[InvestigationState], dict]:
    def rules_diagnose(state: InvestigationState) -> dict:
        target = state.get("target")
        if target is None:
            return {}
        if target.get("mode") == "table":
            ref = f"{target['sheet']}!{target['cell']}"
            if ref in {h["cell"] for h in state.get("hypotheses", [])}:
                return {}
            hypothesis = {"id": f"hyp-{len(state.get('hypotheses', [])) + 1}", "cell": ref, "error_type": "wrong_reference", "claim": target["finding"], "evidence_ids": [], "confidence": "medium", "status": "open"}
            patch = {"cell": ref, "old_formula": book.formula(ref) or str(book.raw(ref)), "new_formula": target["expected_formula"], "source": "agent"} if target.get("expected_formula") else None
            return {"hypotheses": [hypothesis], "patch": patch}
        depths = precedent_depths(book, f"{target['sheet']}!{target['cell']}")
        candidates: list[tuple[int, int, int, int, str, str]] = []
        for sheet in book.sheets:
            extent = sheet_extent(book, sheet)
            if extent is None:
                continue
            for outlier in find_formula_outliers(book, extent):
                ref = normalize_ref(outlier["cell"])
                if ref not in depths:
                    continue
                _, address = split_ref(ref)
                rank = kind_rank(book, ref, outlier["reason"])
                candidates.append((rank, depths[ref], address.row, address.column, ref, outlier["reason"]))
        candidates.sort()
        known = {h["cell"] for h in state.get("hypotheses", [])}
        hypotheses = []
        for rank, depth, row, column, ref, reason in candidates:
            if ref in known:
                continue
            error_type = "wrong_reference" if "differs" in reason else "typed_value"
            hypotheses.append({
                "id": f"hyp-{len(state.get('hypotheses', [])) + len(hypotheses) + 1}",
                "cell": ref,
                "error_type": error_type,
                "claim": reason,
                "evidence_ids": [],
                "confidence": "medium",
                "status": "open",
            })
            if len(hypotheses) == TOP_N:
                break
        return {"hypotheses": hypotheses}

    return rules_diagnose

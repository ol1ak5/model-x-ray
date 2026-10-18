import json
from typing import Literal

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import Runnable
from pydantic import BaseModel, Field

from model_x_ray.llm import invoke_with_usage
from model_x_ray.rules import scan_tables
from model_x_ray.prompts import load_prompt
from model_x_ray.spreadsheet.engine import CellAddress, FormulaError, Workbook, is_number, make_ref, normalize_ref, split_ref
from model_x_ray.state import InvestigationState, Patch, RunLog, Verification


class Objection(BaseModel):
    kind: Literal["formula", "value", "note"] = Field(
        description="formula: the cell does not equal its formula after the fix; value: the cell's value after the fix is wrong or implausible; note: a cell note shows the original content was intentional"
    )
    cell: str = Field(description="The cell the claim is about, for example P&L!H8")
    stated_value: float | None = Field(default=None, description="The number you read for this cell after the fix, for formula and value claims")
    explanation: str


class Verdict(BaseModel):
    verdict: Literal["confirmed", "rejected"]
    reason: str
    objections: list[Objection] = Field(default_factory=list, description="Required when rejecting: every claim behind the rejection, so the engine can check it")


def _close(left: float, right: float) -> bool:
    return abs(left - right) <= max(0.01, 1e-3 * abs(right))


def _value_or_none(book: Workbook, ref: str) -> float | None:
    try:
        value = book.value(ref)
    except FormulaError:
        return None
    return float(value) if is_number(value) else None


def check_objection(book: Workbook, patch: Patch, after: dict[str, object], objection: Objection) -> tuple[bool, str]:
    sheet = patch["cell"].rsplit("!", 1)[0]
    cell = normalize_ref(objection.cell if "!" in objection.cell else f"{sheet}!{objection.cell}")
    patched = book.with_patch(patch["cell"], patch["new_formula"])
    if objection.kind == "note":
        note = book.note(cell)
        return (True, f"{cell} has the note '{note}'") if note else (False, f"{cell} has no note")
    recalculated = _value_or_none(patched, cell)
    if recalculated is None:
        return False, f"{cell} has no number after the fix"
    if objection.kind == "formula":
        sandbox = after.get(cell)
        disagrees = is_number(sandbox) and not _close(float(sandbox), recalculated)
        formula = patched.formula(cell) or "a typed value"
        if disagrees:
            return True, f"the copy shows {cell} = {float(sandbox):.2f} but its formula {formula} gives {recalculated:.2f}"
        return False, f"the recalculated copy gives {cell} = {recalculated:.2f}, which matches its formula {formula}"
    if objection.stated_value is not None and _close(objection.stated_value, recalculated):
        return True, f"{cell} is {recalculated:.2f} after the fix, as stated"
    stated = "no number" if objection.stated_value is None else f"{objection.stated_value:.2f}"
    return False, f"the second model read {cell} as {stated}, but the recalculated copy gives {recalculated:.2f}"


def settle_verdict(verdict: Verdict, book: Workbook, patch: Patch, after: dict[str, object]) -> tuple[str, str, bool | None]:
    if verdict.verdict == "confirmed":
        return "confirmed", verdict.reason, None
    results = [check_objection(book, patch, after, objection) for objection in verdict.objections]
    upheld = [finding for holds, finding in results if holds]
    if upheld:
        return "rejected", f"{verdict.reason.rstrip('.')}. Checked by the engine: {'; '.join(upheld)}.", True
    if not results:
        return "confirmed", "The second model rejected the fix without a claim the engine could check, and every code check passed, so the fix stands.", False
    findings = "; ".join(finding for _, finding in results)
    return "confirmed", f"The second model objected, but the engine disproved each claim: {findings}. Every code check passed, so the fix stands.", False


def build_verifier(llm: BaseChatModel) -> Runnable:
    return llm.with_structured_output(Verdict, method="function_calling")


def _matches(expected: object, actual: object) -> bool:
    if actual is None:
        return False
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        return abs(actual - expected) <= 1e-6 * max(1.0, abs(expected))
    return actual == expected


def _dependent_matches(patched: Workbook, dependent: str, after: dict[str, object]) -> bool:
    try:
        return _matches(patched.value(dependent), after.get(dependent))
    except Exception:
        return False


def _pattern_restored(book: Workbook, patch: Patch, patched: Workbook) -> bool:
    pattern = patched.formula_pattern(patch["cell"])
    if pattern is None:
        return False
    sheet, address = split_ref(patch["cell"])
    neighbours = [
        make_ref(sheet, CellAddress(address.column + offset, address.row))
        for offset in (-2, -1, 1, 2)
        if address.column + offset >= 1
    ]
    formula_neighbours = [n for n in neighbours if book.formula(n) is not None]
    if not formula_neighbours:
        return True
    return any(patched.formula_pattern(n) == pattern for n in formula_neighbours)


def _column_pattern_restored(book: Workbook, patch: Patch, patched: Workbook) -> bool:
    pattern = patched.formula_pattern(patch["cell"])
    sheet, address = split_ref(patch["cell"])
    neighbours = [make_ref(sheet, CellAddress(address.column, address.row + offset)) for offset in (-2, -1, 1, 2) if address.row + offset >= 1]
    formula_neighbours = [n for n in neighbours if book.formula(n) is not None]
    return pattern is not None and (not formula_neighbours or any(patched.formula_pattern(n) == pattern for n in formula_neighbours) or pattern.upper().startswith("=SUM("))


def deterministic_checks(book: Workbook, state: InvestigationState, verification: Verification) -> dict[str, bool]:
    patch = state["patch"]
    before = verification.get("before", {})
    after = verification.get("after", {})
    target = state.get("target")
    target_ref = f"{target['sheet']}!{target['cell']}" if target else None
    prior = target["prior_value"] if target else None
    target_before = before.get(target_ref) if target_ref else None
    target_after = after.get(target_ref) if target_ref else None
    if target and target.get("mode") == "review":
        patched_book = book.with_patch(patch["cell"], patch["new_formula"])
        return {
            "anomaly_resolved": not _matches(target_before, target_after),
            "dependents_consistent": all(_dependent_matches(patched_book, dependent, after) for dependent in book.all_dependents(patch["cell"])),
            "pattern_restored": True,
        }
    if target and target.get("mode") == "table":
        patched_book = book.with_patch(patch["cell"], patch["new_formula"])
        still_flagged = {f["cell"] for f in scan_tables(patched_book)}
        return {
            "anomaly_resolved": f"{target['sheet']}!{target['cell']}" not in still_flagged and patch["cell"] not in still_flagged,
            "dependents_consistent": all(_dependent_matches(patched_book, dependent, after) for dependent in book.all_dependents(patch["cell"])),
            "pattern_restored": _pattern_restored(book, patch, patched_book) or _column_pattern_restored(book, patch, patched_book),
        }
    anomaly_resolved = (
        isinstance(target_before, (int, float))
        and isinstance(target_after, (int, float))
        and isinstance(prior, (int, float))
        and not _matches(target_before, target_after)
        and abs(target_after - prior) < abs(target_before - prior)
    )
    patched = book.with_patch(patch["cell"], patch["new_formula"])
    dependents_consistent = all(
        _dependent_matches(patched, dependent, after)
        for dependent in book.all_dependents(patch["cell"])
    )
    return {
        "anomaly_resolved": bool(anomaly_resolved),
        "dependents_consistent": dependents_consistent,
        "pattern_restored": _pattern_restored(book, patch, patched),
    }


def _relevant_refs(book: Workbook, patch: Patch) -> list[str]:
    sheet, address = split_ref(patch["cell"])
    neighbours = [
        make_ref(sheet, CellAddress(address.column + offset, address.row))
        for offset in (-2, -1, 1, 2)
        if address.column + offset >= 1 and book.raw(make_ref(sheet, CellAddress(address.column + offset, address.row))) is not None
    ]
    return list(dict.fromkeys([patch["cell"], *neighbours, *book.all_dependents(patch["cell"])]))


def evidence_package(
    state: InvestigationState,
    verification: Verification,
    checks: dict[str, bool],
    book: Workbook,
) -> dict:
    patch = state["patch"]
    target = state.get("target")
    target_ref = f"{target['sheet']}!{target['cell']}" if target else None
    before = verification.get("before", {})
    after = verification.get("after", {})
    return {
        "question": state["question"],
        "target": {
            "ref": target_ref,
            "prior_value": target["prior_value"] if target else None,
            "before": before.get(target_ref) if target_ref else None,
            "after": after.get(target_ref) if target_ref else None,
        },
        "patch": dict(patch),
        "formulas": {ref: book.raw(ref) for ref in _relevant_refs(book, patch)},
        "sandbox": {"before": dict(before), "after": dict(after)},
        "deterministic_checks": dict(checks),
    }


def invoke_verifier(
    verifier: Runnable,
    state: InvestigationState,
    verification: Verification,
    checks: dict[str, bool],
    book: Workbook,
    model: str | None = None,
) -> tuple[Verdict, list[RunLog]]:
    package = evidence_package(state, verification, checks, book)
    verdict, records = invoke_with_usage(
        verifier,
        [
            SystemMessage(content=load_prompt("verifier")),
            HumanMessage(content=json.dumps(package, default=str)),
        ],
        role="verifier",
        model=model,
    )
    return verdict, records

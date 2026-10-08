import json
from typing import Literal

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import Runnable
from pydantic import BaseModel

from model_x_ray.llm import invoke_with_usage
from model_x_ray.prompts import load_prompt
from model_x_ray.spreadsheet.engine import CellAddress, Workbook, make_ref, split_ref
from model_x_ray.state import InvestigationState, Patch, RunLog, Verification


class Verdict(BaseModel):
    verdict: Literal["confirmed", "rejected"]
    reason: str


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
    ]
    formula_neighbours = [n for n in neighbours if book.formula(n) is not None]
    if not formula_neighbours:
        return True
    return any(patched.formula_pattern(n) == pattern for n in formula_neighbours)


def deterministic_checks(book: Workbook, state: InvestigationState, verification: Verification) -> dict[str, bool]:
    patch = state["patch"]
    before = verification.get("before", {})
    after = verification.get("after", {})
    target = state.get("target")
    target_ref = f"{target['sheet']}!{target['cell']}" if target else None
    prior = target["prior_value"] if target else None
    target_before = before.get(target_ref) if target_ref else None
    target_after = after.get(target_ref) if target_ref else None
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
        if book.raw(make_ref(sheet, CellAddress(address.column + offset, address.row))) is not None
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

import re
from collections.abc import Callable

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel

from model_x_ray.llm import invoke_with_usage, model_name_of
from model_x_ray.prompts import load_prompt
from model_x_ray.rules import is_period_cell, rank_outliers, row_fix, scan_model, scan_tables
from model_x_ray.spreadsheet.engine import CellAddress, FormulaError, Workbook, make_ref, normalize_ref, split_ref
from model_x_ray.state import InvestigationState, ModelMap, TargetCell
from model_x_ray.tools import find_cells

YEAR = re.compile(r"\b(?:19|20)\d{2}[A-Za-z]?\b")


class LocateRequest(BaseModel):
    label: str
    period: str
    sheet: str | None = None


class Catalogue(BaseModel):
    sheets: list[str]
    labels: list[str]
    periods: list[str]


def workbook_catalogue(book: Workbook) -> Catalogue:
    labels: list[str] = []
    periods: list[str] = []
    for ref in book.cells():
        label = book.row_label(ref)
        period = book.column_header(ref)
        if label is None or period is None:
            continue
        if label not in labels:
            labels.append(label)
        if period not in periods:
            periods.append(period)
    return Catalogue(sheets=book.sheets, labels=labels, periods=periods)


def read_question(question: str, catalogue: Catalogue) -> LocateRequest | None:
    text = question.lower()
    labels = [label for label in catalogue.labels if all(part.lower() in text for part in label.split(" – "))]
    labels = [label for label in labels if not any(label != other and label.lower() in other.lower() for other in labels)]
    years = YEAR.findall(question)
    periods = [period for period in catalogue.periods if any(year in period for year in years)]
    sheets = [sheet for sheet in catalogue.sheets if sheet.lower() in text]
    if len(labels) != 1 or len(periods) != 1:
        return None
    return LocateRequest(label=labels[0], period=periods[0], sheet=sheets[0] if len(sheets) == 1 else None)


def locate_brief(question: str, catalogue: Catalogue, model_map: ModelMap | None = None) -> str:
    lines = [
        f"Question: {question}",
        f"Sheets: {', '.join(catalogue.sheets)}",
        f"Lines: {', '.join(catalogue.labels)}",
        f"Periods: {', '.join(catalogue.periods)}",
    ]
    if model_map:
        for kind in ("actual", "forecast"):
            periods = [c["period"] for c in model_map["columns"] if c["kind"] == kind]
            lines.append(f"{kind.capitalize()} periods: {', '.join(periods) or 'none'}")
    return "\n".join(lines)


def prior_cell(book: Workbook, ref: str) -> str | None:
    sheet, address = split_ref(ref)
    for column in range(address.column - 1, 0, -1):
        candidate = make_ref(sheet, CellAddress(column, address.row))
        if is_period_cell(book, candidate):
            return candidate
    return None


def as_number(value: object) -> float:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else 0.0


def target_cell(book: Workbook, ref: str) -> TargetCell:
    ref = normalize_ref(ref)
    sheet, cell = ref.rsplit("!", 1)
    prior = prior_cell(book, ref)
    return {
        "sheet": sheet,
        "cell": cell,
        "label": book.row_label(ref) or "",
        "period": book.column_header(ref) or "",
        "value": as_number(book.value(ref)),
        "prior_cell": prior.rsplit("!", 1)[1] if prior else "",
        "prior_value": as_number(book.value(prior)) if prior else 0.0,
    }


def is_target(book: Workbook, ref: str) -> bool:
    return is_period_cell(book, ref) and prior_cell(book, ref) is not None


def relative_move(book: Workbook, ref: str) -> float:
    prior = prior_cell(book, ref)
    now, before = as_number(book.value(ref)), as_number(book.value(prior)) if prior else 0.0
    return abs(now - before) / abs(before) if before else abs(now - before)


def check_target(book: Workbook) -> tuple[str, str]:
    outliers = rank_outliers(book, scan_model(book))
    for outlier in outliers:
        for ref in [*book.all_dependents(outlier["cell"]), outlier["cell"]]:
            if is_target(book, ref):
                finding = f"which is a {outlier['reason']}" if outlier["reason"].startswith("typed value") else f"whose {outlier['reason']}"
                return ref, f"Check the model: {book.row_label(ref)} {book.column_header(ref)} depends on {outlier['cell']}, {finding}."
    candidates = [ref for ref in book.cells() if is_target(book, ref) and "/" not in (book.formula(ref) or "/")]
    if not candidates:
        raise ValueError("Model X-Ray found no calculated line with periods to check in this model")
    main = max(candidates, key=lambda ref: len(book.all_precedents(ref)))
    label = book.row_label(main)
    row = [ref for ref in candidates if book.row_label(ref) == label and ref.rsplit("!", 1)[0] == main.rsplit("!", 1)[0]]
    ref = max(row, key=lambda cell: relative_move(book, cell))
    return ref, f"Check the model: no cell breaks its row's pattern; {label} {book.column_header(ref)} is the model's main output in its largest move."


def pick_target(book: Workbook, candidates: list[str]) -> tuple[str, str]:
    usable = [ref for ref in candidates if is_target(book, ref)] or candidates
    links = {ref for ref in usable if any(other in book.all_precedents(ref) for other in usable if other != ref)}
    sources = [ref for ref in usable if ref not in links] or usable
    order = {sheet: index for index, sheet in enumerate(book.sheets)}
    chosen = max(sources, key=lambda ref: (len(book.all_precedents(ref)), -order.get(ref.rsplit("!", 1)[0], 0), -split_ref(ref)[1].row))
    reason = "the source the other cells link to" if links else "the one with the most inputs"
    return chosen, f"{len(candidates)} cells match ({', '.join(candidates)}); I investigated {chosen}, {reason}."


def make_locate_node(llm: BaseChatModel | None, book: Workbook) -> Callable[[InvestigationState], dict]:
    catalogue = workbook_catalogue(book)
    structured = llm.with_structured_output(LocateRequest, method="function_calling") if llm is not None else None
    system = SystemMessage(content=load_prompt("locate"))

    def locate(state: InvestigationState) -> dict:
        if not state.get("question", "").strip():
            outliers = scan_model(book)
            if outliers:
                try:
                    ref, question = check_target(book)
                    target = target_cell(book, ref)
                    ranked = rank_outliers(book, outliers)
                    target["other_findings"] = [{"cell": o["cell"], "reason": o["reason"], "fix": row_fix(book, o["cell"])} for o in ranked[:6]]
                    return {"target": target, "question": question, "target_choice": None}
                except ValueError:
                    pass
            table = table_check(book)
            if table is not None:
                target, question = table
                return {"target": target, "question": question, "target_choice": None}
            try:
                ref, question = check_target(book)
                return {"target": target_cell(book, ref), "question": question, "target_choice": None}
            except ValueError:
                review = review_target(book)
                if review is None:
                    raise
                target, question = review
                return {"target": target, "question": question, "target_choice": None}
        request = read_question(state["question"], catalogue)
        records = []
        if request is None and structured is not None:
            messages = [system, HumanMessage(content=locate_brief(state["question"], catalogue, state.get("model_map")))]
            request, records = invoke_with_usage(structured, messages, role="locate", model=model_name_of(llm))
        if request is None:
            labels = [label for label in catalogue.labels if label.lower() in state["question"].lower()]
            rows = [ref for label in labels for ref in find_cells(book, label, "") if is_target(book, ref)]
            if not rows:
                return checked_instead(book, records, "I could not tell which line the question is about")
            chosen = max(rows, key=lambda ref: relative_move(book, ref))
            choice = {"candidates": rows, "chosen": chosen, "why": f"The question names no period; I investigated {chosen}, the largest move on that line."}
            return {"target": target_cell(book, chosen), "target_choice": choice, "run_log": records}
        candidates = find_cells(book, request.label, request.period) if request.label in catalogue.labels else []
        if request.sheet:
            candidates = [ref for ref in candidates if ref.startswith(f"{request.sheet}!")] or candidates
        if not candidates:
            return checked_instead(book, records, f"I could not find {request.label} {request.period} in this model")
        if len(candidates) == 1:
            return {"target": target_cell(book, candidates[0]), "target_choice": None, "run_log": records}
        chosen, why = pick_target(book, candidates)
        return {"target": target_cell(book, chosen), "target_choice": {"candidates": candidates, "chosen": chosen, "why": why}, "run_log": records}

    return locate


def table_check(book: Workbook) -> tuple[TargetCell, str] | None:
    findings = scan_tables(book)
    if not findings:
        return None
    ranked = sorted(findings, key=lambda f: (len(book.all_dependents(f["cell"])), f["kind"] == "incomplete_total"), reverse=True)
    finding = ranked[0]
    ref = finding["cell"]
    sheet, address = split_ref(ref)
    value = as_number(book.value(ref))
    expected = value
    if finding.get("fix"):
        try:
            expected = as_number(book.with_patch(ref, finding["fix"]).value(ref))
        except FormulaError:
            expected = value
    label = book.row_label(ref) or book.column_header(ref) or ref
    period = book.column_header(ref) if book.row_label(ref) else ""
    target: TargetCell = {
        "sheet": sheet, "cell": ref.rsplit("!", 1)[1], "label": label, "period": period or "", "value": value,
        "prior_cell": "", "prior_value": expected, "mode": "table", "finding": finding["reason"], "expected_formula": finding.get("fix"),
        "other_findings": [{"cell": f["cell"], "reason": f["reason"], "fix": f.get("fix")} for f in ranked[1:6]],
    }
    return target, f"Check the model: {label} ({ref}) looks wrong: {finding['reason']}."


def review_target(book: Workbook) -> tuple[TargetCell, str] | None:
    outputs = [ref for ref in book.cells() if book.formula(ref) is not None and (book.row_label(ref) or book.column_header(ref))]
    if not outputs:
        return None
    ref = max(outputs, key=lambda cell: (len(book.all_precedents(cell)), -split_ref(cell)[1].row))
    try:
        value = as_number(book.value(ref))
    except FormulaError:
        return None
    label = book.row_label(ref) or book.column_header(ref) or ref
    finding = "no cell breaks a pattern here, so the calculation logic behind this output needs a review"
    target: TargetCell = {
        "sheet": split_ref(ref)[0], "cell": ref.rsplit("!", 1)[1], "label": label, "period": "", "value": value,
        "prior_cell": "", "prior_value": value, "mode": "review", "finding": finding, "expected_formula": None,
    }
    return target, f"Check the model: {label} ({ref}) is the main result; {finding}."


def checked_instead(book: Workbook, records: list, missing: str) -> dict:
    ref, question = check_target(book)
    why = f"{missing}, so I checked the whole model instead. {question}"
    return {"target": target_cell(book, ref), "target_choice": {"candidates": [], "chosen": ref, "why": why}, "run_log": records}

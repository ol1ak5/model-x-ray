import re
from collections.abc import Callable

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.types import interrupt
from pydantic import BaseModel

from model_x_ray.llm import invoke_with_usage, model_name_of
from model_x_ray.prompts import load_prompt
from model_x_ray.spreadsheet.engine import CellAddress, Workbook, make_ref, normalize_ref, split_ref
from model_x_ray.state import InvestigationState, ModelMap, TargetCell
from model_x_ray.tools import find_cells

YEAR = re.compile(r"\b(?:19|20)\d{2}\b")


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
    labels = [label for label in catalogue.labels if label.lower() in text]
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
        if book.column_header(candidate) is not None and book.raw(candidate) is not None:
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


def make_locate_node(llm: BaseChatModel, book: Workbook) -> Callable[[InvestigationState], dict]:
    catalogue = workbook_catalogue(book)
    structured = llm.with_structured_output(LocateRequest, method="function_calling")
    system = SystemMessage(content=load_prompt("locate"))

    def locate(state: InvestigationState) -> dict:
        request = read_question(state["question"], catalogue)
        records = []
        if request is None:
            messages = [system, HumanMessage(content=locate_brief(state["question"], catalogue, state.get("model_map")))]
            request, records = invoke_with_usage(structured, messages, role="locate", model=model_name_of(llm))
        candidates = find_cells(book, request.label, request.period) if request.label in catalogue.labels else []
        if request.sheet:
            candidates = [ref for ref in candidates if ref.startswith(f"{request.sheet}!")] or candidates
        if len(candidates) == 1:
            return {"target": target_cell(book, candidates[0]), "run_log": records}
        question = "Which cell do you mean?" if candidates else f"I could not find {request.label} {request.period} in this model. Which cell do you mean?"
        choice = interrupt({"question": question, "candidates": candidates})
        return {"target": target_cell(book, choice["ref"]), "run_log": records}

    return locate

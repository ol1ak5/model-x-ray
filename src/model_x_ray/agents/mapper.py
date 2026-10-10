from collections.abc import Callable
from typing import Literal

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from model_x_ray.agents.locator import Catalogue, workbook_catalogue
from model_x_ray.llm import invoke_with_usage, model_name_of
from model_x_ray.memory import ModelMemory
from model_x_ray.prompts import load_prompt
from model_x_ray.spreadsheet.engine import Workbook, split_ref
from model_x_ray.state import InvestigationState


class RowAnswer(BaseModel):
    label: str
    kind: Literal["revenue", "cost", "subtotal", "ratio", "other"] = Field(description="The kind of line: revenue, cost, subtotal, ratio (margins and growth rates), or other")


class ColumnAnswer(BaseModel):
    period: str
    kind: Literal["actual", "forecast"]


class ModelMapAnswer(BaseModel):
    rows: list[RowAnswer]
    columns: list[ColumnAnswer]


def example_cell(book: Workbook, label: str) -> str:
    cells = [ref for ref in book.cells() if book.row_label(ref) == label and book.column_header(ref) is not None]
    return max(cells, key=lambda ref: split_ref(ref)[1].column)


def describe_line(book: Workbook, label: str) -> str:
    ref = example_cell(book, label)
    formula = book.formula(ref) or "typed number"
    uses: list[str] = []
    for precedent in book.precedents(ref):
        name = book.row_label(precedent)
        if name and name not in uses:
            uses.append(name)
    return f"{label}: {formula}; uses {', '.join(uses)}" if uses else f"{label}: {formula}"


def mapper_brief(book: Workbook, catalogue: Catalogue) -> str:
    lines = [f"Periods: {', '.join(catalogue.periods)}", "Lines:"]
    lines += [describe_line(book, label) for label in catalogue.labels]
    return "\n".join(lines)


def make_map_model_node(llm: BaseChatModel, book: Workbook, memory: ModelMemory | None = None) -> Callable[[InvestigationState], dict]:
    catalogue = workbook_catalogue(book)
    revision = book.revision()
    structured = llm.with_structured_output(ModelMapAnswer, method="function_calling")
    system = SystemMessage(content=load_prompt("map_model"))

    def map_model(state: InvestigationState) -> dict:
        remembered = memory.model_map(state["spreadsheet_id"], revision) if memory else None
        if remembered is not None:
            return {"model_map": remembered}
        messages = [system, HumanMessage(content=mapper_brief(book, catalogue))]
        answer, records = invoke_with_usage(structured, messages, role="mapper", model=model_name_of(llm))
        rows = [row.model_dump() for row in answer.rows if row.label in catalogue.labels]
        columns = [column.model_dump() for column in answer.columns if column.period in catalogue.periods]
        model_map = {"rows": rows, "columns": columns}
        if memory is not None:
            memory.save_model_map(state["spreadsheet_id"], revision, model_map)
        return {"model_map": model_map, "run_log": records}

    return map_model

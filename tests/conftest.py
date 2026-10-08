from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from openpyxl import Workbook as OpenpyxlWorkbook
from openpyxl.comments import Comment
from openpyxl.styles import Font

from model_x_ray.spreadsheet.engine import Workbook
from model_x_ray.spreadsheet.source import SpreadsheetSource, XlsxSource
from model_x_ray.state import Patch

ASSUMPTIONS = {
    "B5": "Revenue growth", "C5": 0.08,
    "B6": "COGS % of revenue", "C6": 0.55,
    "B7": "Opex growth", "C7": 0.05,
}

PNL = {
    "A3": "EUR m", "F3": "2025A", "G3": "2026E", "H3": "2027E",
    "A4": "Revenue", "F4": 185.2, "G4": "=F4*(1+Assumptions!$C$5)", "H4": "=G4*(1+Assumptions!$C$5)",
    "A5": "COGS", "F5": -101.9, "G5": "=-G4*Assumptions!$C$6", "H5": "=-H4*Assumptions!$C$6",
    "A6": "Gross profit", "F6": "=F4+F5", "G6": "=G4+G5", "H6": "=H4+H5",
    "A7": "Opex", "F7": -47.6, "G7": "=F7*(1+Assumptions!$C$7)", "H7": -45.2,
    "A8": "EBITDA", "F8": "=F6+F7", "G8": "=G6+G7", "H8": "=H6+H7",
    "A9": "EBITDA growth", "G9": "=G8/F8-1", "H9": "=H8/G8-1",
}


def write_demo_workbook(path: Path, notes: dict[str, str] | None = None) -> Path:
    book = OpenpyxlWorkbook()
    pnl = book.active
    pnl.title = "P&L"
    assumptions = book.create_sheet("Assumptions")
    for ref, content in PNL.items():
        pnl[ref] = content
    for ref, content in ASSUMPTIONS.items():
        assumptions[ref] = content
    for ref, text in (notes or {}).items():
        pnl[ref].comment = Comment(text, "model owner")
    pnl["F7"].font = Font(color="0000FF")
    for ref in ("F7", "G7", "H7"):
        pnl[ref].number_format = "0.0"
    book.save(path)
    return path


@pytest.fixture
def demo_workbook_path(tmp_path: Path) -> Path:
    return write_demo_workbook(tmp_path / "demo_model.xlsx")


@pytest.fixture
def demo_workbook_with_override_note(tmp_path: Path) -> Path:
    return write_demo_workbook(tmp_path / "demo_model_override.xlsx", notes={"H7": "Per budget meeting, opex frozen at 45.2"})


class EngineSandbox:
    def __init__(self, source: SpreadsheetSource) -> None:
        self._source = source
        self._copies: dict[str, Workbook] = {}
        self.created: list[str] = []
        self.discarded: list[str] = []
        self.writes: list[dict] = []

    def create_copy(self, spreadsheet_id: str) -> str:
        copy_id = f"copy-{len(self.created) + 1}"
        self.created.append(copy_id)
        self._copies[copy_id] = self._source.load(spreadsheet_id)
        return copy_id

    def apply_patch(self, copy_id: str, patch: Patch) -> None:
        self._copies[copy_id] = self._copies[copy_id].with_patch(patch["cell"], patch["new_formula"])

    def read_values(self, copy_id: str, cells: list[str]) -> dict[str, object]:
        return {cell: self._copies[copy_id].value(cell) for cell in cells}

    def discard(self, copy_id: str) -> None:
        del self._copies[copy_id]
        self.discarded.append(copy_id)

    def write_corrected_copy(self, spreadsheet_id: str, patch: Patch, log_rows: list[list[object]]) -> str:
        self.writes.append({"spreadsheet_id": spreadsheet_id, "patch": dict(patch), "log_rows": log_rows})
        return f"corrected:{spreadsheet_id}"


@pytest.fixture
def engine_sandbox(demo_workbook_path: Path) -> EngineSandbox:
    return EngineSandbox(XlsxSource({"demo": demo_workbook_path}))


class ScriptedVerdict(BaseChatModel):
    bound: list[str] = []
    verdicts: list[tuple[str, str]] = [("confirmed", "the sandbox numbers hold")]
    human: list[str] = []
    system: list[str] = []

    @property
    def _llm_type(self) -> str:
        return "scripted-verdict"

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> "ScriptedVerdict":
        names = [getattr(t, "name", None) or getattr(t, "__name__", "") for t in tools]
        return self.model_copy(update={"bound": names, "human": self.human, "system": self.system})

    def _generate(self, messages: list[BaseMessage], stop: list[str] | None = None, **kwargs: Any) -> ChatResult:
        self.system.append(messages[0].content)
        self.human.append(messages[-1].content)
        verdict, reason = self.verdicts[min(len(self.human), len(self.verdicts)) - 1]
        call = {"name": "Verdict", "args": {"verdict": verdict, "reason": reason}, "id": "verify"}
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content="", tool_calls=[call]))])


@pytest.fixture
def scripted_verdict() -> ScriptedVerdict:
    return ScriptedVerdict()

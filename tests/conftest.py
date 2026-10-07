from pathlib import Path

import pytest
from openpyxl import Workbook as OpenpyxlWorkbook
from openpyxl.comments import Comment

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
    book.save(path)
    return path


@pytest.fixture
def demo_workbook_path(tmp_path: Path) -> Path:
    return write_demo_workbook(tmp_path / "demo_model.xlsx")


@pytest.fixture
def demo_workbook_with_override_note(tmp_path: Path) -> Path:
    return write_demo_workbook(tmp_path / "demo_model_override.xlsx", notes={"H7": "Per budget meeting, opex frozen at 45.2"})

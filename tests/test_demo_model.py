from pathlib import Path

import pytest

from model_x_ray.agents.locator import read_question, workbook_catalogue
from model_x_ray.rules import find_formula_outliers
from model_x_ray.spreadsheet.xlsx import load_xlsx

DEMO_DIR = Path(__file__).resolve().parents[1] / "demo"


def test_the_demo_model_loads_and_every_formula_calculates() -> None:
    book = load_xlsx(DEMO_DIR / "nvidia-pnl.xlsx")

    assert book.sheets == ["Assumptions", "P&L"]
    assert book.raw("P&L!A12") == "EBITDA"
    assert book.raw("P&L!G2") == "2030E"
    for ref in book.cells():
        assert book.value(ref) is not None, f"{ref} does not calculate"
    assert book.value("P&L!B3") == 130.5
    assert book.value("P&L!C3") == 215.9
    assert book.value("Assumptions!C3") == 0.70
    assert book.value("P&L!H3") == pytest.approx(1210, abs=15)


def test_the_error_variant_plants_one_break_the_agent_can_see() -> None:
    base = load_xlsx(DEMO_DIR / "nvidia-pnl.xlsx")
    error = load_xlsx(DEMO_DIR / "nvidia-pnl-error.xlsx")

    changed = [ref for ref in base.cells() if base.raw(ref) != error.raw(ref)]
    assert changed == ["P&L!G11"]
    assert base.raw("P&L!G11") == "=SUM(G7:G10)"
    assert error.raw("P&L!G11") == 45.0
    assert error.value("P&L!G11") < base.value("P&L!G11")

    outliers = [
        outlier
        for row in range(3, 17)
        for outlier in find_formula_outliers(error, f"P&L!D{row}:I{row}")
    ]
    assert [outlier["cell"] for outlier in outliers] == ["P&L!G11"]
    assert error.value("P&L!G13") > error.value("P&L!F13")
    assert error.value("P&L!G13") > error.value("P&L!H13")

    request = read_question("Why did EBITDA 2030E jump?", workbook_catalogue(error))
    assert request is not None and request.label == "EBITDA" and request.period == "2030E"

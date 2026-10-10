from datetime import date, datetime
from pathlib import Path

import openpyxl
import pytest
from conftest import write_demo_workbook
from test_investigator import OutlierScanner

from model_x_ray.graph import run_investigation
from model_x_ray.spreadsheet.engine import FormulaError, UnsupportedFormulaError
from model_x_ray.spreadsheet.source import XlsxSource
from model_x_ray.spreadsheet.xlsx import load_xlsx

SEGMENTS = [
    ("Segment", "Region", "Revenue", "Margin"),
    ("Data Center", "US", 120, 0.75),
    ("Gaming", "EU", 12, 0.6),
    ("Data Center", "EU", 30, 0.7),
    ("Automotive", "US", 2, 0.4),
]

FORMULAS = {
    "B1": '=SUMIF(Data!A2:A5,"Data Center",Data!C2:C5)',
    "B2": '=SUMIF(Data!C2:C5,">10")',
    "B3": '=SUMIF(Data!B2:B5,"<>US",Data!C2:C5)',
    "B4": "=SUMPRODUCT(Data!C2:C5,Data!D2:D5)",
    "B5": '=INDEX(Data!C2:C5,MATCH("Gaming",Data!A2:A5,0))',
    "B6": "=INDEX(Data!A2:D5,3,4)",
    "B7": '=VLOOKUP("Automotive",Data!A2:D5,3,FALSE)',
    "B8": '=_xlfn.XLOOKUP("Gaming",Data!A2:A5,Data!D2:D5)',
    "B9": '=XLOOKUP("Robotics",Data!A2:A5,Data!C2:C5,0)',
    "B10": '=IFERROR(VLOOKUP("Robotics",Data!A2:D5,3,FALSE),-1)',
    "B11": "=IFERROR(1/0,0)",
    "B12": "=IF(Data!C6=0,0,Data!C2/Data!C6)",
    "B13": "=AND(Data!C2>100,Data!D2>0.5)",
    "B14": "=OR(Data!C5>100,Data!D5>0.5)",
    "B15": "=NOT(Data!C5>100)",
    "B16": "=EOMONTH(Data!F1,1)",
    "B17": "=VLOOKUP(150,Data!H2:I4,2)",
    "B18": "=MATCH(150,Data!H2:H4)",
    "B19": "=XLOOKUP(\"Gaming\",Data!A2:A5,Data!C2:C5,,0)",
    "B20": '=SUMIFS(Data!C2:C5,Data!A2:A5,"Data Center",Data!B2:B5,"EU")',
    "B21": '=SUMIFS(Data!C2:C5,Data!D2:D5,">=0.6")',
    "B22": '=COUNTIF(Data!A2:A5,"Data Center")',
    "B23": '=COUNTIFS(Data!B2:B5,"US",Data!C2:C5,">1")',
    "B24": '=COUNTIF(Data!C2:C5,">10")',
}

EXPECTED = {
    "B1": 150.0, "B2": 162.0, "B3": 42.0, "B4": 119.0, "B5": 12.0, "B6": 0.7, "B7": 2.0, "B8": 0.6,
    "B9": 0.0, "B10": -1.0, "B11": 0.0, "B12": 0.0, "B13": True, "B14": False, "B15": True,
    "B16": float((date(2026, 2, 28) - date(1899, 12, 30)).days), "B17": 0.2, "B18": 2.0, "B19": 12.0,
    "B20": 30.0, "B21": 162.0, "B22": 2.0, "B23": 2.0, "B24": 3.0,
}


def write_functions_workbook(path: Path) -> Path:
    book = openpyxl.Workbook()
    data = book.active
    data.title = "Data"
    for row in SEGMENTS:
        data.append(list(row))
    data["F1"] = datetime(2026, 1, 31)
    for row, (threshold, rate) in enumerate([(0, 0.1), (100, 0.2), (1000, 0.3)], start=2):
        data[f"H{row}"], data[f"I{row}"] = threshold, rate
    calc = book.create_sheet("Calc")
    for ref, formula in FORMULAS.items():
        calc[ref] = formula
    calc["C1"] = '=VLOOKUP("Robotics",Data!A2:D5,3,FALSE)'
    calc["C2"] = "=INDIRECT(\"Data!C2\")"
    calc["C3"] = '=SUMIFS(Data!C2:C5,Data!A2:A4,"Gaming")'
    book.save(path)
    return path


def test_every_new_function_calculates_like_excel_and_reads_its_ranges_as_inputs(tmp_path: Path) -> None:
    book = load_xlsx(write_functions_workbook(tmp_path / "functions.xlsx"))

    for ref, expected in EXPECTED.items():
        assert book.value(f"Calc!{ref}") == pytest.approx(expected), ref

    assert set(book.precedents("Calc!B1")) == {f"Data!{c}{r}" for c in "AC" for r in range(2, 6)}
    assert "Calc!B7" in book.dependents("Data!C5")
    assert set(book.precedents("Calc!B20")) == {f"Data!{c}{r}" for c in "ABC" for r in range(2, 6)}
    with pytest.raises(FormulaError, match="different sizes"):
        book.value("Calc!C3")

    with pytest.raises(FormulaError, match="Robotics") as not_found:
        book.value("Calc!C1")
    assert not isinstance(not_found.value, UnsupportedFormulaError)
    with pytest.raises(UnsupportedFormulaError, match="INDIRECT"):
        book.value("Calc!C2")


def test_an_investigation_finds_the_planted_error_in_a_model_built_with_lookups(tmp_path: Path, engine_sandbox, scripted_verdict) -> None:
    path = write_demo_workbook(tmp_path / "lookups.xlsx")
    book = openpyxl.load_workbook(path)
    pnl = book["P&L"]
    for column, prior in (("G", "F"), ("H", "G")):
        pnl[f"{column}4"] = f'={prior}4*(1+INDEX(Assumptions!$C$5:$C$7,MATCH("Revenue growth",Assumptions!$B$5:$B$7,0)))'
        pnl[f"{column}5"] = f'=-{column}4*VLOOKUP("COGS % of revenue",Assumptions!$B$5:$C$7,2,FALSE)'
        pnl[f"{column}9"] = f"=IFERROR({column}8/{prior}8-1,0)"
    book.save(path)

    graph = run_investigation(OutlierScanner(), "demo", XlsxSource({"demo": path}), engine_sandbox, verifier=scripted_verdict)
    config = {"configurable": {"thread_id": "lookups"}}
    graph.invoke({"spreadsheet_id": "demo", "question": "Why did EBITDA 2027 jump on the P&L sheet?"}, config)
    state = graph.get_state(config).values

    assert state["target"]["value"] == pytest.approx(52.01, abs=0.01)
    assert state["hypotheses"][0]["cell"] == "P&L!H7"
    assert state["hypotheses"][0]["status"] == "confirmed"
    assert state["verifications"][-1]["after"]["P&L!H8"] == pytest.approx(44.73, abs=0.01)

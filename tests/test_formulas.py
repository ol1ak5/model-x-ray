import re
from datetime import date, datetime
from pathlib import Path

import openpyxl
import pytest
from openpyxl.workbook.defined_name import DefinedName
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


FINANCE_FORMULAS = {
    "A1": "=POWER(2,10)",
    "A2": "=2^-1",
    "A3": "=ROUNDDOWN(3.789,2)",
    "A4": "=ROUNDDOWN(-3.789,1)",
    "A5": "=ROUNDDOWN(31415.92654,-2)",
    "A6": "=INT(8.9)",
    "A7": "=INT(-8.9)",
    "A8": "=MOD(3,2)",
    "A9": "=MOD(-3,2)",
    "A10": "=MOD(3,-2)",
    "A11": "=PPMT(10%/12,1,24,2000)",
    "A12": "=PPMT(8%,10,10,200000)",
    "A13": "=_xlfn.XIRR(Flows!A1:A5,Flows!B1:B5)",
    "A14": "=PPMT(0,3,4,1000)",
    "A15": "=SUM(Flows!A1:A5)-PPMT(5%,2,3,Flows!A2,0,1)",
    "B1": "=POWER(-8,1/3)",
    "B2": "=(-8)^(1/3)",
    "B3": "=POWER(0,-1)",
    "B4": "=MOD(3,0)",
    "B5": "=XIRR(Flows!C1:C2,Flows!B1:B2)",
    "B6": "=PPMT(5%,5,4,1000)",
}

FINANCE_EXPECTED = {
    "A1": 1024.0, "A2": 0.5, "A3": 3.78, "A4": -3.7, "A5": 31400.0, "A6": 8.0, "A7": -9.0,
    "A8": 1.0, "A9": 1.0, "A10": -1.0, "A11": -75.623186, "A12": -27598.053462, "A13": 0.373362534, "A14": -250.0,
    "A15": 3872.323553,
}

FINANCE_ERRORS = {"B1": "#NUM!", "B2": "#NUM!", "B3": "#DIV/0!", "B4": "#DIV/0!", "B5": "#NUM!", "B6": "#NUM!"}


def test_finance_functions_from_a_real_project_finance_model_calculate_like_excel(tmp_path: Path) -> None:
    workbook = openpyxl.Workbook()
    flows = workbook.active
    flows.title = "Flows"
    for row, (flow, day) in enumerate(
        [(-10000, datetime(2008, 1, 1)), (2750, datetime(2008, 3, 1)), (4250, datetime(2008, 10, 30)), (3250, datetime(2009, 2, 15)), (2750, datetime(2009, 4, 1))], start=1
    ):
        flows[f"A{row}"], flows[f"B{row}"] = flow, day
    flows["C1"], flows["C2"] = 100, 50
    calc = workbook.create_sheet("Calc")
    for ref, formula in FINANCE_FORMULAS.items():
        calc[ref] = formula
    workbook.save(tmp_path / "finance.xlsx")
    book = load_xlsx(tmp_path / "finance.xlsx")

    for ref, expected in FINANCE_EXPECTED.items():
        assert book.value(f"Calc!{ref}") == pytest.approx(expected, abs=1e-6), ref
    assert set(book.precedents("Calc!A13")) == {f"Flows!{c}{r}" for c in "AB" for r in range(1, 6)}
    assert "Calc!A15" in book.dependents("Flows!A2")
    for ref, code in FINANCE_ERRORS.items():
        with pytest.raises(FormulaError, match=code):
            book.value(f"Calc!{ref}")


def write_project_finance_layout(path: Path) -> Path:
    workbook = openpyxl.Workbook()
    inputs = workbook.active
    inputs.title = "Inputs"
    inputs["B2"], inputs["B3"], inputs["B4"] = 0.05, 200, 300
    workbook.defined_names["growth"] = DefinedName("growth", attr_text="Inputs!$B$2")
    workbook.defined_names["volumes"] = DefinedName("volumes", attr_text="Inputs!$B$3:$B$4")
    workbook.defined_names["dates_row"] = DefinedName("dates_row", attr_text="Acc!$8:$8")
    acc = workbook.create_sheet("Acc")
    acc["H74"] = datetime(2021, 12, 31)
    for column, (year, debt, scale) in zip("PQR", [(2020, 100, 2), (2021, 90, 3), (2022, 80, 4)]):
        acc[f"{column}8"] = datetime(year, 12, 31)
        acc[f"{column}70"] = debt
        acc[f"{column}78"] = scale
        acc[f"{column}114"] = f"=-IF({column}8<$H$74,0,INDEX(70:70,1,MATCH($H$74,8:8,0)))*{column}78"
    acc["B1"] = "=MATCH(EOMONTH(Acc!P8,12),Acc!P8:R8,0)"
    acc["B2"] = "=SUM(P:P)"
    acc["B3"] = "=Inputs!B3*(1+growth)"
    acc["B4"] = "=SUM(volumes)"
    acc["B5"] = "=MATCH(Acc!H74,dates_row,0)"
    acc["B6"] = "=IFERROR(#REF!,0)"
    acc["C1"] = "=#REF!"
    acc["C2"] = "=Inputs!B3*undefined_rate"
    acc["C3"] = "=Inputs!#REF!+1"
    workbook.save(path)
    return path


def test_a_project_finance_layout_with_whole_rows_names_and_dates_calculates_like_excel(tmp_path: Path) -> None:
    book = load_xlsx(write_project_finance_layout(tmp_path / "layout.xlsx"))

    assert [book.value(f"Acc!{c}114") for c in "PQR"] == [0.0, -270.0, -360.0]
    assert book.value("Acc!B1") == 2.0
    assert book.value("Acc!B2") == 100 + 2 + 0.0
    assert book.value("Acc!B3") == pytest.approx(210.0)
    assert book.value("Acc!B4") == 500.0
    assert book.value("Acc!B5") == 17.0
    assert book.value("Acc!B6") == 0.0
    for ref, message in {"Acc!C1": "#REF!", "Acc!C2": "#NAME?", "Acc!C3": "#REF!"}.items():
        with pytest.raises(FormulaError, match=re.escape(message)):
            book.value(ref)

    assert book.formula_pattern("Acc!P114") == book.formula_pattern("Acc!Q114") == book.formula_pattern("Acc!R114")
    assert book.shifted_formula("Acc!P114", "Acc!Q114") == book.formula("Acc!Q114")
    assert {"Acc!P70", "Acc!R70", "Acc!H74", "Acc!R8"} <= set(book.precedents("Acc!Q114"))
    assert "Acc!B3" in book.dependents("Inputs!B2")
    assert "Acc!B4" in book.dependents("Inputs!B4")


COMMON_FORMULAS = {
    "A1": "=PMT(8%/12,10,10000)",
    "A2": "=PMT(6%/12,18*12,0,50000)",
    "A3": "=IRR(Data!A1:A6)",
    "A4": "=IRR(Data!A1:A3,-10%)",
    "A5": '=HLOOKUP("Axles",Data!C1:E4,2,TRUE)',
    "A6": '=HLOOKUP("Bearings",Data!C1:E4,3,FALSE)',
    "A7": '=HLOOKUP("B",Data!C1:E4,3,TRUE)',
    "A8": "=COUNT(Data!G1:G5)",
    "A9": "=COUNTA(Data!G1:G5)",
    "A10": "=ISERROR(1/0)",
    "A11": "=ISERROR(Data!G1)",
    "A12": "=ISNUMBER(Data!G1)",
    "A13": "=ISNUMBER(1/0)",
    "A14": "=ISTEXT(Data!G2)",
    "A15": "=ISBLANK(Data!G3)",
    "A16": "=LARGE(Data!H1:H5,3)",
    "A17": "=SMALL(Data!H1:H5,2)",
    "A18": '=CHOOSE(2,"a","b","c")',
    "A19": "=CHOOSE(1,5,1/0)",
    "A20": "=EXP(1)",
    "A21": "=LN(86)",
    "A22": "=NORMSDIST(1.333333)",
    "A23": "=_xlfn.NORM.S.DIST(1.333333,TRUE)",
    "A24": "=NORM.S.DIST(1.333333,FALSE)",
    "B1": "=LARGE(Data!H1:H5,9)",
    "B2": '=CHOOSE(4,"a","b","c")',
    "B3": "=LN(0)",
    "B4": "=IRR(Data!H1:H5)",
    "B5": '=HLOOKUP("Nuts",Data!C1:E4,2,FALSE)',
}

COMMON_EXPECTED = {
    "A1": -1037.032089, "A2": -129.081161, "A3": 0.086630948, "A4": -0.443506941, "A5": 4.0, "A6": 7.0, "A7": 5.0,
    "A8": 2.0, "A9": 4.0, "A10": True, "A11": False, "A12": True, "A13": False, "A14": True, "A15": True,
    "A16": 4.0, "A17": 3.0, "A18": "b", "A19": 5.0, "A20": 2.718281828, "A21": 4.454347296, "A22": 0.908788726,
    "A23": 0.908788726, "A24": 0.164010148,
}

COMMON_ERRORS = {"B1": "#NUM!", "B2": "#VALUE!", "B3": "#NUM!", "B4": "#NUM!", "B5": "not found"}


def test_common_functions_from_public_valuation_and_trading_models_calculate_like_excel(tmp_path: Path) -> None:
    workbook = openpyxl.Workbook()
    data = workbook.active
    data.title = "Data"
    for row, flow in enumerate([-70000, 12000, 15000, 18000, 21000, 26000], start=1):
        data[f"A{row}"] = flow
    for row, items in enumerate([("Axles", "Bearings", "Bolts"), (4, 4, 9), (5, 7, 10), (6, 8, 11)], start=1):
        for column, item in zip("CDE", items):
            data[f"{column}{row}"] = item
    data["G1"], data["G2"], data["G4"], data["G5"] = 10, "text", datetime(2026, 1, 31), True
    for row, number in enumerate([3, 5, 3, 5, 4], start=1):
        data[f"H{row}"] = number
    calc = workbook.create_sheet("Calc")
    for ref, formula in COMMON_FORMULAS.items():
        calc[ref] = formula
    workbook.save(tmp_path / "common.xlsx")
    book = load_xlsx(tmp_path / "common.xlsx")

    for ref, expected in COMMON_EXPECTED.items():
        value = book.value(f"Calc!{ref}")
        assert value == (pytest.approx(expected, abs=1e-6) if isinstance(expected, float) else expected), ref
    for ref, message in COMMON_ERRORS.items():
        with pytest.raises(FormulaError, match=re.escape(message)):
            book.value(f"Calc!{ref}")
    assert set(book.precedents("Calc!A6")) == {f"Data!{c}{r}" for c in "CDE" for r in range(1, 5)}


def test_a_link_to_another_workbook_is_reported_as_unsupported_in_plain_words(tmp_path: Path) -> None:
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Summary"
    sheet["A1"] = "=[1]May!$J$10"
    sheet["A2"] = "='[2]Deal sheet'!B4*2"
    sheet["A3"] = "=IFERROR([1]May!$J$10,0)"
    workbook.save(tmp_path / "linked.xlsx")
    book = load_xlsx(tmp_path / "linked.xlsx")

    for ref in ("Summary!A1", "Summary!A2", "Summary!A3"):
        with pytest.raises(UnsupportedFormulaError, match="another workbook"):
            book.value(ref)

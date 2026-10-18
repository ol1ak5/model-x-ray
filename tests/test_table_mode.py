from pathlib import Path

import openpyxl

from model_x_ray.rules import scan_tables
from model_x_ray.spreadsheet.xlsx import load_xlsx


def write_trading_sheets(path: Path) -> Path:
    workbook = openpyxl.Workbook()
    deals = workbook.active
    deals.title = "Deals"
    deals.append(["Deal", "Volume", "Price", "Value", "Flag"])
    for row, (volume, price) in enumerate([(100, 2.5), (80, 2.6), (120, 2.4), (90, 2.7), (60, 2.5), (110, 2.6), (70, 2.8)], start=2):
        deals.append([f"D-{row}", volume, price, f"=B{row}*C{row}", f"=IF(B{row}>85,1,0)"])
    deals["D5"] = 288
    deals["D7"] = "=B6*C7"
    deals["E6"] = 1
    deals["A10"], deals["D10"] = "Total", "=SUM(D2:D8)"
    costs = workbook.create_sheet("Costs")
    costs.append(["Item", "Cost"])
    for row, cost in enumerate([12, 30, 7, 25, 9], start=2):
        costs.append([f"Item {row}", cost])
    costs["A8"], costs["B8"] = "Total cost", "=SUM(B2:B5)"
    costs["A9"], costs["B9"] = "Check", "=SUM(B3)"
    costs["A11"], costs["B11"] = "Fees", 4
    costs["A12"], costs["B12"] = "Taxes", 6
    costs["A13"], costs["B13"] = "Total other", "=SUM(B11:B12)"
    costs["A15"], costs["B15"] = "Grand total", "=B8+B13"
    workbook.save(path)
    return path


def test_incomplete_totals_and_column_pattern_breaks_are_found_with_their_fixes(tmp_path: Path) -> None:
    book = load_xlsx(write_trading_sheets(tmp_path / "trading.xlsx"))

    found = {finding["cell"]: finding for finding in scan_tables(book)}

    assert set(found) == {"Costs!B8", "Deals!D5", "Deals!D7", "Deals!E6"}
    assert found["Costs!B8"]["kind"] == "incomplete_total"
    assert found["Costs!B8"]["fix"] == "=SUM(B2:B6)"
    assert "B6" in found["Costs!B8"]["reason"]
    assert (found["Deals!D5"]["kind"], found["Deals!D5"]["fix"]) == ("typed_in_column", "=B5*C5")
    assert (found["Deals!D7"]["kind"], found["Deals!D7"]["fix"]) == ("column_pattern", "=B7*C7")
    assert found["Deals!E6"]["fix"] == "=IF(B6>85,1,0)"


def test_a_clean_table_has_no_findings(tmp_path: Path) -> None:
    path = write_trading_sheets(tmp_path / "trading.xlsx")
    workbook = openpyxl.load_workbook(path)
    workbook["Deals"]["D5"], workbook["Deals"]["D7"], workbook["Deals"]["E6"] = "=B5*C5", "=B7*C7", "=IF(B6>85,1,0)"
    workbook["Costs"]["B8"] = "=SUM(B2:B6)"
    workbook.save(path)

    assert scan_tables(load_xlsx(path)) == []


def test_a_table_without_a_timeline_is_checked_end_to_end_and_the_total_is_fixed(tmp_path: Path) -> None:
    from uuid import uuid4

    from conftest import ScriptedVerdict
    from test_investigator import ScriptedDiagnosis

    from model_x_ray.benchmark.runner import Setup, build_setup_graph, drive_graph
    from model_x_ray.spreadsheet.sandbox import XlsxSandbox
    from model_x_ray.spreadsheet.source import XlsxSource

    path = write_trading_sheets(tmp_path / "trading.xlsx")
    workbook = openpyxl.load_workbook(path)
    workbook["Deals"]["D5"], workbook["Deals"]["D7"], workbook["Deals"]["E6"] = "=B5*C5", "=B7*C7", "=IF(B6>85,1,0)"
    workbook.save(path)
    setup = Setup(name="scripted", kind="investigator", model="scripted-investigator", verifier="scripted-verifier")

    def factory(model_id: str):
        if model_id == "scripted-verifier":
            return ScriptedVerdict()
        return ScriptedDiagnosis(turns=[(["Costs!B8"], "Costs!B8", "=SUM(B2:B6)")])

    source = XlsxSource({"trading": path})
    graph = build_setup_graph(setup, source, XlsxSandbox(source, tmp_path / "corrected"), "trading", factory)
    final = drive_graph(graph, {"spreadsheet_id": "trading", "question": ""}, {"configurable": {"thread_id": uuid4().hex}})

    target = final["target"]
    assert (target["mode"], target["sheet"], target["cell"]) == ("table", "Costs", "B8")
    assert (target["value"], target["prior_value"], target["expected_formula"]) == (74.0, 83.0, "=SUM(B2:B6)")
    assert final["verifications"][-1]["verdict"] == "confirmed"
    assert final["verifications"][-1]["checks"] == {"anomaly_resolved": True, "dependents_consistent": True, "pattern_restored": True}
    assert "leaves out B6" in final["report"] and "which gives 83.00" in final["report"]
    assert final["corrected_copy_id"]


def test_a_subtotal_counted_twice_is_found() -> None:
    from model_x_ray.spreadsheet.engine import Workbook

    book = Workbook({
        "Sheet!A1": "Fees", "Sheet!B1": 4.0, "Sheet!A2": "Taxes", "Sheet!B2": 6.0,
        "Sheet!A3": "Subtotal", "Sheet!B3": "=SUM(B1:B2)", "Sheet!A4": "Total", "Sheet!B4": "=SUM(B1:B3)",
    })

    found = {f["cell"]: f for f in scan_tables(book)}
    assert found["Sheet!B4"]["kind"] == "double_count"
    assert found["Sheet!B4"]["fix"] == "=B1+B2"


def test_a_calculation_with_no_broken_pattern_is_handed_to_the_investigator_for_a_logic_review(tmp_path: Path) -> None:
    from model_x_ray.agents.locator import make_locate_node
    from model_x_ray.spreadsheet.engine import Workbook

    book = Workbook({
        "Calc!A1": "Revenue", "Calc!B1": 100.0, "Calc!A2": "Costs", "Calc!B2": 60.0,
        "Calc!A3": "Margin", "Calc!B3": "=B1+B2", "Calc!A4": "Margin %", "Calc!B4": "=B3/B1",
    })

    update = make_locate_node(None, book)({"spreadsheet_id": "calc", "question": ""})

    assert update["target"]["mode"] == "review"
    assert update["target"]["cell"] == "B4"
    assert "main result" in update["question"]

from pathlib import Path
from uuid import uuid4

import openpyxl
import pytest

from conftest import ScriptedVerdict
from test_investigator import ScriptedDiagnosis

from model_x_ray.benchmark.runner import Setup, build_setup_graph, drive_graph
from model_x_ray.spreadsheet.sandbox import XlsxSandbox
from model_x_ray.spreadsheet.source import XlsxSource

SETUP = Setup(name="scripted", kind="investigator", model="scripted-investigator", verifier="scripted-verifier")


def run(tmp_path: Path, path: Path) -> dict:
    source = XlsxSource({"model": path})
    graph = build_setup_graph(SETUP, source, XlsxSandbox(source, tmp_path / "corrected"), "model", lambda model_id: ScriptedVerdict() if model_id == "scripted-verifier" else ScriptedDiagnosis(turns=[([], None)]))
    return drive_graph(graph, {"spreadsheet_id": "model", "question": ""}, {"configurable": {"thread_id": uuid4().hex}})


def write_cost_sheet(path: Path, rate: str) -> Path:
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Costs"
    sheet["A1"], sheet["B1"] = "Item", "Amount"
    for row, (item, amount) in enumerate([("Pipeline fees", 1200), ("Storage", 450), ("Transport", 830), ("Balancing", 120), ("Admin", 75)], start=2):
        sheet[f"A{row}"], sheet[f"B{row}"] = item, amount
    sheet["A7"], sheet["B7"] = "Subtotal", "=SUM(B2:B6)"
    sheet["A8"], sheet["B8"] = "FX rate", rate
    sheet["A9"], sheet["B9"] = "Total in USD", "=B7*B8"
    workbook.save(path)
    return path


def test_when_the_main_result_reads_another_workbook_the_logic_review_takes_the_largest_result_it_can_calculate(tmp_path: Path) -> None:
    final = run(tmp_path, write_cost_sheet(tmp_path / "costs.xlsx", "=[1]Rates!$B$2"))

    assert (final["target"]["mode"], final["target"]["cell"]) == ("review", "B7")
    assert final["target"]["value"] == 2675.0
    assert final["report"]
    assert final.get("patch") is None


def test_a_model_whose_formulas_all_read_another_workbook_says_why_nothing_could_be_checked(tmp_path: Path) -> None:
    path = write_cost_sheet(tmp_path / "costs.xlsx", "=[1]Rates!$B$2")
    workbook = openpyxl.load_workbook(path)
    workbook["Costs"]["B7"] = "=[1]Ledger!$C$9"
    workbook.save(path)

    with pytest.raises(ValueError, match=r"none of the 3 formulas in this model can be calculated.*B7.*reads another workbook"):
        run(tmp_path, path)

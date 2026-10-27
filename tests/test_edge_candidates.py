from pathlib import Path
from uuid import uuid4

import openpyxl

from conftest import ScriptedDiagnosis, ScriptedVerdict

from model_x_ray.benchmark.runner import Setup, build_setup_graph, drive_graph
from model_x_ray.spreadsheet.sandbox import XlsxSandbox
from model_x_ray.spreadsheet.source import XlsxSource

YEARS = "CDEFGH"


def write_forecast(path: Path, last_revenue: str) -> Path:
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "P&L"
    sheet["A1"], sheet["B1"] = "Revenue growth", 0.08
    for index, column in enumerate(YEARS):
        sheet[f"{column}3"] = f"{2024 + index}E"
    sheet["A4"], sheet["A5"], sheet["A6"] = "Revenue", "Costs", "Profit"
    sheet["C4"], sheet["C5"] = 500.0, 300.0
    for index, column in enumerate(YEARS[1:], start=1):
        previous = YEARS[index - 1]
        sheet[f"{column}4"] = f"={previous}4*(1+$B$1)"
        sheet[f"{column}5"] = f"={column}4*0.6"
    for column in YEARS:
        sheet[f"{column}6"] = f"={column}4-{column}5"
    sheet["H4"] = last_revenue
    workbook.save(path)
    return path


def check(tmp_path: Path, path: Path, model: ScriptedDiagnosis) -> dict:
    setup = Setup(name="scripted", kind="investigator", model="scripted-investigator", verifier="scripted-verifier")
    source = XlsxSource({"m": path})
    graph = build_setup_graph(setup, source, XlsxSandbox(source, tmp_path / "copies"), "m", lambda model_id: ScriptedVerdict() if model_id == "scripted-verifier" else model)
    return drive_graph(graph, {"spreadsheet_id": "m", "question": ""}, {"configurable": {"thread_id": uuid4().hex}})


def test_a_last_year_that_reads_two_years_back_is_offered_to_the_investigator_and_fixed_when_it_judges_it_an_error(tmp_path: Path) -> None:
    path = write_forecast(tmp_path / "forecast.xlsx", "=F4*(1+$B$1)")
    model = ScriptedDiagnosis(briefs=[], turns=[([], None)], choice=1, judgements=[{"number": 1, "verdict": "error", "reason": "the last year reads two years back"}])

    final = check(tmp_path, path, model)

    assert "P&L!H4" in model.briefs[0] and "last period" in model.briefs[0]
    assert (final["patch"]["cell"], final["patch"]["new_formula"]) == ("P&L!H4", "=G4*(1+$B$1)")
    assert final["verifications"][-1]["verdict"] == "confirmed"


def test_an_edge_break_is_never_patched_without_the_investigators_judgement(tmp_path: Path) -> None:
    path = write_forecast(tmp_path / "forecast.xlsx", "=F4*(1+$B$1)")

    final = check(tmp_path, path, ScriptedDiagnosis(briefs=[], turns=[([], None)]))

    assert final.get("patch") is None or final["patch"]["cell"] != "P&L!H4"


def test_a_deliberate_terminal_year_judged_intentional_is_left_alone(tmp_path: Path) -> None:
    path = write_forecast(tmp_path / "forecast.xlsx", "=G4*1.02")
    model = ScriptedDiagnosis(briefs=[], turns=[([], None)], judgements=[{"number": 1, "verdict": "intentional", "reason": "terminal year grows at a stable 2%"}])

    final = check(tmp_path, path, model)

    assert final.get("patch") is None

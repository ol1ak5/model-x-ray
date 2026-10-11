from pathlib import Path

import openpyxl
import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver
from test_investigator import ScriptedDiagnosis
from test_project_layout import write_project_model

from model_x_ray.api import AgentModels, UsageCap, create_app
from model_x_ray.graph import run_investigation
from model_x_ray.rules import scan_model
from model_x_ray.spreadsheet.sandbox import XlsxSandbox
from model_x_ray.spreadsheet.source import XlsxSource
from model_x_ray.spreadsheet.xlsx import load_xlsx


def clean_demo(demo_workbook_path: Path, tmp_path: Path) -> Path:
    book = openpyxl.load_workbook(demo_workbook_path)
    book["P&L"]["H7"] = "=G7*(1+Assumptions!$C$7)"
    book.save(tmp_path / "clean.xlsx")
    return tmp_path / "clean.xlsx"


def test_the_model_scan_flags_hardcodes_among_formulas_but_not_typed_history_or_side_columns(demo_workbook_path: Path, tmp_path: Path) -> None:
    assert [o["cell"] for o in scan_model(load_xlsx(demo_workbook_path))] == ["P&L!H7"]
    assert scan_model(load_xlsx(clean_demo(demo_workbook_path, tmp_path))) == []
    assert scan_model(load_xlsx(write_project_model(tmp_path / "project.xlsx"))) == []
    assert [o["cell"] for o in scan_model(load_xlsx(write_project_model(tmp_path / "planted.xlsx", planted=55.0)))] == ["FM!O24"]


def test_checking_a_model_without_a_question_investigates_the_hardcode_through_the_output_it_moves(demo_workbook_path: Path, engine_sandbox, scripted_verdict) -> None:
    graph = run_investigation(ScriptedDiagnosis(turns=[(["P&L!H7"], "P&L!H7")]), "demo", XlsxSource({"demo": demo_workbook_path}), engine_sandbox, verifier=scripted_verdict)
    config = {"configurable": {"thread_id": "check"}}
    graph.invoke({"spreadsheet_id": "demo", "question": ""}, config)
    state = graph.get_state(config).values

    assert (state["target"]["cell"], state["target"]["label"], state["target"]["period"]) == ("H8", "EBITDA", "2027E")
    assert state["question"] == "Check the model: EBITDA 2027E depends on P&L!H7, which is a typed value where the row uses =RC[-1]*(1+Assumptions!R7C3)."
    assert state["hypotheses"][0]["status"] == "confirmed"
    assert state["report"].startswith("EBITDA 2027E moved from")


def test_checking_a_clean_model_reports_no_error_on_its_main_output(demo_workbook_path: Path, engine_sandbox, scripted_verdict, tmp_path: Path) -> None:
    path = clean_demo(demo_workbook_path, tmp_path)
    nothing = ScriptedDiagnosis(turns=[([], "P&L!H7")])
    graph = run_investigation(nothing, "clean", XlsxSource({"clean": path}), engine_sandbox, verifier=scripted_verdict)
    config = {"configurable": {"thread_id": "check-clean"}}
    graph.invoke({"spreadsheet_id": "clean", "question": ""}, config)
    state = graph.get_state(config).values

    assert state["target"]["label"] == "EBITDA"
    assert state["question"].startswith("Check the model: no cell breaks its row's pattern; EBITDA")
    assert "Check the model" in nothing.briefs[0]


def test_an_uploaded_model_can_be_checked_and_uploads_stay_private(demo_workbook_path: Path, engine_sandbox, scripted_verdict, tmp_path: Path) -> None:
    models = AgentModels(llm=ScriptedDiagnosis(turns=[(["P&L!H7"], "P&L!H7")]), verifier=scripted_verdict)
    source = XlsxSource({"demo": demo_workbook_path})
    app = create_app(source, XlsxSandbox(source, tmp_path / "corrected"), models, InMemorySaver(), UsageCap(per_visitor=10, total=100), upload_dir=tmp_path / "uploads")
    client = TestClient(app)

    uploaded = client.post("/spreadsheets", params={"name": "My model.xlsx"}, content=demo_workbook_path.read_bytes())
    assert uploaded.status_code == 201
    upload_id = uploaded.json()["id"]
    assert uploaded.json()["name"] == "My model.xlsx" and uploaded.json()["sheets"] == ["P&L", "Assumptions"]
    assert [s["id"] for s in client.get("/spreadsheets").json()] == ["demo"]

    body = client.post("/investigations", json={"spreadsheet_id": upload_id}).json()
    assert body["target"]["cell"] == "H8"
    assert body["question"].startswith("Check the model:")

    bad = client.post("/spreadsheets", params={"name": "notes.xlsx"}, content=b"not a spreadsheet")
    assert bad.status_code == 400
    assert "not a readable .xlsx" in bad.json()["detail"]


@pytest.mark.parametrize("name", ["model.csv", "../escape.xlsx"])
def test_only_xlsx_files_with_safe_names_are_accepted(name: str, demo_workbook_path: Path, engine_sandbox, scripted_verdict, tmp_path: Path) -> None:
    app = create_app(XlsxSource({"demo": demo_workbook_path}), engine_sandbox, AgentModels(llm=ScriptedDiagnosis()), InMemorySaver(), UsageCap(per_visitor=10, total=100), upload_dir=tmp_path / "uploads")
    response = TestClient(app).post("/spreadsheets", params={"name": name}, content=demo_workbook_path.read_bytes())
    assert response.status_code == 201 if name == "../escape.xlsx" else response.status_code == 400
    assert not (tmp_path / "escape.xlsx").exists()

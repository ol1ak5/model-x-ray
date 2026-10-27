from pathlib import Path

import openpyxl
from conftest import ScriptedDiagnosis
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver

from model_x_ray.api import AgentModels, UsageCap, create_app
from model_x_ray.spreadsheet.source import XlsxSource
from model_x_ray.spreadsheet.xlsx import load_xlsx

SHEET = "Inputs & Property valuation"


def renamed(demo_workbook_path: Path, tmp_path: Path) -> Path:
    book = openpyxl.load_workbook(demo_workbook_path)
    book["P&L"].title = SHEET
    path = tmp_path / "renamed.xlsx"
    book.save(path)
    return path


def test_the_agent_may_quote_a_sheet_name_with_spaces_and_an_ampersand_the_way_excel_does(demo_workbook_path: Path, engine_sandbox, scripted_verdict, tmp_path: Path) -> None:
    path = renamed(demo_workbook_path, tmp_path)
    book = load_xlsx(path)
    plain = book.value(f"{SHEET}!H8")
    assert book.value(f"'{SHEET}'!H8") == plain
    assert book.value(f"'{SHEET}!H8'") == plain
    assert book.value(f"'{SHEET}'!$H$8") == plain

    source = XlsxSource({"demo": path})
    engine_sandbox.__init__(source)
    for named in (f"'{SHEET}'!H7", f"'{SHEET}!H7'"):
        models = AgentModels(llm=ScriptedDiagnosis(turns=[([named], named)]), verifier=scripted_verdict)
        client = TestClient(create_app(source, engine_sandbox, models, InMemorySaver(), UsageCap(per_visitor=10, total=100)))

        view = client.post("/investigations", json={"spreadsheet_id": "demo", "question": f"Why did EBITDA 2027 jump on the {SHEET} sheet?"})

        assert view.status_code == 201, view.text
        assert view.json()["status"] == "needs_review"
        assert view.json()["patch"]["cell"] == f"{SHEET}!H7", "the fix lands on the cell the agent named, whatever quotes it used"

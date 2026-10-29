import json
from pathlib import Path

import openpyxl
from conftest import ScriptedDiagnosis
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver

from model_x_ray.api import AgentModels, UsageCap, create_app
from model_x_ray.spreadsheet.sandbox import XlsxSandbox
from model_x_ray.spreadsheet.source import XlsxSource


def client_for(demo_workbook_path: Path, scratch: Path, scripted_verdict) -> TestClient:
    source = XlsxSource({"demo": demo_workbook_path})
    models = AgentModels(llm=ScriptedDiagnosis(turns=[(["P&L!H7"], "P&L!H7")]), verifier=scripted_verdict)
    return TestClient(create_app(source, XlsxSandbox(source, scratch / "corrected"), models, InMemorySaver(), UsageCap(per_visitor=10, total=100), upload_dir=scratch / "uploads"))


def cells_of(sheet: dict) -> dict[str, dict]:
    return {cell["ref"]: cell for cell in sheet["cells"]}


def test_the_viewer_gets_every_sheet_with_calculated_values_and_the_formulas_behind_them(demo_workbook_path: Path, scripted_verdict, tmp_path: Path) -> None:
    client = client_for(demo_workbook_path, tmp_path, scripted_verdict)

    book = client.post("/workbook", json={"spreadsheet_id": "demo"})

    assert book.status_code == 200, book.text
    sheets = book.json()["sheets"]
    assert [sheet["name"] for sheet in sheets] == ["P&L", "Assumptions"]
    pnl = sheets[0]
    assert (pnl["rows"], pnl["columns"]) == (9, 8), "the grid reaches the last used row and column"
    cells = cells_of(pnl)
    assert cells["A6"] == {"ref": "A6", "value": "Gross profit", "formula": None}
    assert cells["G6"]["formula"] == "=G4+G5"
    assert round(cells["G6"]["value"], 4) == round(185.2 * 1.08 * (1 - 0.55), 4), "values are calculated by the engine, not read from a cache"
    assert cells["H7"] == {"ref": "H7", "value": -45.2, "formula": None}
    assert cells_of(sheets[1])["C6"]["value"] == 0.55


def test_a_visitor_sees_the_sheets_of_their_own_file_sent_with_the_request(demo_workbook_path: Path, scripted_verdict, tmp_path: Path) -> None:
    client = client_for(demo_workbook_path, tmp_path, scripted_verdict)
    own = openpyxl.load_workbook(demo_workbook_path)
    own["Assumptions"]["C6"] = 0.6
    own.create_sheet("Notes")["A1"] = "Board version"
    path = tmp_path / "own.xlsx"
    own.save(path)

    book = client.post("/workbook", data={"request": json.dumps({})}, files={"file": ("Own model.xlsx", path.read_bytes(), "application/octet-stream")})

    assert book.status_code == 200, book.text
    sheets = {sheet["name"]: sheet for sheet in book.json()["sheets"]}
    assert set(sheets) == {"P&L", "Assumptions", "Notes"}
    assert cells_of(sheets["Assumptions"])["C6"]["value"] == 0.6
    assert cells_of(sheets["Notes"])["A1"]["value"] == "Board version"

    unknown = client.post("/workbook", json={"spreadsheet_id": "nowhere"})
    assert unknown.status_code == 400


def test_the_viewer_gets_the_workbook_as_it_was_designed_fills_fonts_number_formats_borders_and_widths(scripted_verdict, tmp_path: Path) -> None:
    model = Path(__file__).parent.parent / "demo_models" / "PPA_Model_Europe.xlsx"
    client = client_for(model, tmp_path, scripted_verdict)

    book = client.post("/workbook", json={"spreadsheet_id": "demo"})

    assert book.status_code == 200, book.text
    results = next(sheet for sheet in book.json()["sheets"] if sheet["name"] == "Results")

    def style(ref: str) -> dict:
        return results["styles"][results["cell_styles"][ref]]

    assert style("M12") == {"fill": "#0D5C33", "color": "#FFFFFF", "bold": True, "size": 9.0, "align": "center"}, "a header keeps its dark green fill and its white, bold, centred text"
    npv = style("M16")
    assert npv["fill"] == "#F7FAF8"
    assert npv["format"] == "#,##0;\\(#,##0\\);\\-", "the NPV keeps its thousands format with negatives in brackets"
    assert npv["border_bottom"].startswith("1px solid")
    assert style("H16")["format"].startswith("0.0%"), "coverage stays a percentage"
    assert style("H16")["color"] == "#12814A", "a linked input keeps its green text"
    assert results["widths"]["C"] == 11 * 7 + 5, "column widths follow the file"
    assert results["gridlines"] is False, "the sheet hides gridlines, as in Excel"

import base64
import io
import json
from pathlib import Path

import openpyxl

from conftest import ScriptedDiagnosis
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver

from model_x_ray.api import AgentModels, UsageCap, create_app
from model_x_ray.spreadsheet.sandbox import CHANGE_LOG_SHEET, XlsxSandbox
from model_x_ray.spreadsheet.source import XlsxSource


def with_file(request: dict, content: bytes, name: str = "Demo model.xlsx") -> dict:
    return {"data": {"request": json.dumps(request)}, "files": {"file": (name, content, "application/octet-stream")}}


def final_view(text: str) -> dict:
    views = [json.loads(block.split("data: ", 1)[1]) for block in text.strip().split("\n\n") if block.startswith("event: view")]
    assert views, text
    return views[-1]


def test_a_cell_the_reviewer_called_deliberate_is_set_aside_by_the_next_round(demo_workbook_path: Path, scripted_verdict, tmp_path: Path) -> None:
    source = XlsxSource({"demo": demo_workbook_path})
    models = AgentModels(llm=ScriptedDiagnosis(turns=[(["P&L!H7"], "P&L!H7")]), verifier=scripted_verdict)
    client = TestClient(create_app(source, XlsxSandbox(source, tmp_path / "corrected"), models, InMemorySaver(), UsageCap(per_visitor=10, total=100), upload_dir=tmp_path / "uploads"))

    first = final_view(client.post("/investigations/stream", json={"spreadsheet_id": "demo", "question": ""}).text)
    assert first["patch"]["cell"] == "P&L!H7", "the first round finds the typed opex"

    second = final_view(client.post("/investigations/stream", json={"spreadsheet_id": "demo", "question": "", "set_aside": ["P&L!H7"]}).text)

    assert [o["cell"] for o in second["known_overrides"]] == ["P&L!H7"]
    assert second["known_overrides"][0]["content"] == "-45.2"
    assert second["patch"] is None or second["patch"]["cell"] != "P&L!H7", "a cell the reviewer called deliberate is never proposed again"
    assert "P&L!H7" not in json.dumps(second["target"]), "nor is it chosen as the cell to investigate"


def test_every_suspect_is_listed_up_front_and_each_parallel_check_investigates_its_own(scripted_verdict, tmp_path: Path) -> None:
    model = Path(__file__).parent.parent / "demo_models" / "demo.xlsx"
    source = XlsxSource({"demo": model})
    models = AgentModels(llm=ScriptedDiagnosis(turns=[([], None)]), verifier=scripted_verdict)
    client = TestClient(create_app(source, XlsxSandbox(source, tmp_path / "corrected"), models, InMemorySaver(), UsageCap(per_visitor=10, total=100), upload_dir=tmp_path / "uploads"))

    suspects = client.post("/suspects", json={"spreadsheet_id": "demo"}).json()["cells"]

    assert suspects[:2] == ["P&L!G5", "P&L!I6"], "the sign flip and the typed value, the two planted errors, come first"
    for suspect in suspects:
        others = [cell for cell in suspects if cell != suspect]
        view = final_view(client.post("/investigations/stream", json={"spreadsheet_id": "demo", "question": "", "set_aside": others}).text)
        assert suspect in view["question"], (suspect, view["question"])


def test_errors_checked_in_parallel_are_approved_one_after_another_into_one_corrected_copy(scripted_verdict, tmp_path: Path) -> None:
    model = Path(__file__).parent.parent / "demo_models" / "demo.xlsx"

    def instance(turn: tuple) -> TestClient:
        source = XlsxSource({"demo": model})
        models = AgentModels(llm=ScriptedDiagnosis(turns=[turn]), verifier=scripted_verdict)
        corrected = tmp_path / f"corrected-{turn[1]}"
        return TestClient(create_app(source, XlsxSandbox(source, corrected), models, InMemorySaver(), UsageCap(per_visitor=10, total=100), upload_dir=tmp_path / f"uploads-{turn[1]}", copy_dir=corrected))

    sign = instance((["P&L!G5"], "P&L!G5", "=-G4*Assumptions!$C$5", "wrong_reference"))
    typed = instance((["P&L!I6"], "P&L!I6", "=I4+I5", "typed_value"))
    first = final_view(sign.post("/investigations/stream", json={"spreadsheet_id": "demo", "question": "", "set_aside": ["P&L!I6"]}).text)
    second = final_view(typed.post("/investigations/stream", json={"spreadsheet_id": "demo", "question": "", "set_aside": ["P&L!G5"]}).text)
    assert first["patch"]["cell"] == "P&L!G5" and second["patch"]["cell"] == "P&L!I6"

    approved = final_view(sign.post(f"/investigations/{first['id']}/resume/stream", json={"action": "approve", "reason": "", "state": first}).text)
    copy = base64.b64decode(approved["corrected_file"]["base64"])

    resumed = typed.post(f"/investigations/{second['id']}/resume/stream", **with_file({"action": "approve", "reason": "", "state": second, "on_corrected_copy": True}, copy))
    assert resumed.status_code == 200, resumed.text
    book = openpyxl.load_workbook(io.BytesIO(base64.b64decode(final_view(resumed.text)["corrected_file"]["base64"])))
    assert book["P&L"]["G5"].value == "=-G4*Assumptions!$C$5", "the first approved fix stays in the copy"
    assert book["P&L"]["I6"].value == "=I4+I5", "and the second is added to it"
    assert [row[1] for row in book[CHANGE_LOG_SHEET].iter_rows(min_row=2, values_only=True)] == ["P&L!G5", "P&L!I6"], "the change log lists both fixes"

    again = typed.post(f"/investigations/{second['id']}/resume/stream", **with_file({"action": "approve", "reason": "", "state": second, "on_corrected_copy": True}, base64.b64decode(final_view(resumed.text)["corrected_file"]["base64"])))
    assert again.status_code == 400, "a copy where the fixed cell already changed cannot take the same fix again"

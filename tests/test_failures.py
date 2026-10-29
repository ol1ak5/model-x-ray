from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver
from test_investigator import ScriptedDiagnosis

from model_x_ray.api import AgentModels, UsageCap, create_app
from model_x_ray.spreadsheet.source import XlsxSource

QUESTION = {"spreadsheet_id": "demo", "question": "Why did EBITDA 2027 jump on the P&L sheet?"}


def app_with(demo_workbook_path: Path, engine_sandbox, scripted_verdict, cap: UsageCap | None = None, upload_dir: Path | None = None) -> TestClient:
    models = AgentModels(llm=ScriptedDiagnosis(turns=[(["P&L!H7"], "P&L!H7")]), verifier=scripted_verdict)
    source = XlsxSource({"demo": demo_workbook_path})
    app = create_app(source, engine_sandbox, models, InMemorySaver(), cap or UsageCap(per_visitor=10, total=100), upload_dir=upload_dir)
    return TestClient(app, raise_server_exceptions=False)


def assert_failure(response, status: int, code: str) -> None:
    assert response.status_code == status, response.text
    body = response.json()
    assert set(body) == {"detail", "code"}, body
    assert body["code"] == code, body
    assert isinstance(body["detail"], str) and body["detail"].strip()


def test_every_refusal_on_the_way_to_a_check_carries_a_code_a_page_can_act_on(demo_workbook_path: Path, engine_sandbox, scripted_verdict) -> None:
    client = app_with(demo_workbook_path, engine_sandbox, scripted_verdict)

    assert_failure(client.post("/investigations", json={"spreadsheet_id": ""}), 400, "missing_model")
    assert_failure(client.post("/investigations", json={"spreadsheet_id": "elsewhere"}), 400, "unknown_model")
    assert_failure(client.get("/investigations/nothing"), 404, "unknown_investigation")
    assert_failure(client.post("/investigations/nothing/resume", json={"action": "approve"}), 404, "unknown_investigation")
    assert_failure(client.post("/investigations/nothing/ask", json={"question": "Why?", "state": {"question": "x"}}), 400, "bad_state")
    assert_failure(client.post("/investigations/nothing/resume", json={"state": {"spreadsheet_id": "demo"}, "action": "approve"}), 400, "bad_state")
    assert_failure(client.post("/investigations/demo/ask", json={"question": "   "}), 400, "missing_question")
    assert_failure(client.post("/investigations/demo/ask", json={"question": "x" * 2000}), 400, "question_too_long")


def test_a_finished_check_cannot_be_resumed_and_a_missing_corrected_copy_says_so(demo_workbook_path: Path, engine_sandbox, scripted_verdict) -> None:
    client = app_with(demo_workbook_path, engine_sandbox, scripted_verdict)

    started = client.post("/investigations", json=QUESTION)
    assert started.status_code == 201
    investigation_id = started.json()["id"]
    assert_failure(client.get(f"/investigations/{investigation_id}/corrected"), 404, "no_corrected_copy")
    client.post(f"/investigations/{investigation_id}/resume", json={"action": "reject", "reason": "not convinced"})
    assert_failure(client.post(f"/investigations/{investigation_id}/resume", json={"action": "approve"}), 409, "finished_investigation")


def test_the_usage_cap_and_an_invalid_fix_have_their_own_codes(demo_workbook_path: Path, engine_sandbox, scripted_verdict) -> None:
    client = app_with(demo_workbook_path, engine_sandbox, scripted_verdict, cap=UsageCap(per_visitor=1, total=1))

    started = client.post("/investigations", json=QUESTION)
    assert started.status_code == 201
    assert_failure(client.post("/investigations", json=QUESTION), 429, "usage_cap")
    assert_failure(
        client.post(f"/investigations/{started.json()['id']}/resume", json={"action": "edit", "patch": {"cell": "P&L!H7", "new_formula": '=INDIRECT("G7")'}}),
        422,
        "invalid_fix",
    )


def test_an_upload_that_is_refused_says_which_way_it_failed(demo_workbook_path: Path, engine_sandbox, scripted_verdict, tmp_path: Path) -> None:
    client = app_with(demo_workbook_path, engine_sandbox, scripted_verdict, upload_dir=tmp_path / "uploads")

    assert_failure(client.post("/spreadsheets?name=notes.txt", content=b"hello"), 400, "upload_rejected")
    assert_failure(client.post("/spreadsheets?name=broken.xlsx", content=b"not a workbook"), 400, "workbook_unreadable")
    assert_failure(client.post("/spreadsheets?name=huge.xlsx", content=b"0" * (10 * 1024 * 1024 + 1)), 413, "upload_too_large")


def test_a_streamed_failure_carries_the_same_code_as_a_plain_one(demo_workbook_path: Path, engine_sandbox, scripted_verdict) -> None:
    client = app_with(demo_workbook_path, engine_sandbox, scripted_verdict, cap=UsageCap(per_visitor=1, total=1))

    assert client.post("/investigations/stream", json=QUESTION).status_code == 200
    refused = client.post("/investigations/stream", json=QUESTION)
    assert_failure(refused, 429, "usage_cap")

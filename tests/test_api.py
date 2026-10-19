from pathlib import Path

import pytest
from conftest import ScriptedAnswer
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver
from test_investigator import ScriptedDiagnosis

from model_x_ray.api import AgentModels, UsageCap, create_app
from model_x_ray.spreadsheet.source import XlsxSource
from model_x_ray.spreadsheet.xlsx import load_xlsx


def client_for(demo_workbook_path: Path, engine_sandbox, scripted_verdict, locator=None, cap: UsageCap | None = None) -> TestClient:
    models = AgentModels(
        llm=ScriptedDiagnosis(turns=[(["P&L!H7"], "P&L!H7")]),
        verifier=scripted_verdict,
        locator=locator,
    )
    app = create_app(XlsxSource({"demo": demo_workbook_path}), engine_sandbox, models, InMemorySaver(), cap or UsageCap(per_visitor=10, total=100))
    return TestClient(app)


def test_the_demo_page_is_allowed_from_any_local_dev_port(demo_workbook_path: Path, engine_sandbox, scripted_verdict) -> None:
    client = client_for(demo_workbook_path, engine_sandbox, scripted_verdict)

    moved = client.get("/spreadsheets", headers={"Origin": "http://localhost:5174"})
    assert moved.headers["access-control-allow-origin"] == "http://localhost:5174"

    stranger = client.get("/spreadsheets", headers={"Origin": "https://spreadsheets.example"})
    assert "access-control-allow-origin" not in stranger.headers


def test_a_full_investigation_pauses_for_review_and_writes_the_corrected_copy_on_approval(demo_workbook_path: Path, engine_sandbox, scripted_verdict) -> None:
    client = client_for(demo_workbook_path, engine_sandbox, scripted_verdict)

    started = client.post("/investigations", json={"spreadsheet_id": "demo", "question": "Why did EBITDA 2027 jump on the P&L sheet?"})
    assert started.status_code == 201
    body = started.json()
    assert body["status"] == "needs_review"
    assert (body["target"]["sheet"], body["target"]["cell"]) == ("P&L", "H8")
    assert "Root cause found in P&L!H7" in body["report"]
    assert body["pause"]["patch"]["cell"] == "P&L!H7"
    assert [h["status"] for h in body["hypotheses"]] == ["confirmed"]
    assert body["causal_tree"]["cell"] == "P&L!H8"
    assert any(e["kind"] == "anomaly" for e in body["evidence"])
    assert {entry["role"] for entry in body["run_log"]} >= {"investigator", "verifier"}
    assert "messages" not in body

    again = client.get(f"/investigations/{body['id']}")
    assert again.json()["status"] == "needs_review"

    done = client.post(f"/investigations/{body['id']}/resume", json={"action": "approve", "reason": "the typed opex is the error"})
    assert done.status_code == 200
    assert done.json()["status"] == "done"
    assert done.json()["corrected_copy_id"] == "corrected:demo"
    assert engine_sandbox.writes[0]["patch"]["cell"] == "P&L!H7"


def test_an_unknown_line_pauses_for_a_cell_and_continues_after_the_choice(demo_workbook_path: Path, engine_sandbox, scripted_verdict) -> None:
    locator = ScriptedAnswer(tool="LocateRequest", answer={"label": "Net income", "period": "2027E", "sheet": None})
    client = client_for(demo_workbook_path, engine_sandbox, scripted_verdict, locator=locator)

    body = client.post("/investigations", json={"spreadsheet_id": "demo", "question": "Why did net income fall next year?"}).json()
    assert body["status"] == "needs_cell"
    assert body["pause"]["candidates"] == []
    assert "Net income" in body["pause"]["question"]

    chosen = client.post(f"/investigations/{body['id']}/resume", json={"ref": "P&L!H8"}).json()
    assert chosen["status"] == "needs_review"
    assert chosen["target"]["cell"] == "H8"

    rejected = client.post(f"/investigations/{body['id']}/resume", json={"action": "reject", "reason": "not convinced"}).json()
    assert rejected["status"] == "done"
    assert rejected["corrected_copy_id"] is None
    assert engine_sandbox.writes == []


def test_a_human_fix_typed_without_an_equals_sign_is_normalized_before_it_runs(demo_workbook_path: Path, engine_sandbox, scripted_verdict) -> None:
    client = client_for(demo_workbook_path, engine_sandbox, scripted_verdict)
    body = client.post("/investigations", json={"spreadsheet_id": "demo", "question": "Why did EBITDA 2027 jump on the P&L sheet?"}).json()
    assert body["status"] == "needs_review"

    edited = client.post(
        f"/investigations/{body['id']}/resume",
        json={"action": "edit", "reason": "sign slip on direct costs", "patch": {"cell": "P&L!H7", "old_formula": "-45.2", "new_formula": "-G7*Assumptions!$C$7"}},
    )

    assert edited.status_code == 200
    assert edited.json()["status"] == "needs_review"
    assert edited.json()["patch"]["new_formula"] == "=-G7*Assumptions!$C$7"
    patched = load_xlsx(demo_workbook_path).with_patch("P&L!H7", "=-G7*Assumptions!$C$7")
    assert edited.json()["verifications"][-1]["after"]["P&L!H8"] == pytest.approx(patched.value("P&L!H8"))


def test_a_fix_that_cannot_be_calculated_is_refused_and_the_run_stays_paused(demo_workbook_path: Path, engine_sandbox, scripted_verdict) -> None:
    client = client_for(demo_workbook_path, engine_sandbox, scripted_verdict)
    body = client.post("/investigations", json={"spreadsheet_id": "demo", "question": "Why did EBITDA 2027 jump on the P&L sheet?"}).json()
    copies_before = len(engine_sandbox.created)

    refused = client.post(
        f"/investigations/{body['id']}/resume",
        json={"action": "edit", "reason": "", "patch": {"cell": "P&L!H7", "old_formula": "-45.2", "new_formula": "=SUMX(G7)"}},
    )

    assert refused.status_code == 422
    assert "P&L!H7" in refused.json()["detail"]
    assert "starts with =" in refused.json()["detail"]
    assert len(engine_sandbox.created) == copies_before

    still = client.get(f"/investigations/{body['id']}").json()
    assert still["status"] == "needs_review"
    assert still["patch"]["new_formula"] == "=G7*(1+Assumptions!$C$7)"

    approved = client.post(f"/investigations/{body['id']}/resume", json={"action": "approve", "reason": ""})
    assert approved.status_code == 200
    assert approved.json()["status"] == "done"


def test_clear_errors_and_the_usage_cap(demo_workbook_path: Path, engine_sandbox, scripted_verdict) -> None:
    client = client_for(demo_workbook_path, engine_sandbox, scripted_verdict, cap=UsageCap(per_visitor=1, total=100))
    question = {"spreadsheet_id": "demo", "question": "Why did EBITDA 2027 jump?"}

    unknown = client.post("/investigations", json={"spreadsheet_id": "other", "question": "Why?"})
    assert unknown.status_code == 400
    assert "Unknown spreadsheet 'other'" in unknown.json()["detail"]

    assert client.get("/investigations/nope").status_code == 404

    first = client.post("/investigations", json=question)
    assert first.status_code == 201
    done = client.post(f"/investigations/{first.json()['id']}/resume", json={"action": "reject", "reason": "no"})
    assert client.post(f"/investigations/{first.json()['id']}/resume", json={"action": "approve", "reason": "late"}).status_code == 409
    assert done.json()["status"] == "done"

    capped = client.post("/investigations", json=question)
    assert capped.status_code == 429
    assert "limit" in capped.json()["detail"]

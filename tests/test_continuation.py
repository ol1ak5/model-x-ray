import json
from pathlib import Path

from conftest import EngineSandbox, ScriptedDiagnosis
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver

from model_x_ray.api import AgentModels, UsageCap, create_app
from model_x_ray.spreadsheet.source import XlsxSource

QUESTION = {"spreadsheet_id": "demo", "question": "Why did EBITDA 2027 jump on the P&L sheet?"}

PATCH = {"cell": "P&L!H7", "old_formula": "-45.2", "new_formula": "=G7*(1+Assumptions!$C$7)", "source": "agent"}


def app_for(path: Path, sandbox: EngineSandbox, verdict) -> TestClient:
    models = AgentModels(llm=ScriptedDiagnosis(turns=[(["P&L!H7"], "P&L!H7")]), verifier=verdict)
    return TestClient(create_app(XlsxSource({"demo": path}), sandbox, models, InMemorySaver(), UsageCap(per_visitor=50, total=100)))


def paused_on_review(path: Path, sandbox: EngineSandbox, verdict) -> tuple[TestClient, dict]:
    client = app_for(path, sandbox, verdict)
    view = client.post("/investigations", json=QUESTION).json()
    assert view["status"] == "needs_review"
    return client, view


def browser_state(view: dict) -> dict:
    return json.loads(json.dumps(view))


def test_a_second_app_finishes_the_review_the_first_one_paused_on(demo_workbook_path: Path, engine_sandbox: EngineSandbox, scripted_verdict) -> None:
    _, view = paused_on_review(demo_workbook_path, engine_sandbox, scripted_verdict)
    carried = browser_state(view)
    assert carried["spreadsheet_id"] == "demo"
    assert carried["attempts"] == 1
    assert carried["contributions"]

    restarted = app_for(demo_workbook_path, engine_sandbox, scripted_verdict)

    assert restarted.get(f"/investigations/{view['id']}").status_code == 404
    assert restarted.post(f"/investigations/{view['id']}/resume", json={"action": "approve", "reason": "typed opex"}).status_code == 404

    streamed = restarted.post(f"/investigations/{view['id']}/resume/stream", json={"action": "approve", "reason": "typed opex", "state": carried})

    assert streamed.status_code == 200
    assert "event: step" in streamed.text
    assert "Saving a new version" in streamed.text
    assert '"status": "done"' in streamed.text
    assert '"corrected_copy_id": "corrected:demo"' in streamed.text
    assert engine_sandbox.writes[0]["patch"] == PATCH


def test_the_carried_state_writes_what_the_live_thread_writes(demo_workbook_path: Path, engine_sandbox: EngineSandbox, scripted_verdict) -> None:
    live, view = paused_on_review(demo_workbook_path, engine_sandbox, scripted_verdict)
    live.post(f"/investigations/{view['id']}/resume", json={"action": "approve", "reason": "typed opex"})

    carried_path = demo_workbook_path.parent / "carried.xlsx"
    carried_path.write_bytes(demo_workbook_path.read_bytes())
    carried_sandbox = EngineSandbox(XlsxSource({"demo": carried_path}))
    restarted = app_for(carried_path, carried_sandbox, scripted_verdict)
    restarted.post(f"/investigations/{view['id']}/resume", json={"action": "approve", "reason": "typed opex", "state": browser_state(view)})

    assert len(engine_sandbox.writes) == 1
    assert len(carried_sandbox.writes) == 1
    assert engine_sandbox.writes[0]["patch"] == carried_sandbox.writes[0]["patch"]
    assert engine_sandbox.writes[0]["log_rows"][1][1:] == carried_sandbox.writes[0]["log_rows"][1][1:]
    assert engine_sandbox.writes[0]["log_rows"][1][1] == "P&L!H7"


def test_the_carried_state_rejects_without_touching_the_workbook(demo_workbook_path: Path, engine_sandbox: EngineSandbox, scripted_verdict) -> None:
    _, view = paused_on_review(demo_workbook_path, engine_sandbox, scripted_verdict)
    restarted = app_for(demo_workbook_path, engine_sandbox, scripted_verdict)

    rejected = restarted.post(f"/investigations/{view['id']}/resume", json={"action": "reject", "reason": "not convinced", "intentional": True, "state": browser_state(view)})

    assert rejected.status_code == 200
    assert rejected.json()["status"] == "done"
    assert rejected.json()["corrected_copy_id"] is None
    assert engine_sandbox.writes == []
    assert restarted.post(f"/investigations/{view['id']}/resume", json={"action": "approve", "reason": "late"}).status_code == 409


def test_an_edited_fix_is_tested_again_from_the_carried_state(demo_workbook_path: Path, engine_sandbox: EngineSandbox, scripted_verdict) -> None:
    _, view = paused_on_review(demo_workbook_path, engine_sandbox, scripted_verdict)
    restarted = app_for(demo_workbook_path, engine_sandbox, scripted_verdict)
    edit = {"action": "edit", "reason": "use the budget growth", "patch": {"cell": "P&L!H7", "old_formula": "-45.2", "new_formula": "=G7*1.05"}, "state": browser_state(view)}

    again = restarted.post(f"/investigations/{view['id']}/resume", json=edit)

    assert again.status_code == 200
    body = again.json()
    assert body["status"] == "needs_review"
    assert body["patch"] == {"cell": "P&L!H7", "old_formula": "-45.2", "new_formula": "=G7*1.05", "source": "human"}
    assert engine_sandbox.created


def test_a_state_the_server_did_not_write_is_refused(demo_workbook_path: Path, engine_sandbox: EngineSandbox, scripted_verdict) -> None:
    _, view = paused_on_review(demo_workbook_path, engine_sandbox, scripted_verdict)
    carried = browser_state(view)
    restarted = app_for(demo_workbook_path, engine_sandbox, scripted_verdict)
    path = f"/investigations/{view['id']}/resume"

    assert restarted.post(path, json={"action": "approve", "reason": "x"}).status_code == 404

    no_spreadsheet = restarted.post(path, json={"action": "approve", "state": {"question": "Why?"}})
    assert no_spreadsheet.status_code == 400
    assert "spreadsheet" in no_spreadsheet.json()["detail"]

    unknown = restarted.post(path, json={"action": "approve", "state": {**carried, "spreadsheet_id": "somewhere-else"}})
    assert unknown.status_code == 400
    assert "Unknown spreadsheet" in unknown.json()["detail"]

    wrong_lists = restarted.post(path, json={"action": "approve", "state": {**carried, "hypotheses": "no"}})
    assert wrong_lists.status_code == 400
    assert "hypotheses" in wrong_lists.json()["detail"]

    no_action = restarted.post(path, json={"state": carried})
    assert no_action.status_code == 400
    assert "action" in no_action.json()["detail"]

    assert engine_sandbox.writes == []

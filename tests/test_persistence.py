import sqlite3
from pathlib import Path

from conftest import EngineSandbox, ScriptedDiagnosis
from fastapi.testclient import TestClient

from model_x_ray.api import AgentModels, UsageCap, create_app
from model_x_ray.memory import sqlite_checkpointer
from model_x_ray.spreadsheet.source import XlsxSource

QUESTION = {"spreadsheet_id": "demo", "question": "Why did EBITDA 2027 jump on the P&L sheet?"}


def app_on(path: Path, sandbox: EngineSandbox, checkpoints: Path, investigator: ScriptedDiagnosis, verdict) -> TestClient:
    models = AgentModels(llm=investigator, verifier=verdict)
    return TestClient(create_app(XlsxSource({"demo": path}), sandbox, models, sqlite_checkpointer(str(checkpoints)), UsageCap(per_visitor=50, total=100)))


def stored_threads(checkpoints: Path) -> list[str]:
    connection = sqlite3.connect(checkpoints)
    try:
        return [row[0] for row in connection.execute("select distinct thread_id from checkpoints")]
    finally:
        connection.close()


def test_a_restart_forgets_a_paused_investigation_even_with_the_checkpoint_on_disk(demo_workbook_path: Path, engine_sandbox: EngineSandbox, scripted_verdict, tmp_path: Path) -> None:
    checkpoints = tmp_path / "checkpoints.db"
    running = app_on(demo_workbook_path, engine_sandbox, checkpoints, ScriptedDiagnosis(turns=[(["P&L!H7"], "P&L!H7")]), scripted_verdict)

    body = running.post("/investigations", json=QUESTION).json()

    assert body["status"] == "needs_review"
    assert running.get(f"/investigations/{body['id']}").status_code == 200
    assert stored_threads(checkpoints) == [body["id"]]

    restarted = app_on(demo_workbook_path, engine_sandbox, checkpoints, ScriptedDiagnosis(turns=[(["P&L!H7"], "P&L!H7")]), scripted_verdict)

    assert restarted.get(f"/investigations/{body['id']}").status_code == 404
    assert restarted.post(f"/investigations/{body['id']}/resume", json={"action": "approve", "reason": "typed opex"}).status_code == 404

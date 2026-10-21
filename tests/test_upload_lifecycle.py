import json
import os
import time
from collections.abc import Callable
from pathlib import Path

from conftest import ScriptedDiagnosis
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver

from model_x_ray.api import AgentModels, UsageCap, create_app
from model_x_ray.spreadsheet.sandbox import XlsxSandbox
from model_x_ray.spreadsheet.source import XlsxSource

QUESTION = "Why did EBITDA 2027 jump on the P&L sheet?"


def app_for(path: Path, tmp_path: Path, scripted_verdict, clock: Callable[[], float] = time.monotonic, ttl: float = 1800.0) -> tuple[TestClient, XlsxSource, Path, Path]:
    source = XlsxSource({"demo": path})
    uploads = tmp_path / "uploads"
    corrected = tmp_path / "corrected"
    models = AgentModels(llm=ScriptedDiagnosis(turns=[(["P&L!H7"], "P&L!H7")]), verifier=scripted_verdict)
    app = create_app(
        source, XlsxSandbox(source, corrected), models, InMemorySaver(), UsageCap(per_visitor=10, total=100),
        upload_dir=uploads, upload_ttl=ttl, clock=clock, copy_dir=corrected, copy_ttl=ttl,
    )
    return TestClient(app), source, uploads, corrected


def upload(client: TestClient, path: Path, name: str = "My model.xlsx") -> str:
    response = client.post("/spreadsheets", params={"name": name}, content=path.read_bytes())
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_a_finished_run_deletes_the_upload_and_the_id_stops_resolving(demo_workbook_path: Path, scripted_verdict, tmp_path: Path) -> None:
    client, _, uploads, corrected = app_for(demo_workbook_path, tmp_path, scripted_verdict)
    upload_id = upload(client, demo_workbook_path)
    stored = uploads / f"{upload_id}.xlsx"
    assert stored.is_file()

    started = client.post("/investigations", json={"spreadsheet_id": upload_id, "question": QUESTION}).json()
    assert started["status"] == "needs_review"
    assert stored.is_file(), "the model is still needed while the run is paused"

    done = client.post(f"/investigations/{started['id']}/resume", json={"action": "approve", "reason": "sign slip on COGS"})
    assert done.status_code == 200
    assert done.json()["status"] == "done"
    assert done.json()["corrected_copy_id"]

    assert not stored.exists(), "the uploaded model is the visitor's file and must not outlive its run"
    assert [sheet["id"] for sheet in client.get("/spreadsheets").json()] == ["demo"]

    again = client.post("/investigations", json={"spreadsheet_id": upload_id, "question": QUESTION})
    assert again.status_code == 400
    assert "Unknown spreadsheet" in again.json()["detail"]
    assert list(corrected.glob("*.xlsx")), "the fix is still written for the download"


def test_an_abandoned_upload_is_swept_after_the_time_to_live(demo_workbook_path: Path, scripted_verdict, tmp_path: Path) -> None:
    now = [1000.0]
    client, source, uploads, _ = app_for(demo_workbook_path, tmp_path, scripted_verdict, clock=lambda: now[0], ttl=60.0)
    upload_id = upload(client, demo_workbook_path)
    started = client.post("/investigations", json={"spreadsheet_id": upload_id, "question": QUESTION}).json()
    assert started["status"] == "needs_review"
    stored = uploads / f"{upload_id}.xlsx"

    now[0] += 59.0
    assert client.get("/spreadsheets").status_code == 200
    assert stored.is_file(), "a run paused inside its time to live keeps its model"

    now[0] += 2.0
    assert [sheet["id"] for sheet in client.get("/spreadsheets").json()] == ["demo"]
    assert not stored.exists()
    assert upload_id not in source.ids()
    sheet = client.get(f"/investigations/{started['id']}/sheet")
    assert sheet.status_code == 404
    assert "no longer" in sheet.json()["detail"]


def test_the_corrected_copy_is_served_once_and_removed_after_the_download(demo_workbook_path: Path, scripted_verdict, tmp_path: Path) -> None:
    client, _, _, corrected = app_for(demo_workbook_path, tmp_path, scripted_verdict)
    started = client.post("/investigations", json={"spreadsheet_id": "demo", "question": QUESTION}).json()
    done = client.post(f"/investigations/{started['id']}/resume", json={"action": "approve", "reason": "sign slip on COGS"}).json()
    name = done["corrected_copy_id"]
    path = corrected / name
    assert path.is_file()

    first = client.get(f"/investigations/{started['id']}/corrected")

    assert first.status_code == 200
    assert first.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert first.content[:2] == b"PK", "the visitor downloads a real workbook"
    assert not path.exists(), "the corrected model is deal data and is not kept after the download"
    assert json.loads(json.dumps(done))["corrected_copy_id"] == name

    assert client.get(f"/investigations/{started['id']}/corrected").status_code == 404


def approved(client: TestClient, spreadsheet_id: str) -> None:
    started = client.post("/investigations", json={"spreadsheet_id": spreadsheet_id, "question": QUESTION})
    assert started.status_code == 201, started.text
    done = client.post(f"/investigations/{started.json()['id']}/resume", json={"action": "approve", "reason": "sign slip on COGS"})
    assert done.status_code == 200, done.text
    assert done.json()["corrected_copy_id"]


def test_a_corrected_copy_nobody_downloads_is_swept_after_the_time_to_live(demo_workbook_path: Path, scripted_verdict, tmp_path: Path) -> None:
    client, _, _, corrected = app_for(demo_workbook_path, tmp_path, scripted_verdict)
    approved(client, "demo")
    second = upload(client, demo_workbook_path, "Second model.xlsx")
    approved(client, second)

    stale, fresh = sorted(corrected.glob("*.xlsx"), key=lambda path: path.stat().st_mtime)
    now = time.time()
    os.utime(stale, (now - 3600, now - 3600))
    os.utime(fresh, (now - 60, now - 60))

    assert client.get("/spreadsheets").status_code == 200
    assert not stale.exists(), "a copy nobody downloaded is deal data the server should not keep"
    assert fresh.is_file(), "a copy inside the window is still available for the download"


def test_the_sweep_leaves_a_copy_alone_while_its_download_is_in_flight(tmp_path: Path) -> None:
    from model_x_ray.api import Copies

    copy = tmp_path / "demo-corrected.xlsx"
    copy.write_bytes(b"xlsx")
    aged = time.time() - 3600
    os.utime(copy, (aged, aged))
    copies = Copies(tmp_path, ttl=1800.0)

    copies.holding(copy)
    assert copies.sweep() == []
    assert copy.is_file()

    copies.release(copy)
    assert not copy.exists()

import shutil
from pathlib import Path

import openpyxl
import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver
from test_investigator import ScriptedDiagnosis

from model_x_ray.api import AgentModels, UsageCap, create_app
from model_x_ray.server import app_from_env
from model_x_ray.spreadsheet.sandbox import XlsxSandbox
from model_x_ray.spreadsheet.source import XlsxSource


def test_the_app_from_env_lists_every_model_in_the_folder_and_allows_the_frontend(demo_workbook_path: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    models = tmp_path / "models"
    (models / "planted").mkdir(parents=True)
    shutil.copy(demo_workbook_path, models / "demo.xlsx")
    shutil.copy(demo_workbook_path, models / "planted" / "variant-001.xlsx")
    monkeypatch.setenv("NEBIUS_API_KEY", "test-key")
    monkeypatch.setenv("NEBIUS_BASE_URL", "https://api.tokenfactory.nebius.com/v1/")
    monkeypatch.setenv("MODEL_X_RAY_MODELS_DIR", str(models))
    monkeypatch.setenv("MODEL_X_RAY_OUTPUT_DIR", str(tmp_path / "corrected"))
    monkeypatch.setenv("MODEL_X_RAY_CHECKPOINTS", str(tmp_path / "checkpoints.db"))
    monkeypatch.setenv("MODEL_X_RAY_ALLOWED_ORIGINS", "http://localhost:5173,https://model-x-ray.vercel.app")
    client = TestClient(app_from_env())

    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/spreadsheets").json() == [
        {"id": "demo", "sheets": ["P&L", "Assumptions"]},
        {"id": "planted/variant-001", "sheets": ["P&L", "Assumptions"]},
    ]
    preflight = client.options("/investigations", headers={"Origin": "https://model-x-ray.vercel.app", "Access-Control-Request-Method": "POST"})
    assert preflight.headers["access-control-allow-origin"] == "https://model-x-ray.vercel.app"
    assert "access-control-allow-origin" not in client.get("/health", headers={"Origin": "https://evil.example"}).headers


def test_a_missing_models_folder_is_reported_clearly(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MODEL_X_RAY_MODELS_DIR", str(tmp_path / "nowhere"))
    with pytest.raises(ValueError, match="nowhere"):
        app_from_env()


def test_the_corrected_file_can_be_downloaded_after_approval(demo_workbook_path: Path, scripted_verdict, tmp_path: Path) -> None:
    source = XlsxSource({"demo": demo_workbook_path})
    models = AgentModels(llm=ScriptedDiagnosis(turns=[(["P&L!H7"], "P&L!H7")]), verifier=scripted_verdict)
    app = create_app(source, XlsxSandbox(source, tmp_path / "corrected"), models, InMemorySaver(), UsageCap(per_visitor=10, total=100))
    client = TestClient(app)

    body = client.post("/investigations", json={"spreadsheet_id": "demo", "question": "Why did EBITDA 2027 jump on the P&L sheet?"}).json()
    assert client.get(f"/investigations/{body['id']}/corrected").status_code == 404
    client.post(f"/investigations/{body['id']}/resume", json={"action": "approve", "reason": "typed opex"})

    download = client.get(f"/investigations/{body['id']}/corrected")
    assert download.status_code == 200
    assert download.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    saved = tmp_path / "downloaded.xlsx"
    saved.write_bytes(download.content)
    assert openpyxl.load_workbook(saved)["P&L"]["H7"].value == "=G7*(1+Assumptions!$C$7)"

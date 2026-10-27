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


def test_the_sheet_around_the_target_is_returned_for_the_grid_view(demo_workbook_path: Path, scripted_verdict, tmp_path: Path) -> None:
    source = XlsxSource({"demo": demo_workbook_path})
    models = AgentModels(llm=ScriptedDiagnosis(turns=[(["P&L!H7"], "P&L!H7")]), verifier=scripted_verdict)
    client = TestClient(create_app(source, XlsxSandbox(source, tmp_path / "corrected"), models, InMemorySaver(), UsageCap(per_visitor=10, total=100)))

    body = client.post("/investigations", json={"spreadsheet_id": "demo"}).json()
    sheet = client.get(f"/investigations/{body['id']}/sheet").json()

    assert sheet["sheet"] == "P&L"
    assert sheet["header_row"] == 3
    assert [c["header"] for c in sheet["columns"]] == ["2025A", "2026E", "2027E"]
    assert [c["letter"] for c in sheet["columns"]] == ["F", "G", "H"]
    opex = next(row for row in sheet["rows"] if row["label"] == "Opex")
    assert opex["row"] == 7
    assert [cell["ref"] for cell in opex["cells"]] == ["P&L!F7", "P&L!G7", "P&L!H7"]
    assert opex["cells"][2] == {"ref": "P&L!H7", "value": -45.2, "formula": None}
    assert opex["cells"][1]["formula"] == "=F7*(1+Assumptions!$C$7)"
    assert client.get("/investigations/nope/sheet").status_code == 404


def test_the_vercel_entrypoint_writes_only_to_the_temp_folder_and_serves_the_built_frontend(demo_workbook_path: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import runpy
    import tempfile

    project = tmp_path / "project"
    (project / "demo_models").mkdir(parents=True)
    shutil.copy(demo_workbook_path, project / "demo_models" / "demo.xlsx")
    (project / "frontend" / "dist").mkdir(parents=True)
    (project / "frontend" / "dist" / "index.html").write_text("<!doctype html><title>Model X-Ray</title>")
    scratch = tmp_path / "tmp"
    scratch.mkdir()
    for name in ("MODEL_X_RAY_MODELS_DIR", "MODEL_X_RAY_OUTPUT_DIR", "MODEL_X_RAY_UPLOAD_DIR", "MODEL_X_RAY_CHECKPOINTS", "MODEL_X_RAY_MEMORY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("NEBIUS_API_KEY", "test-key")
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))
    monkeypatch.chdir(project)
    project.chmod(0o555)
    try:
        client = TestClient(runpy.run_path(str(Path(__file__).parents[1] / "app.py"))["app"])

        assert client.get("/spreadsheets").json() == [{"id": "demo", "sheets": ["P&L", "Assumptions"]}]
        uploaded = client.post("/spreadsheets", params={"name": "My model.xlsx"}, content=demo_workbook_path.read_bytes())
        assert uploaded.status_code == 201, uploaded.text
        page = client.get("/", headers={"Accept": "text/html"})
        assert page.status_code == 200
        assert "<title>Model X-Ray</title>" in page.text
    finally:
        project.chmod(0o755)

    written = {path.name for path in (scratch / "model-x-ray").rglob("*")}
    assert {"checkpoints.db", "memory.db", "uploads"} <= written
    assert f"{uploaded.json()['id']}.xlsx" in written


def test_vercel_sends_every_api_route_to_the_api_service_and_everything_else_to_the_page(demo_workbook_path: Path, scripted_verdict) -> None:
    import json
    import re

    config = json.loads((Path(__file__).parents[1] / "vercel.json").read_text())
    api_rule, page_rule = config["rewrites"]
    assert api_rule["destination"] == {"service": "api"}
    assert page_rule == {"source": "/(.*)", "destination": {"service": "web"}}
    routed = set(re.fullmatch(r"/:prefix\((.+)\)/:path\*", api_rule["source"]).group(1).split("|"))

    source = XlsxSource({"demo": demo_workbook_path})
    app = create_app(source, XlsxSandbox(source, demo_workbook_path.parent / "corrected"), AgentModels(llm=scripted_verdict), InMemorySaver(), UsageCap(per_visitor=1, total=1))
    prefixes = {route.path.strip("/").split("/")[0] for route in app.routes if route.path.strip("/")}

    assert prefixes - {"redoc"} <= routed, "a route Vercel does not send to the API would be answered by the page"
    assert {"health", "spreadsheets", "investigations"} <= routed


def test_a_check_ends_with_time_to_spare_before_vercel_cuts_the_request() -> None:
    import json

    from model_x_ray.agents.investigator import CHECK_SECONDS

    config = json.loads((Path(__file__).parents[1] / "vercel.json").read_text())
    limit = config["services"]["api"]["functions"]["app.py"]["maxDuration"]
    measured_tail = 42
    assert CHECK_SECONDS + measured_tail + 45 <= limit, "the check, the steps after it (42 s measured on 27 Oct) and a margin for a slow start must fit in one request"

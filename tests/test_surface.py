from pathlib import Path

from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver
from test_investigator import ScriptedDiagnosis

from model_x_ray.api import AgentModels, UsageCap, create_app
from model_x_ray.spreadsheet.source import XlsxSource

QUESTION = {"spreadsheet_id": "demo", "question": "Why did EBITDA 2027 jump on the P&L sheet?"}


def clients(demo_workbook_path: Path, engine_sandbox, scripted_verdict) -> tuple[TestClient, TestClient]:
    models = AgentModels(llm=ScriptedDiagnosis(turns=[(["P&L!H7"], "P&L!H7")]), verifier=scripted_verdict)
    source = XlsxSource({"demo": demo_workbook_path})
    local = create_app(source, engine_sandbox, models, InMemorySaver(), UsageCap(per_visitor=10, total=100))
    deployed = create_app(source, engine_sandbox, models, InMemorySaver(), UsageCap(per_visitor=10, total=100), public=True)
    return TestClient(local), TestClient(deployed)


def test_the_deployment_does_not_publish_its_api_reference_while_local_development_keeps_it(demo_workbook_path: Path, engine_sandbox, scripted_verdict) -> None:
    local, deployed = clients(demo_workbook_path, engine_sandbox, scripted_verdict)

    for path in ("/docs", "/redoc", "/openapi.json"):
        assert local.get(path).status_code == 200, path
        assert deployed.get(path).status_code == 404, path


def test_a_check_from_the_page_is_served_and_a_script_without_an_origin_is_refused(demo_workbook_path: Path, engine_sandbox, scripted_verdict) -> None:
    _, deployed = clients(demo_workbook_path, engine_sandbox, scripted_verdict)
    from_the_page = {"Origin": "http://testserver", "Referer": "http://testserver/"}

    served = deployed.post("/investigations", json=QUESTION, headers=from_the_page)
    assert served.status_code == 201, served.text

    scripted = deployed.post("/investigations", json=QUESTION)
    assert scripted.status_code == 403
    assert scripted.json()["code"] == "same_origin_required"

    foreign = deployed.post("/investigations", json=QUESTION, headers={"Origin": "https://spreadsheets.example"})
    assert foreign.status_code == 403
    assert foreign.json()["code"] == "same_origin_required"


def test_resuming_and_asking_are_gated_too_while_the_page_can_still_read_the_sheet(demo_workbook_path: Path, engine_sandbox, scripted_verdict) -> None:
    _, deployed = clients(demo_workbook_path, engine_sandbox, scripted_verdict)
    from_the_page = {"Origin": "http://testserver"}

    started = deployed.post("/investigations", json=QUESTION, headers=from_the_page).json()
    investigation_id = started["id"]

    assert deployed.post(f"/investigations/{investigation_id}/resume", json={"action": "approve"}).status_code == 403
    assert deployed.post(f"/investigations/{investigation_id}/ask", json={"question": "Why?", "state": started}).status_code == 403
    assert deployed.post(f"/investigations/{investigation_id}/resume", json={"action": "reject", "reason": "not convinced"}, headers=from_the_page).status_code == 200
    assert deployed.get(f"/investigations/{investigation_id}").status_code == 200
    assert deployed.get("/spreadsheets").status_code == 200


def test_the_page_is_recognised_by_its_host_name_whatever_the_port_and_scheme(demo_workbook_path: Path, engine_sandbox, scripted_verdict) -> None:
    models = AgentModels(llm=ScriptedDiagnosis(turns=[(["P&L!H7"], "P&L!H7")]), verifier=scripted_verdict)
    source = XlsxSource({"demo": demo_workbook_path})
    deployed = create_app(source, engine_sandbox, models, InMemorySaver(), UsageCap(per_visitor=10, total=100), allowed_origins=["https://model-x-ray.vercel.app"], public=True)
    client = TestClient(deployed)

    assert client.post("/investigations", json=QUESTION, headers={"Origin": "https://testserver:8443"}).status_code == 201
    assert client.post("/investigations", json=QUESTION, headers={"Origin": "https://model-x-ray.vercel.app"}).status_code == 201
    assert client.post("/investigations", json=QUESTION, headers={"Referer": "https://model-x-ray.vercel.app/check"}).status_code == 201
    assert client.post("/investigations", json=QUESTION, headers={"Origin": "https://someone-else.vercel.app"}).status_code == 403

from pathlib import Path

import openpyxl
from conftest import ScriptedAnswer
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore
from test_investigator import ScriptedDiagnosis

from model_x_ray.api import AgentModels, UsageCap, create_app
from model_x_ray.memory import sqlite_store
from model_x_ray.spreadsheet.source import XlsxSource

QUESTION = {"spreadsheet_id": "demo", "question": "Why did EBITDA 2027 jump on the P&L sheet?"}
DEMO_MAP = {
    "rows": [{"label": "Revenue", "kind": "revenue"}, {"label": "Opex", "kind": "cost"}, {"label": "EBITDA", "kind": "subtotal"}],
    "columns": [{"period": "2025A", "kind": "actual"}, {"period": "2026E", "kind": "forecast"}, {"period": "2027E", "kind": "forecast"}],
}


def client_for(path: Path, engine_sandbox, scripted_verdict, store, investigator: ScriptedDiagnosis | None = None, mapper=None) -> TestClient:
    models = AgentModels(llm=investigator or ScriptedDiagnosis(turns=[(["P&L!H7"], "P&L!H7")]), verifier=scripted_verdict, mapper=mapper)
    return TestClient(create_app(XlsxSource({"demo": path}), engine_sandbox, models, InMemorySaver(), UsageCap(per_visitor=50, total=100), store=store))


def test_a_cell_marked_intentional_is_never_flagged_again_until_it_changes(demo_workbook_path: Path, engine_sandbox, scripted_verdict, tmp_path: Path) -> None:
    store = InMemoryStore()
    investigator = ScriptedDiagnosis(turns=[(["P&L!H7"], "P&L!H7")])
    client = client_for(demo_workbook_path, engine_sandbox, scripted_verdict, store, investigator)

    first = client.post("/investigations", json=QUESTION).json()
    assert first["hypotheses"][0]["cell"] == "P&L!H7"
    client.post(f"/investigations/{first['id']}/resume", json={"action": "reject", "reason": "Opex frozen per budget meeting", "intentional": True})

    second = client.post("/investigations", json=QUESTION).json()
    assert second["known_overrides"] == [{"cell": "P&L!H7", "content": "-45.2", "reason": "Opex frozen per budget meeting"}]
    assert "Marked intentional by a reviewer, do not propose: P&L!H7 (Opex frozen per budget meeting)" in investigator.briefs[-1]
    assert second["hypotheses"] == []
    assert second["report"].startswith("No error found.")

    changed = tmp_path / "changed.xlsx"
    book = openpyxl.load_workbook(demo_workbook_path)
    book["P&L"]["H7"] = -46.0
    book.save(changed)
    after_edit = client_for(changed, engine_sandbox, scripted_verdict, store).post("/investigations", json=QUESTION).json()
    assert after_edit["known_overrides"] == []
    assert after_edit["hypotheses"][0]["cell"] == "P&L!H7"


def test_a_plain_rejection_and_an_approval_are_remembered_differently(demo_workbook_path: Path, engine_sandbox, scripted_verdict) -> None:
    store = InMemoryStore()
    investigator = ScriptedDiagnosis(turns=[(["P&L!H7"], "P&L!H7")])
    client = client_for(demo_workbook_path, engine_sandbox, scripted_verdict, store, investigator)

    rejected = client.post("/investigations", json=QUESTION).json()
    client.post(f"/investigations/{rejected['id']}/resume", json={"action": "reject", "reason": "not convinced"})
    approved = client.post("/investigations", json=QUESTION).json()
    assert approved["known_overrides"] == []
    client.post(f"/investigations/{approved['id']}/resume", json={"action": "approve", "reason": "typed opex"})

    third = client.post("/investigations", json=QUESTION).json()
    assert third["past_findings"] == [{"cell": "P&L!H7", "error_type": "typed_value", "old_formula": "-45.2", "new_formula": "=G7*(1+Assumptions!$C$7)"}]
    assert "Fixed before on this model: P&L!H7 typed_value, -45.2 -> =G7*(1+Assumptions!$C$7)" in investigator.briefs[-1]


def test_the_model_map_is_reused_for_the_same_revision_and_rebuilt_when_the_model_changes(demo_workbook_path: Path, engine_sandbox, scripted_verdict, tmp_path: Path) -> None:
    store = sqlite_store(str(tmp_path / "memory.db"))
    mapper = ScriptedAnswer(tool="ModelMapAnswer", answer=DEMO_MAP)

    for _ in range(2):
        body = client_for(demo_workbook_path, engine_sandbox, scripted_verdict, store, mapper=mapper).post("/investigations", json=QUESTION).json()
        assert [row["label"] for row in body["model_map"]["rows"]] == ["Revenue", "Opex", "EBITDA"]
    assert len(mapper.prompts) == 1
    assert [entry["role"] for entry in body["run_log"]].count("mapper") == 0

    changed = tmp_path / "changed.xlsx"
    book = openpyxl.load_workbook(demo_workbook_path)
    book["P&L"]["F4"] = 190.0
    book.save(changed)
    client_for(changed, engine_sandbox, scripted_verdict, sqlite_store(str(tmp_path / "memory.db")), mapper=mapper).post("/investigations", json=QUESTION)
    assert len(mapper.prompts) == 2

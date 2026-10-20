import re
from pathlib import Path

from test_api import client_for

API_TS = Path(__file__).resolve().parents[1] / "frontend" / "src" / "api.ts"


def required_view_fields() -> set[str]:
    block = API_TS.read_text().split("export type InvestigationView = {", 1)[1].split("\n};", 1)[0]
    return {match.group(1) for line in block.splitlines() if (match := re.match(r"\s*(\w+)(\??):", line)) and match.group(2) != "?"}


def test_every_field_the_page_requires_arrives_with_the_view(demo_workbook_path, engine_sandbox, scripted_verdict) -> None:
    client = client_for(demo_workbook_path, engine_sandbox, scripted_verdict)
    required = required_view_fields()
    assert {"target", "report", "run_log", "tool_call_counts"} <= required

    started = client.post("/investigations", json={"spreadsheet_id": "demo", "question": "Why did EBITDA 2027 jump on the P&L sheet?"})
    assert started.status_code == 201
    paused = started.json()
    assert required <= set(paused), sorted(required - set(paused))

    done = client.post(f"/investigations/{paused['id']}/resume", json={"action": "approve", "reason": "the typed opex is the error"})
    assert done.status_code == 200
    assert required <= set(done.json()), sorted(required - set(done.json()))

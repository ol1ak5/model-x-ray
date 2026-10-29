import json
from pathlib import Path
from typing import Any

import httpx
import openpyxl
import openai
from fastapi.testclient import TestClient
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langchain_core.outputs import ChatResult
from langgraph.checkpoint.memory import InMemorySaver
from test_api import client_for

from model_x_ray.api import AgentModels, UsageCap, create_app
from model_x_ray.spreadsheet.source import XlsxSource

QUESTION = {"spreadsheet_id": "demo", "question": "Why did EBITDA 2027 jump on the P&L sheet?"}


class BrokenModel(BaseChatModel):
    error: Any = None

    @property
    def _llm_type(self) -> str:
        return "broken"

    def bind_tools(self, tools: Any, **kwargs: Any) -> "BrokenModel":
        return self

    def _generate(self, messages: list[BaseMessage], stop: list[str] | None = None, **kwargs: Any) -> ChatResult:
        raise self.error


def events(response: httpx.Response) -> list[tuple[str, dict]]:
    parsed = []
    for block in response.text.strip().split("\n\n"):
        fields = dict(line.split(": ", 1) for line in block.splitlines())
        parsed.append((fields["event"], json.loads(fields["data"])))
    return parsed


def broken_client(demo_workbook_path: Path, engine_sandbox, error: Exception) -> TestClient:
    models = AgentModels(llm=BrokenModel(error=error))
    app = create_app(XlsxSource({"demo": demo_workbook_path}), engine_sandbox, models, InMemorySaver(), UsageCap(per_visitor=10, total=100))
    return TestClient(app, raise_server_exceptions=False)


def test_the_stream_reports_every_step_then_the_view_and_resumes_the_same_way(demo_workbook_path: Path, engine_sandbox, scripted_verdict) -> None:
    client = client_for(demo_workbook_path, engine_sandbox, scripted_verdict)

    started = client.post("/investigations/stream", json=QUESTION)
    assert started.headers["content-type"].startswith("text/event-stream")
    stream = events(started)

    steps = [data["step"] for kind, data in stream if kind == "step"]
    assert steps == ["load_sheet", "map_model", "locate", "trace", "diagnose", "test", "verify", "explain"]
    assert stream[2][1]["label"] == "Finding the cell"
    kind, view = stream[-1]
    assert kind == "view"
    assert view["status"] == "needs_review"
    assert "Root cause found in P&L!H7" in view["report"]

    resumed = events(client.post(f"/investigations/{view['id']}/resume/stream", json={"action": "approve", "reason": "typed opex"}))
    assert [data["step"] for kind, data in resumed if kind == "step"] == ["human_review", "apply_fix"]
    assert resumed[-1][1]["status"] == "done"
    assert resumed[-1][1]["corrected_copy_id"] == "corrected:demo"


def test_an_ai_service_timeout_gives_a_short_message_instead_of_a_traceback(demo_workbook_path: Path, engine_sandbox) -> None:
    timeout = openai.APITimeoutError(request=httpx.Request("POST", "https://api.tokenfactory.nebius.com/v1/chat/completions"))
    client = broken_client(demo_workbook_path, engine_sandbox, timeout)

    plain = client.post("/investigations", json=QUESTION)
    assert plain.status_code == 503
    assert plain.json() == {"detail": "The AI service took too long to answer. Please try again in a minute.", "code": "provider_timeout"}

    stream = events(client.post("/investigations/stream", json=QUESTION))
    assert [data["step"] for kind, data in stream if kind == "step"] == ["load_sheet", "map_model", "locate", "trace"]
    assert stream[-1] == ("error", {"status": 503, "code": "provider_timeout", "detail": "The AI service took too long to answer. Please try again in a minute."})


def test_a_formula_we_cannot_calculate_and_an_unexpected_crash_both_get_clear_messages(demo_workbook_path: Path, engine_sandbox, scripted_verdict, tmp_path: Path) -> None:
    book = openpyxl.load_workbook(demo_workbook_path)
    book["P&L"]["H4"] = '=INDIRECT("G4")*1.08'
    book.save(tmp_path / "indirect.xlsx")
    models = AgentModels(llm=BrokenModel(error=RuntimeError("boom")), verifier=scripted_verdict)
    app = create_app(XlsxSource({"demo": tmp_path / "indirect.xlsx"}), engine_sandbox, models, InMemorySaver(), UsageCap(per_visitor=10, total=100))
    unsupported = TestClient(app, raise_server_exceptions=False).post("/investigations", json=QUESTION)
    assert unsupported.status_code == 422
    assert unsupported.json()["code"] == "unsupported_formula"
    assert unsupported.json()["detail"].startswith("This model uses a formula Model X-Ray cannot calculate yet: Unsupported function INDIRECT in P&L!H4")

    crash = broken_client(demo_workbook_path, engine_sandbox, RuntimeError("boom at line 42")).post("/investigations", json=QUESTION)
    assert crash.status_code == 500
    assert crash.json() == {"detail": "Something went wrong during the investigation. The team has the details; please try again.", "code": "unexpected"}
    assert "boom" not in crash.text

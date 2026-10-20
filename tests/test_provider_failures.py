from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.checkpoint.memory import InMemorySaver

from conftest import ScriptedDiagnosis

from model_x_ray.api import AgentModels, UsageCap, create_app
from model_x_ray.spreadsheet.source import XlsxSource

PROVIDER_ERROR = "[ERROR: Agent failed (Function process_single_item_agent timed out after 90.0 seconds), API failed (API request returned None after all retries)]"


class FlakyInvestigator(ScriptedDiagnosis):
    failures_left: list[int] = [0]

    def bind_tools(self, tools: Any, **kwargs: Any) -> "FlakyInvestigator":
        return self.model_copy(update={"bound": [getattr(t, "name", None) or getattr(t, "__name__", "") for t in tools], "briefs": self.briefs, "failures_left": self.failures_left})

    def _generate(self, messages: list[BaseMessage], stop: list[str] | None = None, **kwargs: Any) -> ChatResult:
        if "Diagnosis" not in self.bound and self.failures_left[0] > 0:
            self.failures_left[0] -= 1
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content=PROVIDER_ERROR))])
        return super()._generate(messages, stop, **kwargs)


def client_with(investigator: BaseChatModel, demo_workbook_path: Path, engine_sandbox, scripted_verdict) -> TestClient:
    models = AgentModels(llm=investigator, verifier=scripted_verdict, locator=None)
    return TestClient(create_app(XlsxSource({"demo": demo_workbook_path}), engine_sandbox, models, InMemorySaver(), UsageCap(per_visitor=10, total=100)), raise_server_exceptions=False)


def test_a_provider_error_returned_as_the_answer_is_retried_and_the_investigation_still_finds_the_error(demo_workbook_path: Path, engine_sandbox, scripted_verdict) -> None:
    investigator = FlakyInvestigator(briefs=[], failures_left=[1], turns=[(["P&L!H7"], "P&L!H7")])
    client = client_with(investigator, demo_workbook_path, engine_sandbox, scripted_verdict)

    response = client.post("/investigations", json={"spreadsheet_id": "demo", "question": "Why did EBITDA 2027 jump?"})

    assert response.status_code == 201
    assert response.json()["patch"]["cell"] == "P&L!H7"
    assert investigator.failures_left == [0]


def test_a_provider_that_keeps_failing_is_reported_as_a_service_failure_never_as_a_clean_model(demo_workbook_path: Path, engine_sandbox, scripted_verdict) -> None:
    investigator = FlakyInvestigator(briefs=[], failures_left=[99], turns=[(["P&L!H7"], "P&L!H7")])
    client = client_with(investigator, demo_workbook_path, engine_sandbox, scripted_verdict)

    response = client.post("/investigations", json={"spreadsheet_id": "demo", "question": "Why did EBITDA 2027 jump?"})

    assert response.status_code == 503
    assert "AI service" in response.json()["detail"]
    assert "No error found" not in response.text

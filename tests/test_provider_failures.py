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


class SilentOnce(ScriptedDiagnosis):
    silences_left: list[int] = [0]

    def bind_tools(self, tools: Any, **kwargs: Any) -> "SilentOnce":
        return self.model_copy(update={"bound": [getattr(t, "name", None) or getattr(t, "__name__", "") for t in tools], "briefs": self.briefs, "silences_left": self.silences_left})

    def _generate(self, messages: list[BaseMessage], stop: list[str] | None = None, **kwargs: Any) -> ChatResult:
        if "Diagnosis" in self.bound and self.silences_left[0] > 0:
            self.silences_left[0] -= 1
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content="Let me reason about every line once more before answering..."))])
        return super()._generate(messages, stop, **kwargs)


def test_a_diagnosis_the_model_writes_as_text_instead_of_through_the_tool_is_asked_again(demo_workbook_path: Path, engine_sandbox, scripted_verdict) -> None:
    investigator = SilentOnce(briefs=[], silences_left=[1], turns=[(["P&L!H7"], "P&L!H7")])
    client = client_with(investigator, demo_workbook_path, engine_sandbox, scripted_verdict)

    response = client.post("/investigations", json={"spreadsheet_id": "demo", "question": "Why did EBITDA 2027 jump?"})

    assert response.status_code == 201
    assert response.json()["patch"]["cell"] == "P&L!H7"
    assert investigator.silences_left == [0]


def test_a_model_that_never_returns_its_conclusion_is_asked_only_once_more_so_the_check_stays_short(demo_workbook_path: Path, engine_sandbox, scripted_verdict) -> None:
    investigator = SilentOnce(briefs=[], silences_left=[99], turns=[(["P&L!H7"], "P&L!H7")])
    client = client_with(investigator, demo_workbook_path, engine_sandbox, scripted_verdict)

    response = client.post("/investigations", json={"spreadsheet_id": "demo", "question": "Why did EBITDA 2027 jump?"})

    assert response.status_code == 201
    asked = 99 - investigator.silences_left[0]
    assert asked % 2 == 0 and asked <= 2 * 3, f"each review asked for its conclusion {asked} times in total; two per review is the limit"
    assert response.json()["patch"] is None


class Curious(ScriptedDiagnosis):
    thoughts: list[int] = [0]

    def bind_tools(self, tools: Any, **kwargs: Any) -> "Curious":
        return self.model_copy(update={"bound": [getattr(t, "name", None) or getattr(t, "__name__", "") for t in tools], "briefs": self.briefs, "thoughts": self.thoughts})

    def _generate(self, messages: list[BaseMessage], stop: list[str] | None = None, **kwargs: Any) -> ChatResult:
        if "Diagnosis" not in self.bound:
            self.thoughts[0] += 1
            call = {"name": "get_cell", "args": {"ref": "P&L!H7"}, "id": f"look-{self.thoughts[0]}"}
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content="", tool_calls=[call]))])
        return super()._generate(messages, stop, **kwargs)


def test_a_review_that_keeps_asking_for_tools_concludes_once_its_time_is_up(demo_workbook_path: Path, engine_sandbox, scripted_verdict, monkeypatch) -> None:
    import itertools

    import model_x_ray.agents.investigator as investigator_module

    ticks = itertools.count(0.0, investigator_module.REVIEW_SECONDS / 2)
    monkeypatch.setattr(investigator_module, "clock", lambda: next(ticks))
    investigator = Curious(briefs=[], thoughts=[0], turns=[(["P&L!H7"], "P&L!H7")])
    client = client_with(investigator, demo_workbook_path, engine_sandbox, scripted_verdict)

    response = client.post("/investigations", json={"spreadsheet_id": "demo", "question": "Why did EBITDA 2027 jump?"})

    assert response.status_code == 201, response.text
    assert investigator.thoughts[0] <= 3, f"the review kept consulting {investigator.thoughts[0]} times after its time was up"
    assert response.json()["patch"]["cell"] == "P&L!H7", "the conclusion still comes, from what the review saw"

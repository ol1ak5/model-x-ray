import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from conftest import ScriptedDiagnosis
from fastapi.testclient import TestClient
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.checkpoint.memory import InMemorySaver

from model_x_ray.api import AgentModels, UsageCap, create_app
from model_x_ray.spreadsheet.source import XlsxSource

QUESTION = {"spreadsheet_id": "demo", "question": "Why did EBITDA 2027 jump on the P&L sheet?"}


class ScriptedReply(BaseChatModel):
    replies: list[str] = []
    seen: list[list[BaseMessage]] = []

    @property
    def _llm_type(self) -> str:
        return "scripted-reply"

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> "ScriptedReply":
        return self

    def _generate(self, messages: list[BaseMessage], stop: list[str] | None = None, **kwargs: Any) -> ChatResult:
        self.seen.append(messages)
        text = self.replies[min(len(self.seen), len(self.replies)) - 1]
        usage = {"input_tokens": 900, "output_tokens": 60, "total_tokens": 960}
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=text, usage_metadata=usage))])


def app_with(demo_workbook_path: Path, engine_sandbox, verdict, chat: ScriptedReply, ask_cap: UsageCap | None = None) -> TestClient:
    models = AgentModels(llm=ScriptedDiagnosis(turns=[(["P&L!H7"], "P&L!H7")]), verifier=verdict, explainer=chat)
    return TestClient(create_app(XlsxSource({"demo": demo_workbook_path}), engine_sandbox, models, InMemorySaver(), UsageCap(per_visitor=10, total=100), ask_cap=ask_cap))


def paused_view(client: TestClient) -> dict:
    view = client.post("/investigations", json=QUESTION).json()
    assert view["status"] == "needs_review"
    return json.loads(json.dumps(view))


def test_the_reviewer_asks_about_the_fix_and_the_agent_answers_from_the_run_it_made(demo_workbook_path: Path, engine_sandbox, scripted_verdict) -> None:
    chat = ScriptedReply(replies=["H7 is typed as -45.2 while every other Opex year grows the year before by 5%.", "**Yes.** The copy tested it; EBITDA 2027 went 52.01 -> 44.73 — in line with 2026."])
    started = app_with(demo_workbook_path, engine_sandbox, scripted_verdict, ScriptedReply(replies=["unused"]))
    view = paused_view(started)
    elsewhere = app_with(demo_workbook_path, engine_sandbox, scripted_verdict, chat)

    first = elsewhere.post(f"/investigations/{view['id']}/ask", json={"question": "Why is H7 wrong?", "state": view})

    assert first.status_code == 200, first.text
    assert first.json()["answer"] == "H7 is typed as -45.2 while every other Opex year grows the year before by 5%."
    brief = chat.seen[0][-1].content
    assert "P&L!H7" in brief and "-45.2" in brief and "=G7*(1+Assumptions!$C$7)" in brief, "the agent answers from the cell, its content and the tested fix"
    assert view["report"].split(" (")[0] in brief, "the report the reviewer read is part of what the agent knows"
    assert brief.rstrip().endswith("Why is H7 wrong?")
    assert "->" not in brief
    assert "P&L!H8 (EBITDA 2027E) from" in brief, "the cells the fix changes are named by their line and period, so the agent can talk about EBITDA"

    history = [{"role": "user", "text": "Why is H7 wrong?"}, {"role": "agent", "text": first.json()["answer"]}]
    second = elsewhere.post(f"/investigations/{view['id']}/ask", json={"question": "Was the fix tested?", "state": view, "history": history})

    assert second.json()["answer"] == "Yes. The copy tested it. EBITDA 2027 went 52.01 to 44.73, in line with 2026.", "the page shows plain sentences: no markdown, semicolons, dashes or arrows"
    follow_up = chat.seen[1][-1].content
    assert follow_up.index("Why is H7 wrong?") < follow_up.index("every other Opex year") < follow_up.index("Was the fix tested?")


def test_questions_need_the_run_state_and_a_question_and_have_their_own_daily_limit(demo_workbook_path: Path, engine_sandbox, scripted_verdict) -> None:
    chat = ScriptedReply(replies=["An answer."])
    client = app_with(demo_workbook_path, engine_sandbox, scripted_verdict, chat, ask_cap=UsageCap(per_visitor=2, total=10, noun="questions"))
    view = paused_view(client)
    calls = len(chat.seen)

    assert client.post(f"/investigations/{view['id']}/ask", json={"question": "Why?"}).status_code == 400
    assert client.post(f"/investigations/{view['id']}/ask", json={"question": "   ", "state": view}).status_code == 400
    assert client.post(f"/investigations/{view['id']}/ask", json={"question": "x" * 2000, "state": view}).status_code == 400
    assert len(chat.seen) == calls, "nothing reaches the model before the request is valid"

    for _ in range(2):
        assert client.post(f"/investigations/{view['id']}/ask", json={"question": "Why?", "state": view}).status_code == 200
    limited = client.post(f"/investigations/{view['id']}/ask", json={"question": "Why?", "state": view})
    assert limited.status_code == 429
    assert "questions" in limited.json()["detail"]
    assert client.post("/investigations", json=QUESTION).status_code == 201, "questions do not use up the visitor's checks"

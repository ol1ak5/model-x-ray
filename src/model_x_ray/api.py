from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from langchain_core.language_models import BaseChatModel
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command
from pydantic import BaseModel

from model_x_ray.graph import run_investigation
from model_x_ray.spreadsheet.sandbox import SandboxWithWrite
from model_x_ray.spreadsheet.source import SpreadsheetSource

PUBLIC_FIELDS = ("question", "target", "causal_tree", "hypotheses", "evidence", "verifications", "patch", "report", "corrected_copy_id", "run_log")


@dataclass
class AgentModels:
    llm: BaseChatModel
    verifier: BaseChatModel | None = None
    locator: BaseChatModel | None = None
    mapper: BaseChatModel | None = None


@dataclass
class UsageCap:
    per_visitor: int
    total: int
    day: date = field(default_factory=date.today)
    counts: dict[str, int] = field(default_factory=dict)

    def check(self, visitor: str) -> None:
        if self.day != date.today():
            self.day, self.counts = date.today(), {}
        if self.counts.get(visitor, 0) >= self.per_visitor:
            raise HTTPException(429, f"Daily limit of {self.per_visitor} investigations per visitor reached; try again tomorrow")
        if sum(self.counts.values()) >= self.total:
            raise HTTPException(429, f"The demo's daily limit of {self.total} investigations is reached; try again tomorrow")

    def record(self, visitor: str) -> None:
        self.counts[visitor] = self.counts.get(visitor, 0) + 1


class StartRequest(BaseModel):
    spreadsheet_id: str
    question: str


class ResumeRequest(BaseModel):
    ref: str | None = None
    action: Literal["approve", "edit", "reject"] | None = None
    reason: str = ""
    patch: dict[str, Any] | None = None


def investigation_view(graph: CompiledStateGraph, investigation_id: str) -> dict:
    snapshot = graph.get_state({"configurable": {"thread_id": investigation_id}})
    pauses = [interrupt.value for task in snapshot.tasks for interrupt in task.interrupts]
    if "choose_target" in snapshot.next:
        status = "needs_cell"
    elif "human_review" in snapshot.next:
        status = "needs_review"
    else:
        status = "done"
    values = snapshot.values
    return {"id": investigation_id, "status": status, "pause": pauses[0] if pauses else None, **{name: values.get(name) for name in PUBLIC_FIELDS}}


def create_app(source: SpreadsheetSource, sandbox: SandboxWithWrite, models: AgentModels, checkpointer: BaseCheckpointSaver, cap: UsageCap) -> FastAPI:
    app = FastAPI(title="Model X-Ray")
    graphs: dict[str, CompiledStateGraph] = {}

    def build(spreadsheet_id: str) -> CompiledStateGraph:
        try:
            return run_investigation(models.llm, spreadsheet_id, source, sandbox, checkpointer, verifier=models.verifier, locator=models.locator, mapper=models.mapper)
        except ValueError as error:
            raise HTTPException(400, str(error)) from error

    def graph_of(investigation_id: str) -> CompiledStateGraph:
        if investigation_id not in graphs:
            raise HTTPException(404, f"No investigation {investigation_id!r}")
        return graphs[investigation_id]

    @app.post("/investigations", status_code=201)
    def start(request: StartRequest, http: Request) -> dict:
        visitor = http.client.host if http.client else "unknown"
        cap.check(visitor)
        graph = build(request.spreadsheet_id)
        investigation_id = uuid4().hex
        graph.invoke({"spreadsheet_id": request.spreadsheet_id, "question": request.question}, {"configurable": {"thread_id": investigation_id}})
        graphs[investigation_id] = graph
        cap.record(visitor)
        return investigation_view(graph, investigation_id)

    @app.get("/investigations/{investigation_id}")
    def read(investigation_id: str) -> dict:
        return investigation_view(graph_of(investigation_id), investigation_id)

    @app.post("/investigations/{investigation_id}/resume")
    def resume(investigation_id: str, request: ResumeRequest) -> dict:
        graph = graph_of(investigation_id)
        if investigation_view(graph, investigation_id)["status"] == "done":
            raise HTTPException(409, "This investigation is finished and cannot be resumed")
        graph.invoke(Command(resume=request.model_dump(exclude_none=True)), {"configurable": {"thread_id": investigation_id}})
        return investigation_view(graph, investigation_id)

    return app

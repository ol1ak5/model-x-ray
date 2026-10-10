import json
import logging
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal
from uuid import uuid4

import openai
import pydantic
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from langchain_core.language_models import BaseChatModel
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command
from pydantic import BaseModel

from model_x_ray.graph import run_investigation
from model_x_ray.spreadsheet.engine import FormulaError, UnsupportedFormulaError
from model_x_ray.spreadsheet.sandbox import SandboxWithWrite
from model_x_ray.spreadsheet.source import SpreadsheetSource

logger = logging.getLogger("model_x_ray.api")

STEP_LABELS = {
    "load_sheet": "Reading the workbook",
    "map_model": "Understanding the model's layout",
    "locate": "Finding the cell",
    "trace": "Tracing the formulas",
    "diagnose": "Looking for the root cause",
    "test": "Testing the fix",
    "verify": "Verifying the fix",
    "explain": "Writing the explanation",
    "human_review": "Saving the decision",
    "apply_fix": "Saving a new version",
}

GENERIC_FAILURE = "Something went wrong during the investigation. The team has the details; please try again."

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


def friendly_error(error: Exception) -> tuple[int, str]:
    if isinstance(error, HTTPException):
        return error.status_code, str(error.detail)
    if isinstance(error, openai.APITimeoutError):
        return 503, "The AI service took too long to answer. Please try again in a minute."
    if isinstance(error, openai.RateLimitError):
        return 503, "The AI service is busy right now. Please try again in a minute."
    if isinstance(error, openai.AuthenticationError):
        return 503, "The AI service rejected our access key. Please tell the team."
    if isinstance(error, openai.APIConnectionError):
        return 503, "The AI service could not be reached. Please try again in a minute."
    if isinstance(error, openai.APIStatusError):
        return 502, "The AI service returned an error. Please try again."
    if isinstance(error, pydantic.ValidationError):
        return 502, "The AI answered in an unexpected format. Please try again."
    if isinstance(error, UnsupportedFormulaError):
        return 422, f"This model uses a formula Model X-Ray cannot calculate yet: {error}"
    if isinstance(error, FormulaError):
        return 422, f"This model has a formula problem Model X-Ray cannot work around: {error}"
    if isinstance(error, ValueError):
        return 400, str(error)
    logger.exception("Investigation failed", exc_info=error)
    return 500, GENERIC_FAILURE


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def investigation_view(graph: CompiledStateGraph, investigation_id: str) -> dict:
    snapshot = graph.get_state({"configurable": {"thread_id": investigation_id}})
    pauses = [interrupt.value for task in snapshot.tasks for interrupt in task.interrupts]
    if "locate" in snapshot.next:
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

    @app.exception_handler(Exception)
    def explain_failure(request: Request, error: Exception) -> JSONResponse:
        status, detail = friendly_error(error)
        return JSONResponse({"detail": detail}, status_code=status)

    def progress(graph: CompiledStateGraph, graph_input: Any, investigation_id: str) -> Iterator[str]:
        try:
            for update in graph.stream(graph_input, {"configurable": {"thread_id": investigation_id}}, stream_mode="updates"):
                for step in update:
                    if step in STEP_LABELS:
                        yield sse("step", {"step": step, "label": STEP_LABELS[step]})
            yield sse("view", investigation_view(graph, investigation_id))
        except Exception as error:
            status, detail = friendly_error(error)
            yield sse("error", {"status": status, "detail": detail})

    def build(spreadsheet_id: str) -> CompiledStateGraph:
        try:
            return run_investigation(models.llm, spreadsheet_id, source, sandbox, checkpointer, verifier=models.verifier, locator=models.locator, mapper=models.mapper)
        except ValueError as error:
            raise HTTPException(400, str(error)) from error

    def graph_of(investigation_id: str) -> CompiledStateGraph:
        if investigation_id not in graphs:
            raise HTTPException(404, f"No investigation {investigation_id!r}")
        return graphs[investigation_id]

    def open_investigation(request: StartRequest, http: Request) -> tuple[CompiledStateGraph, str]:
        visitor = http.client.host if http.client else "unknown"
        cap.check(visitor)
        graph = build(request.spreadsheet_id)
        investigation_id = uuid4().hex
        graphs[investigation_id] = graph
        cap.record(visitor)
        return graph, investigation_id

    def paused_graph(investigation_id: str) -> CompiledStateGraph:
        graph = graph_of(investigation_id)
        if investigation_view(graph, investigation_id)["status"] == "done":
            raise HTTPException(409, "This investigation is finished and cannot be resumed")
        return graph

    @app.post("/investigations", status_code=201)
    def start(request: StartRequest, http: Request) -> dict:
        graph, investigation_id = open_investigation(request, http)
        graph.invoke({"spreadsheet_id": request.spreadsheet_id, "question": request.question}, {"configurable": {"thread_id": investigation_id}})
        return investigation_view(graph, investigation_id)

    @app.post("/investigations/stream")
    def start_stream(request: StartRequest, http: Request) -> StreamingResponse:
        graph, investigation_id = open_investigation(request, http)
        graph_input = {"spreadsheet_id": request.spreadsheet_id, "question": request.question}
        return StreamingResponse(progress(graph, graph_input, investigation_id), media_type="text/event-stream")

    @app.get("/investigations/{investigation_id}")
    def read(investigation_id: str) -> dict:
        return investigation_view(graph_of(investigation_id), investigation_id)

    @app.post("/investigations/{investigation_id}/resume")
    def resume(investigation_id: str, request: ResumeRequest) -> dict:
        graph = paused_graph(investigation_id)
        graph.invoke(Command(resume=request.model_dump(exclude_none=True)), {"configurable": {"thread_id": investigation_id}})
        return investigation_view(graph, investigation_id)

    @app.post("/investigations/{investigation_id}/resume/stream")
    def resume_stream(investigation_id: str, request: ResumeRequest) -> StreamingResponse:
        graph = paused_graph(investigation_id)
        graph_input = Command(resume=request.model_dump(exclude_none=True))
        return StreamingResponse(progress(graph, graph_input, investigation_id), media_type="text/event-stream")

    return app

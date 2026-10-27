import base64
import hashlib
import json
import logging
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

import openai
import pydantic
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from starlette.background import BackgroundTask
from langchain_core.language_models import BaseChatModel
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph.state import CompiledStateGraph
from langgraph.store.base import BaseStore
from langgraph.types import Command
from pydantic import BaseModel

from model_x_ray.agents.ask import answer_question
from model_x_ray.agents.verifier import CHECK_LABELS
from model_x_ray.graph import run_continuation, run_investigation
from model_x_ray.llm import ProviderFailure
from model_x_ray.rules import is_period_cell
from model_x_ray.spreadsheet.engine import FormulaError, UnsupportedFormulaError, Workbook, column_letters, is_number, normalize_ref, split_ref
from model_x_ray.spreadsheet.sandbox import SandboxWithWrite, check_patch, normalized_formula
from model_x_ray.spreadsheet.source import SpreadsheetSource
from model_x_ray.spreadsheet.xlsx import load_xlsx

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

MAX_UPLOAD_BYTES = 10 * 1024 * 1024

LOCAL_DEV_ORIGIN = r"http://(localhost|127\.0\.0\.1)(:\d+)?"

XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

GENERIC_FAILURE = "Something went wrong during the investigation. The team has the details; please try again."

PUBLIC_FIELDS = ("spreadsheet_id", "question", "target_choice", "decisions", "model_map", "known_overrides", "past_findings", "target", "causal_tree", "contributions", "hypotheses", "evidence", "verifications", "patch", "report", "corrected_copy_id", "run_log", "attempts", "tool_call_counts", "node_log", "human_decision")

CARRIED_LISTS = ("known_overrides", "past_findings", "contributions", "hypotheses", "evidence", "verifications", "run_log", "decisions")

CARRIED_RECORDS = ("model_map", "target", "causal_tree", "patch")


@dataclass
class AgentModels:
    llm: BaseChatModel
    verifier: BaseChatModel | None = None
    locator: BaseChatModel | None = None
    mapper: BaseChatModel | None = None
    explainer: BaseChatModel | None = None


@dataclass
class UsageCap:
    per_visitor: int
    total: int
    noun: str = "investigations"
    day: date = field(default_factory=date.today)
    counts: dict[str, int] = field(default_factory=dict)

    def check(self, visitor: str) -> None:
        if self.day != date.today():
            self.day, self.counts = date.today(), {}
        if self.counts.get(visitor, 0) >= self.per_visitor:
            raise HTTPException(429, f"Daily limit of {self.per_visitor} {self.noun} per visitor reached; try again tomorrow")
        if sum(self.counts.values()) >= self.total:
            raise HTTPException(429, f"The demo's daily limit of {self.total} {self.noun} is reached; try again tomorrow")

    def record(self, visitor: str) -> None:
        self.counts[visitor] = self.counts.get(visitor, 0) + 1


UPLOAD_TTL = 1800.0
COPY_TTL = 1800.0


@dataclass
class Uploads:
    source: SpreadsheetSource
    directory: Path | None
    ttl: float = UPLOAD_TTL
    clock: Callable[[], float] = time.monotonic

    def __post_init__(self) -> None:
        self._held: dict[str, tuple[Path, float]] = {}

    @property
    def enabled(self) -> bool:
        return self.directory is not None

    def add(self, spreadsheet_id: str, path: Path) -> None:
        self._held[spreadsheet_id] = (path, self.clock())

    def holds(self, spreadsheet_id: str) -> bool:
        return spreadsheet_id in self._held

    def drop(self, spreadsheet_id: str) -> None:
        entry = self._held.pop(spreadsheet_id, None)
        if entry is None:
            return
        self.source.remove(spreadsheet_id)
        entry[0].unlink(missing_ok=True)

    def sweep(self) -> list[str]:
        now = self.clock()
        expired = [name for name, (_, added) in self._held.items() if now - added >= self.ttl]
        for name in expired:
            self.drop(name)
        return expired


@dataclass
class Copies:
    directory: Path | None
    ttl: float = COPY_TTL

    def __post_init__(self) -> None:
        self._serving: set[Path] = set()

    def holding(self, path: Path) -> None:
        self._serving.add(path)

    def release(self, path: Path) -> None:
        self._serving.discard(path)
        path.unlink(missing_ok=True)

    def sweep(self) -> list[Path]:
        if self.directory is None or not self.directory.is_dir():
            return []
        cutoff = time.time() - self.ttl
        removed = []
        for path in self.directory.glob("*.xlsx"):
            if path in self._serving or path.stat().st_mtime > cutoff:
                continue
            path.unlink(missing_ok=True)
            removed.append(path)
        return removed


class StartRequest(BaseModel):
    spreadsheet_id: str = ""
    question: str = ""
    set_aside: list[str] = []


SET_ASIDE_REASON = "The reviewer said it is not an error"


class AskRequest(BaseModel):
    question: str = ""
    state: dict[str, Any] | None = None
    history: list[dict[str, str]] = []


MAX_QUESTION_CHARS = 500

MAX_HISTORY_TURNS = 8


class WorkbookRequest(BaseModel):
    spreadsheet_id: str = ""


class ResumeRequest(BaseModel):
    action: Literal["approve", "edit", "reject"] | None = None
    reason: str = ""
    patch: dict[str, Any] | None = None
    intentional: bool = False
    state: dict[str, Any] | None = None


def decision_of(request: ResumeRequest) -> dict[str, Any]:
    if request.action is None:
        raise HTTPException(400, "Send an action to continue the investigation")
    decision: dict[str, Any] = {"action": request.action, "reason": request.reason, "intentional": request.intentional}
    if request.patch is not None:
        decision["patch"] = request.patch
    return decision


def carried_state(raw: dict[str, Any]) -> dict[str, Any]:
    spreadsheet_id = raw.get("spreadsheet_id")
    if not isinstance(spreadsheet_id, str) or not spreadsheet_id:
        raise HTTPException(400, "The state does not say which spreadsheet it belongs to, so the investigation cannot be continued")
    if not isinstance(raw.get("question"), str):
        raise HTTPException(400, "The state does not carry the question, so the investigation cannot be continued")
    carried = {name: raw.get(name) for name in PUBLIC_FIELDS}
    for name in CARRIED_LISTS:
        if carried[name] is None:
            carried[name] = []
        elif not isinstance(carried[name], list):
            raise HTTPException(400, f"The state's {name} is not a list")
    for name in CARRIED_RECORDS:
        if carried[name] is not None and not isinstance(carried[name], dict):
            raise HTTPException(400, f"The state's {name} is not an object")
    if not isinstance(carried["attempts"], int):
        carried["attempts"] = 0
    return carried


def friendly_error(error: Exception) -> tuple[int, str]:
    if isinstance(error, HTTPException):
        return error.status_code, str(error.detail)
    if isinstance(error, ProviderFailure):
        return 503, "The AI service failed to answer (it returned an internal error). Please try again in a minute."
    if isinstance(error, openai.APITimeoutError):
        return 503, "The AI service took too long to answer. Please try again in a minute."
    if isinstance(error, openai.RateLimitError):
        return 503, "The AI service is busy right now. Please try again in a minute."
    if isinstance(error, openai.AuthenticationError):
        return 503, "The AI service rejected our access key. Please tell the team."
    if isinstance(error, openai.APIConnectionError):
        return 503, "The AI service could not be reached. Please try again in a minute."
    if isinstance(error, openai.APIStatusError) and error.status_code in (503, 529):
        return 503, "The AI service is busy right now. Please try again in a minute."
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


def checked_patch(source: SpreadsheetSource, spreadsheet_id: str, requested: dict[str, Any]) -> dict[str, str]:
    cell = str(requested.get("cell", "")).strip()
    formula = str(requested.get("new_formula", "")).strip()
    if not cell or not formula:
        raise HTTPException(422, "An edited fix needs a cell and a number or formula")
    patch = {
        "cell": cell,
        "old_formula": str(requested.get("old_formula", "")),
        "new_formula": normalized_formula(formula),
        "source": "human",
    }
    try:
        check_patch(source.load(spreadsheet_id), patch)
    except (FormulaError, UnsupportedFormulaError) as error:
        raise HTTPException(
            422,
            f"That fix does not work in {cell}: {error}. Enter a number, or a formula that starts with =.",
        ) from error
    return patch


MAX_GRID_ROWS = 40

MAX_VIEW_ROWS = 300

MAX_VIEW_COLUMNS = 40


def workbook_view(book: Workbook) -> dict:
    sheets = []
    for name in book.sheets:
        refs = [ref for ref in book.cells() if split_ref(ref)[0] == name]
        addresses = {ref: split_ref(ref)[1] for ref in refs}
        rows = min(max((address.row for address in addresses.values()), default=0), MAX_VIEW_ROWS)
        columns = min(max((address.column for address in addresses.values()), default=0), MAX_VIEW_COLUMNS)
        cells = []
        for ref, address in sorted(addresses.items(), key=lambda item: (item[1].row, item[1].column)):
            if address.row > rows or address.column > columns:
                continue
            try:
                value = book.value(ref)
            except FormulaError:
                value = "#ERROR"
            cells.append({"ref": f"{column_letters(address.column)}{address.row}", "value": value, "formula": book.formula(ref)})
        sheets.append({"name": name, "rows": rows, "columns": columns, "cells": cells})
    return {"sheets": sheets}


def sheet_window(book: Workbook, sheet: str, focus_row: int) -> dict:
    cells = [ref for ref in book.cells() if ref.startswith(f"{sheet}!") and is_period_cell(book, ref)]
    by_position = {split_ref(ref)[1].row * 100000 + split_ref(ref)[1].column: ref for ref in cells}
    columns = sorted({split_ref(ref)[1].column for ref in cells})
    rows = sorted({split_ref(ref)[1].row for ref in cells})
    if len(rows) > MAX_GRID_ROWS:
        start = max(0, min(rows.index(focus_row) if focus_row in rows else 0, len(rows) - MAX_GRID_ROWS) - MAX_GRID_ROWS // 4)
        rows = rows[start:start + MAX_GRID_ROWS]

    def value_of(ref: str) -> float | None:
        try:
            value = book.value(ref)
        except FormulaError:
            return None
        return float(value) if is_number(value) else None

    def header_of(column: int) -> str:
        first = next(ref for ref in cells if split_ref(ref)[1].column == column)
        return book.column_header(first) or column_letters(column)

    grid_rows = []
    for row in rows:
        refs = [f"{sheet}!{column_letters(column)}{row}" for column in columns]
        present = [by_position.get(row * 100000 + column) for column in columns]
        label = next((book.row_label(ref) for ref in present if ref), "")
        grid_rows.append({"row": row, "label": label, "cells": [{"ref": ref, "value": value_of(ref), "formula": book.formula(ref)} for ref in refs]})
    first = next((ref for ref in cells if split_ref(ref)[1].row == rows[0]), None) if rows else None
    header_row = book.header_row(first) if first else None
    return {"sheet": sheet, "header_row": header_row, "columns": [{"letter": column_letters(c), "header": header_of(c)} for c in columns], "rows": grid_rows}


def upload_id_of(content: bytes) -> str:
    return f"upload-{hashlib.sha256(content).hexdigest()[:16]}"


def visitor_of(http: Request) -> str:
    forwarded = http.headers.get("x-forwarded-for", "").split(",")[0].strip()
    return forwarded or (http.client.host if http.client else "unknown")


async def read_request[T: BaseModel](http: Request, model: type[T]) -> tuple[T, bytes | None, str]:
    if not http.headers.get("content-type", "").startswith("multipart/form-data"):
        try:
            return model.model_validate(await http.json()), None, ""
        except (ValueError, pydantic.ValidationError) as error:
            raise HTTPException(400, "The request is not valid JSON for this endpoint") from error
    form = await http.form()
    try:
        request = model.model_validate_json(str(form.get("request") or "{}"))
    except pydantic.ValidationError as error:
        raise HTTPException(400, "The request field is not valid JSON for this endpoint") from error
    upload = form.get("file")
    if upload is None or isinstance(upload, str):
        return request, None, ""
    return request, await upload.read(), upload.filename or ""


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def investigation_view(graph: CompiledStateGraph, investigation_id: str) -> dict:
    snapshot = graph.get_state({"configurable": {"thread_id": investigation_id}})
    pauses = [interrupt.value for task in snapshot.tasks for interrupt in task.interrupts]
    if "human_review" in snapshot.next:
        status = "needs_review"
    else:
        status = "done"
    values = snapshot.values
    return {
        "id": investigation_id,
        "status": status,
        "pause": pauses[0] if pauses else None,
        "check_labels": CHECK_LABELS,
        **{name: values.get(name) for name in PUBLIC_FIELDS},
    }


def create_app(source: SpreadsheetSource, sandbox: SandboxWithWrite, models: AgentModels, checkpointer: BaseCheckpointSaver, cap: UsageCap, allowed_origins: list[str] | None = None, store: BaseStore | None = None, upload_dir: Path | None = None, upload_ttl: float = UPLOAD_TTL, clock: Callable[[], float] = time.monotonic, copy_dir: Path | None = None, copy_ttl: float = COPY_TTL, ask_cap: UsageCap | None = None) -> FastAPI:
    app = FastAPI(title="Model X-Ray")
    app.add_middleware(CORSMiddleware, allow_origins=allowed_origins or [], allow_origin_regex=LOCAL_DEV_ORIGIN, allow_methods=["GET", "POST"], allow_headers=["Content-Type"])
    graphs: dict[str, CompiledStateGraph] = {}
    held = Uploads(source, upload_dir, upload_ttl, clock)
    copies = Copies(copy_dir, copy_ttl)
    questions = ask_cap or UsageCap(per_visitor=30, total=500, noun="questions")

    @app.exception_handler(Exception)
    def explain_failure(request: Request, error: Exception) -> JSONResponse:
        status, detail = friendly_error(error)
        return JSONResponse({"detail": detail}, status_code=status)

    def hold(content: bytes, name: str) -> str:
        if not held.enabled:
            raise HTTPException(404, "Uploading models is not enabled on this server")
        filename = Path(name).name
        if not filename.lower().endswith(".xlsx"):
            raise HTTPException(400, "Upload an Excel .xlsx file")
        if len(content) > MAX_UPLOAD_BYTES:
            raise HTTPException(413, "The file is larger than 10 MB")
        upload_id = upload_id_of(content)
        path = upload_dir / f"{upload_id}.xlsx"
        if held.holds(upload_id) and path.is_file():
            return upload_id
        upload_dir.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        try:
            load_xlsx(path)
        except Exception as error:
            path.unlink(missing_ok=True)
            raise HTTPException(400, f"{filename} is not a readable .xlsx file") from error
        source.add(upload_id, path)
        held.add(upload_id, path)
        return upload_id

    def delivered(graph: CompiledStateGraph, investigation_id: str) -> dict:
        view = investigation_view(graph, investigation_id)
        view["sheet"] = None
        target = view.get("target")
        if target:
            try:
                book = source.load(view["spreadsheet_id"])
                view["sheet"] = sheet_window(book, target["sheet"], split_ref(f"{target['sheet']}!{target['cell']}")[1].row)
            except ValueError:
                view["sheet"] = None
        view["corrected_file"] = None
        name = view.get("corrected_copy_id")
        locate_file = getattr(sandbox, "corrected_path", None)
        path = locate_file(name) if name and locate_file else None
        if path is not None:
            view["corrected_file"] = {"name": path.name, "base64": base64.b64encode(path.read_bytes()).decode("ascii")}
        return view

    def release(graph: CompiledStateGraph, investigation_id: str, failed: bool) -> None:
        try:
            state = graph.get_state({"configurable": {"thread_id": investigation_id}}).values
            finished = failed or investigation_view(graph, investigation_id)["status"] == "done"
        except Exception:
            return
        spreadsheet_id = state.get("spreadsheet_id")
        if finished and spreadsheet_id and held.holds(spreadsheet_id):
            held.drop(spreadsheet_id)

    def progress(graph: CompiledStateGraph, graph_input: Any, investigation_id: str) -> Iterator[str]:
        failed = False
        try:
            for update in graph.stream(graph_input, {"configurable": {"thread_id": investigation_id}}, stream_mode="updates"):
                for step in update:
                    if step in STEP_LABELS:
                        yield sse("step", {"step": step, "label": STEP_LABELS[step]})
            yield sse("view", delivered(graph, investigation_id))
        except Exception as error:
            failed = True
            status, detail = friendly_error(error)
            yield sse("error", {"status": status, "detail": detail})
        finally:
            release(graph, investigation_id, failed)

    def build(spreadsheet_id: str) -> CompiledStateGraph:
        try:
            return run_investigation(models.llm, spreadsheet_id, source, sandbox, checkpointer, verifier=models.verifier, locator=models.locator, mapper=models.mapper, explainer=models.explainer, store=store)
        except ValueError as error:
            raise HTTPException(400, str(error)) from error

    def graph_of(investigation_id: str) -> CompiledStateGraph:
        if investigation_id not in graphs:
            raise HTTPException(404, f"No investigation {investigation_id!r}")
        return graphs[investigation_id]

    def open_investigation(request: StartRequest, http: Request) -> tuple[CompiledStateGraph, str]:
        if not request.spreadsheet_id:
            raise HTTPException(400, "Choose a model or send the .xlsx file to check")
        visitor = visitor_of(http)
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

    def continue_graph(spreadsheet_id: str) -> CompiledStateGraph:
        try:
            return run_continuation(models.llm, spreadsheet_id, source, sandbox, checkpointer, verifier=models.verifier, locator=models.locator, mapper=models.mapper, explainer=models.explainer, store=store)
        except ValueError as error:
            raise HTTPException(400, str(error)) from error

    def resumable(investigation_id: str, request: ResumeRequest, upload_id: str | None = None) -> tuple[CompiledStateGraph, Any]:
        if upload_id is not None and request.state is not None and request.state.get("spreadsheet_id") != upload_id:
            raise HTTPException(400, "This is not the file the review started on; send the same .xlsx to continue it")
        if investigation_id in graphs:
            graph = paused_graph(investigation_id)
            return graph, Command(resume=resume_payload(graph, investigation_id, request))
        if request.state is None:
            raise HTTPException(404, f"No investigation {investigation_id!r}")
        decision = decision_of(request)
        carried = carried_state(request.state)
        if decision.get("patch"):
            decision["patch"] = checked_patch(source, carried["spreadsheet_id"], decision["patch"])
        graph = continue_graph(carried["spreadsheet_id"])
        graphs[investigation_id] = graph
        return graph, {**carried, "human_decision": decision}

    def resume_payload(graph: CompiledStateGraph, investigation_id: str, request: ResumeRequest) -> dict[str, Any]:
        payload = request.model_dump(exclude_none=True)
        if payload.get("patch"):
            values = graph.get_state({"configurable": {"thread_id": investigation_id}}).values
            payload["patch"] = checked_patch(source, values["spreadsheet_id"], payload["patch"])
        return payload

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.get("/spreadsheets")
    def spreadsheets() -> list[dict]:
        held.sweep()
        copies.sweep()
        return [{"id": spreadsheet_id, "sheets": source.list_sheets(spreadsheet_id)} for spreadsheet_id in source.ids() if not held.holds(spreadsheet_id)]

    @app.post("/spreadsheets", status_code=201)
    async def upload(request: Request, name: str) -> dict:
        if not held.enabled:
            raise HTTPException(404, "Uploading models is not enabled on this server")
        upload_id = hold(await request.body(), name)
        return {"id": upload_id, "name": Path(name).name, "sheets": source.list_sheets(upload_id)}

    def cell_labels(state: dict[str, Any]) -> dict[str, str]:
        try:
            book = source.load(state["spreadsheet_id"])
        except ValueError:
            return {}
        refs = {ref for verification in state.get("verifications", []) for ref in verification.get("after", {})}
        if state.get("patch"):
            refs.add(state["patch"]["cell"])
        labels = {}
        for ref in refs:
            try:
                name = " ".join(part for part in (book.row_label(ref), book.column_header(ref)) if part)
            except (ValueError, KeyError):
                name = ""
            if name:
                labels[ref] = name
        return labels

    @app.post("/investigations/{investigation_id}/ask")
    def ask(investigation_id: str, request: AskRequest, http: Request) -> dict:
        question = request.question.strip()
        if not question:
            raise HTTPException(400, "Write a question for the agent")
        if len(question) > MAX_QUESTION_CHARS:
            raise HTTPException(400, f"Keep the question under {MAX_QUESTION_CHARS} characters")
        if request.state is None:
            raise HTTPException(400, "Send the check's state with the question, so the agent knows what it found")
        state = carried_state(request.state)
        visitor = visitor_of(http)
        questions.check(visitor)
        answer, _ = answer_question(models.explainer or models.llm, state, request.history[-MAX_HISTORY_TURNS:], question, cell_labels(state))
        questions.record(visitor)
        return {"answer": answer}

    @app.post("/workbook")
    async def workbook(http: Request) -> dict:
        request, content, name = await read_request(http, WorkbookRequest)
        spreadsheet_id = hold(content, name) if content is not None else request.spreadsheet_id
        try:
            return workbook_view(source.load(spreadsheet_id))
        except ValueError as error:
            raise HTTPException(400, str(error)) from error

    @app.get("/investigations/{investigation_id}/sheet")
    def sheet(investigation_id: str) -> dict:
        values = graph_of(investigation_id).get_state({"configurable": {"thread_id": investigation_id}}).values
        target = values.get("target")
        if not target:
            raise HTTPException(404, "The investigation has not found its cell yet")
        try:
            book = source.load(values["spreadsheet_id"])
        except ValueError as error:
            raise HTTPException(404, f"This model is no longer on the server; upload it again to check it ({error})") from error
        return sheet_window(book, target["sheet"], split_ref(f"{target['sheet']}!{target['cell']}")[1].row)

    @app.get("/investigations/{investigation_id}/corrected")
    def corrected(investigation_id: str) -> FileResponse:
        name = investigation_view(graph_of(investigation_id), investigation_id)["corrected_copy_id"]
        locate_file = getattr(sandbox, "corrected_path", None)
        path = locate_file(name) if name and locate_file else None
        if path is None:
            raise HTTPException(404, "No corrected file for this investigation; it is written only after you approve the fix, and once downloaded it is removed from the server")
        copies.holding(path)
        return FileResponse(path, media_type=XLSX_MEDIA_TYPE, filename=path.name, background=BackgroundTask(copies.release, path))

    def start_input(request: StartRequest) -> dict[str, Any]:
        graph_input: dict[str, Any] = {"spreadsheet_id": request.spreadsheet_id, "question": request.question}
        if request.set_aside:
            book = source.load(request.spreadsheet_id)
            overrides = []
            for cell in request.set_aside:
                try:
                    ref = normalize_ref(cell)
                except FormulaError:
                    continue
                overrides.append({"cell": ref, "content": str(book.raw(ref)), "reason": SET_ASIDE_REASON})
            graph_input["known_overrides"] = overrides
        return graph_input

    @app.post("/investigations", status_code=201)
    def start(request: StartRequest, http: Request) -> dict:
        graph, investigation_id = open_investigation(request, http)
        graph.invoke(start_input(request), {"configurable": {"thread_id": investigation_id}})
        return investigation_view(graph, investigation_id)

    @app.post("/investigations/stream")
    async def start_stream(http: Request) -> StreamingResponse:
        request, content, name = await read_request(http, StartRequest)
        if content is not None:
            request = request.model_copy(update={"spreadsheet_id": hold(content, name)})
        graph, investigation_id = open_investigation(request, http)
        return StreamingResponse(progress(graph, start_input(request), investigation_id), media_type="text/event-stream")

    @app.get("/investigations/{investigation_id}")
    def read(investigation_id: str) -> dict:
        return investigation_view(graph_of(investigation_id), investigation_id)

    @app.post("/investigations/{investigation_id}/resume")
    def resume(investigation_id: str, request: ResumeRequest) -> dict:
        graph, graph_input = resumable(investigation_id, request)
        graph.invoke(graph_input, {"configurable": {"thread_id": investigation_id}})
        view = investigation_view(graph, investigation_id)
        release(graph, investigation_id, False)
        return view

    @app.post("/investigations/{investigation_id}/resume/stream")
    async def resume_stream(investigation_id: str, http: Request) -> StreamingResponse:
        request, content, name = await read_request(http, ResumeRequest)
        upload_id = hold(content, name) if content is not None else None
        graph, graph_input = resumable(investigation_id, request, upload_id)
        return StreamingResponse(progress(graph, graph_input, investigation_id), media_type="text/event-stream")

    return app

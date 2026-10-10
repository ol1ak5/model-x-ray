from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from model_x_ray.agents.investigator import build_investigator, make_diagnose_node
from model_x_ray.graph import build_graph, run_investigation
from model_x_ray.llm import build_chat_model
from model_x_ray.spreadsheet.source import XlsxSource
from model_x_ray.spreadsheet.xlsx import load_xlsx
from model_x_ray.state import InvestigationState


CELLS = {
    "P&L!H4": "P&L!H4 Revenue 2027 = 216.0, formula =G4*(1+Assumptions!C5)",
    "P&L!H5": "P&L!H5 COGS 2027 = -118.8, formula =-H4*Assumptions!C6",
    "P&L!H6": "P&L!H6 Gross profit 2027 = 97.2, formula =H4+H5",
    "P&L!H7": "P&L!H7 Opex 2027 = -45.2, typed number, no formula, no note",
    "P&L!H8": "P&L!H8 EBITDA 2027 = 52.0, formula =H6+H7",
}

PRECEDENTS = {
    "P&L!H8": "P&L!H8 depends on P&L!H6, P&L!H7",
    "P&L!H6": "P&L!H6 depends on P&L!H4, P&L!H5",
    "P&L!H7": "P&L!H7 has no precedents: it is a typed number",
}


@tool
def get_cell(ref: str) -> str:
    """Return the value and formula of one spreadsheet cell, for example ref='P&L!H8'."""
    return CELLS.get(ref, f"{ref} is empty")


@tool
def trace_precedents(ref: str) -> str:
    """List the cells that a cell's formula depends on (its inputs), for example ref='P&L!H8'."""
    return PRECEDENTS.get(ref, f"{ref} has no precedents")


class AlwaysCallsATool(BaseChatModel):
    bound: list[str] = []
    calls: int = 0

    @property
    def _llm_type(self) -> str:
        return "always-calls-a-tool"

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> "AlwaysCallsATool":
        names = [getattr(t, "name", None) or getattr(t, "__name__", "") for t in tools]
        return self.model_copy(update={"bound": names})

    def _generate(self, messages: list[BaseMessage], stop: list[str] | None = None, **kwargs: Any) -> ChatResult:
        self.calls += 1
        if "Diagnosis" in self.bound:
            call = {"name": "Diagnosis", "args": {"hypotheses": [], "patch": None}, "id": "conclude"}
        else:
            call = {"name": "get_cell", "args": {"ref": "P&L!H8"}, "id": f"call-{self.calls}"}
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content="", tool_calls=[call]))])


def test_investigator_stops_at_the_tool_budget() -> None:
    investigator = build_investigator(AlwaysCallsATool(), [get_cell, trace_precedents], max_tool_calls=8)

    result = investigator.invoke({"messages": [HumanMessage(content="Why did EBITDA 2027 jump?")]})

    assert result["tool_calls_used"] == 8
    assert sum(1 for m in result["messages"] if m.type == "tool") == 8
    assert result["diagnosis"].hypotheses == []


class BatchesFiveToolCalls(BaseChatModel):
    bound: list[str] = []
    turns: int = 0

    @property
    def _llm_type(self) -> str:
        return "batches-five-tool-calls"

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> "BatchesFiveToolCalls":
        names = [getattr(t, "name", None) or getattr(t, "__name__", "") for t in tools]
        return self.model_copy(update={"bound": names})

    def _generate(self, messages: list[BaseMessage], stop: list[str] | None = None, **kwargs: Any) -> ChatResult:
        self.turns += 1
        if "Diagnosis" in self.bound:
            call = {"name": "Diagnosis", "args": {"hypotheses": [], "patch": None}, "id": "conclude"}
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content="", tool_calls=[call]))])
        calls = [{"name": "count_cell", "args": {"ref": "P&L!H8"}, "id": f"batch-{self.turns}-{i}"} for i in range(5)]
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content="", tool_calls=calls))])


def test_parallel_tool_calls_never_exceed_the_budget() -> None:
    executions: list[str] = []

    @tool
    def count_cell(ref: str) -> str:
        """Return the value of one cell, for example ref='P&L!H8'."""
        executions.append(ref)
        return f"{ref} = 52.0"

    investigator = build_investigator(BatchesFiveToolCalls(), [count_cell], max_tool_calls=3)

    result = investigator.invoke({"messages": [HumanMessage(content="Why did EBITDA 2027 jump?")]})

    assert result["tool_calls_used"] == 3
    assert executions == ["P&L!H8"] * 3
    tool_messages = [m for m in result["messages"] if m.type == "tool"]
    assert len(tool_messages) == 5
    assert sum(1 for m in tool_messages if m.content == "Tool budget exhausted.") == 2


@pytest.mark.live
def test_investigator_chains_tools_and_answers_with_nemotron() -> None:
    llm = build_chat_model("nvidia/nemotron-3-super-120b-a12b")
    investigator = build_investigator(llm, [get_cell, trace_precedents])

    result = investigator.invoke({"messages": [HumanMessage(content="Which cells feed into P&L!H8, and what is the value of the first one?")]})

    used = [m.name for m in result["messages"] if m.type == "tool"]
    assert used[:2] == ["trace_precedents", "get_cell"]
    assert result["diagnosis"] is not None


@tool
def compare_formulas(ref: str) -> str:
    """Compare a cell's formula with the formulas in the neighbouring cells of the same row and report whether it breaks the pattern, for example ref='P&L!H7'."""
    if ref == "P&L!H7":
        return "P&L!H7 is a typed number -45.2 with no formula and no note; neighbours use =F7*(1+Assumptions!C7) and =G7*(1+Assumptions!C7) style formulas. H7 breaks the pattern."
    return f"{ref} follows the same formula pattern as its neighbours."


@tool
def explain_change(ref: str) -> str:
    """Split the change of a cell between the prior and current period into the contribution of each input, for example ref='P&L!H8'."""
    return "P&L!H8 changed from 40.0 to 52.0 (+12.0): gross profit P&L!H6 contributed +7.2 (in line with 8% revenue growth), opex P&L!H7 contributed +4.8 (opex fell 9.6% while revenue grew 8%)."


@pytest.mark.live
def test_investigator_diagnoses_a_typed_value_with_nemotron() -> None:
    llm = build_chat_model("nvidia/nemotron-3-super-120b-a12b")
    investigator = build_investigator(llm, [get_cell, trace_precedents, compare_formulas, explain_change])

    result = investigator.invoke({"messages": [HumanMessage(content="Why did EBITDA 2027 in P&L!H8 jump 30%?")]})
    diagnosis = result["diagnosis"]

    assert diagnosis.hypotheses[0].cell.endswith("H7")
    assert diagnosis.hypotheses[0].error_type == "typed_value"
    assert diagnosis.patch is not None and diagnosis.patch.cell.endswith("H7")


class ScriptedDiagnosis(BaseChatModel):
    bound: list[str] = []
    briefs: list[str] = []
    turns: list[tuple[list[str], str] | tuple[list[str], str, str]] = [(["P&L!H7"], "P&L!H7")]

    @property
    def _llm_type(self) -> str:
        return "scripted-diagnosis"

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> "ScriptedDiagnosis":
        names = [getattr(t, "name", None) or getattr(t, "__name__", "") for t in tools]
        return self.model_copy(update={"bound": names, "briefs": self.briefs})

    def _generate(self, messages: list[BaseMessage], stop: list[str] | None = None, **kwargs: Any) -> ChatResult:
        if "Diagnosis" not in self.bound:
            self.briefs.append(messages[1].content)
            usage = {"input_tokens": 1200, "output_tokens": 150, "total_tokens": 1350}
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content="Enough evidence.", usage_metadata=usage))])
        turn = self.turns[min(len(self.briefs), len(self.turns)) - 1]
        cells, patch_cell = turn[0], turn[1]
        new_formula = turn[2] if len(turn) > 2 else "=G7*(1+Assumptions!$C$7)"
        args = {
            "hypotheses": [
                {"cell": cell, "error_type": "typed_value", "claim": f"{cell} is a typed number, not a formula", "confidence": "high"}
                for cell in cells
            ],
            "patch": {"cell": patch_cell, "new_formula": new_formula},
        }
        call = {"name": "Diagnosis", "args": args, "id": "conclude"}
        usage = {"input_tokens": 1200, "output_tokens": 150, "total_tokens": 1350}
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content="", tool_calls=[call], usage_metadata=usage))])


def test_investigator_runs_as_the_diagnose_node_of_the_main_graph(demo_workbook_path: Path) -> None:
    investigator = build_investigator(ScriptedDiagnosis(), [get_cell, trace_precedents])
    graph = build_graph(InMemorySaver(), diagnose=make_diagnose_node(investigator, load_xlsx(demo_workbook_path)))
    config = {"configurable": {"thread_id": "real-diagnose"}}

    graph.invoke({"spreadsheet_id": "demo", "question": "Why did EBITDA 2027 jump on the P&L sheet?"}, config)
    state = graph.get_state(config).values

    assert [(h["id"], h["cell"], h["confidence"], h["status"]) for h in state["hypotheses"]] == [("hyp-1", "P&L!H7", "high", "confirmed")]
    assert state["patch"]["new_formula"] == "=G7*(1+Assumptions!$C$7)"
    assert graph.get_state(config).next == ("human_review",)


def test_run_investigation_wires_the_real_investigator_into_the_graph(demo_workbook_path: Path, engine_sandbox) -> None:
    model = ScriptedDiagnosis(turns=[(["P&L!H5"], "P&L!H5")])
    graph = run_investigation(model, "demo", XlsxSource({"demo": demo_workbook_path}), engine_sandbox)
    config = {"configurable": {"thread_id": "entrypoint"}}

    graph.invoke({"spreadsheet_id": "demo", "question": "Why did EBITDA 2027 jump on the P&L sheet?"}, config)
    state = graph.get_state(config).values

    assert model.briefs and "Question:" in model.briefs[0]
    assert "Cause tree" in model.briefs[0]
    assert "P&L!H7 Opex" in model.briefs[0] and "SUSPICIOUS" in model.briefs[0]
    assert state["causal_tree"] is not None and state["causal_tree"]["cell"] == "P&L!H8"
    assert {c["cell"] for c in state["contributions"]} == {"P&L!H6", "P&L!H7"}
    assert [(h["id"], h["cell"], h["claim"]) for h in state["hypotheses"]] == [
        ("hyp-1", "P&L!H5", "P&L!H5 is a typed number, not a formula"),
    ]
    assert state["patch"]["cell"] == "P&L!H5"
    assert graph.get_state(config).next == ("human_review",)


def test_diagnose_keeps_only_the_top_three_hypotheses(demo_workbook_path: Path) -> None:
    model = ScriptedDiagnosis(turns=[(["P&L!H5", "P&L!H6", "P&L!H7", "P&L!H4", "Assumptions!C5"], "P&L!H7")])
    investigator = build_investigator(model, [get_cell, trace_precedents])
    graph = build_graph(InMemorySaver(), diagnose=make_diagnose_node(investigator, load_xlsx(demo_workbook_path)))
    config = {"configurable": {"thread_id": "five-proposals"}}

    graph.invoke({"spreadsheet_id": "demo", "question": "Why did EBITDA 2027 jump on the P&L sheet?"}, config)
    state = graph.get_state(config).values

    assert [(h["id"], h["cell"]) for h in state["hypotheses"]] == [
        ("hyp-1", "P&L!H5"),
        ("hyp-2", "P&L!H6"),
        ("hyp-3", "P&L!H7"),
    ]
    assert graph.get_state(config).next == ("human_review",)


def test_retry_tells_the_investigator_which_hypotheses_were_rejected(demo_workbook_path: Path) -> None:
    model = ScriptedDiagnosis(turns=[(["P&L!H7", "P&L!H5"], "P&L!H5"), ([], "P&L!H5")])
    investigator = build_investigator(model, [get_cell, trace_precedents])
    graph = build_graph(InMemorySaver(), diagnose=make_diagnose_node(investigator, load_xlsx(demo_workbook_path)), overrides={"verify": reject_first_then_confirm})
    config = {"configurable": {"thread_id": "retry-brief"}}

    graph.invoke({"spreadsheet_id": "demo", "question": "Why did EBITDA 2027 jump on the P&L sheet?"}, config)
    state = graph.get_state(config).values

    assert "Already rejected, do not propose again: P&L!H7" in model.briefs[1]
    assert [(h["id"], h["cell"], h["status"]) for h in state["hypotheses"]] == [("hyp-1", "P&L!H7", "rejected"), ("hyp-2", "P&L!H5", "confirmed")]


def reject_first_then_confirm(state: InvestigationState) -> dict:
    if state.get("attempts", 0) == 0:
        hypothesis = state["hypotheses"][0]
        verdict = "rejected"
    else:
        hypothesis = next(h for h in state["hypotheses"] if h["status"] == "open")
        verdict = "confirmed"
    return {
        "verifications": [{"hypothesis_id": hypothesis["id"], "before": {}, "after": {}, "checks": {}, "verdict": verdict, "reason": "scripted"}],
        "hypotheses": [{"id": hypothesis["id"], "status": verdict}],
        "attempts": state.get("attempts", 0) + 1,
    }


class OutlierScanner(BaseChatModel):
    bound: list[str] = []

    @property
    def _llm_type(self) -> str:
        return "outlier-scanner"

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> "OutlierScanner":
        names = [getattr(t, "name", None) or getattr(t, "__name__", "") for t in tools]
        return self.model_copy(update={"bound": names})

    @staticmethod
    def _results(messages: list[BaseMessage]) -> dict[str, str]:
        return {m.name: m.content for m in messages if isinstance(m, ToolMessage) and m.name}

    @staticmethod
    def _candidate(outliers: str) -> str | None:
        if outliers == "no outliers found":
            return None
        return outliers.splitlines()[0].split(":")[0]

    @staticmethod
    def _diagnosis(results: dict[str, str]) -> dict:
        cell = OutlierScanner._candidate(results.get("find_formula_outliers", "no outliers found"))
        if cell is None or "note: " in results.get("get_cell_metadata", "no note"):
            return {"hypotheses": [], "patch": None}
        return {
            "hypotheses": [{
                "cell": cell,
                "error_type": "typed_value",
                "claim": f"{cell} is a typed value where the row uses formulas",
                "confidence": "high",
            }],
            "patch": {"cell": cell, "new_formula": "=G7*(1+Assumptions!$C$7)"},
        }

    def _generate(self, messages: list[BaseMessage], stop: list[str] | None = None, **kwargs: Any) -> ChatResult:
        results = self._results(messages)
        if "Diagnosis" in self.bound:
            call = {"name": "Diagnosis", "args": self._diagnosis(results), "id": "conclude"}
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content="", tool_calls=[call]))])
        if "find_formula_outliers" not in results:
            call = {"name": "find_formula_outliers", "args": {"range": "P&L!G4:H9"}, "id": "scan"}
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content="", tool_calls=[call]))])
        cell = self._candidate(results["find_formula_outliers"])
        if cell is not None and "get_cell_metadata" not in results:
            call = {"name": "get_cell_metadata", "args": {"ref": cell}, "id": "meta"}
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content="", tool_calls=[call]))])
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content="Enough evidence."))])


def test_investigator_finds_the_planted_typed_value_through_the_real_tools(demo_workbook_path: Path, engine_sandbox, scripted_verdict) -> None:
    graph = run_investigation(OutlierScanner(), "demo", XlsxSource({"demo": demo_workbook_path}), engine_sandbox, verifier=scripted_verdict)
    config = {"configurable": {"thread_id": "planted-real-tools"}}

    graph.invoke({"spreadsheet_id": "demo", "question": "Why did EBITDA 2027 jump on the P&L sheet?"}, config)
    state = graph.get_state(config).values

    assert state["hypotheses"][0]["cell"] == "P&L!H7"
    assert state["hypotheses"][0]["error_type"] == "typed_value"
    assert state["hypotheses"][0]["status"] == "confirmed"

    patch = state["patch"]
    assert patch["cell"] == "P&L!H7"
    assert patch["old_formula"] == "-45.2"

    evidence_by_id = {e["id"]: e for e in state["evidence"]}
    assert [e["id"] for e in state["evidence"]] == ["ev-1", "ev-2", "ev-3", "ev-4", "ev-5", "ev-6"]
    assert [e["kind"] for e in state["evidence"]][-1] == "verification"
    assert [e["cell"] for e in state["evidence"][:3]] == ["P&L!H8", "P&L!H6", "P&L!H7"]
    assert all(e["cell"] == "P&L!H7" for e in state["evidence"][3:])
    assert any(e["kind"] == "anomaly" for e in state["evidence"])
    for evidence_id in state["hypotheses"][0]["evidence_ids"]:
        assert evidence_id in evidence_by_id
        assert evidence_by_id[evidence_id]["cell"] == "P&L!H7"

    book = load_xlsx(demo_workbook_path)
    patched = book.with_patch(patch["cell"], patch["new_formula"])
    assert patched.formula_pattern("P&L!H7") == book.formula_pattern("P&L!G7")
    assert patched.value("P&L!H8") == pytest.approx(44.73, abs=0.01)


def test_investigator_leaves_a_deliberate_override_alone(demo_workbook_with_override_note: Path, engine_sandbox) -> None:
    graph = run_investigation(OutlierScanner(), "demo", XlsxSource({"demo": demo_workbook_with_override_note}), engine_sandbox)
    config = {"configurable": {"thread_id": "override-real-tools"}}

    graph.invoke({"spreadsheet_id": "demo", "question": "Why did EBITDA 2027 jump on the P&L sheet?"}, config)
    state = graph.get_state(config).values

    assert state["hypotheses"] == []
    assert state["patch"] is None
    assert "Inconclusive" in state["report"]
    assert any("Per budget meeting" in e["text"] for e in state["evidence"])
    assert all(evidence_id.startswith("ev-") for evidence_id in [e["id"] for e in state["evidence"]])


@pytest.mark.live
def test_nemotron_super_finds_the_planted_typed_value_on_the_fixture(demo_workbook_path: Path, engine_sandbox) -> None:
    llm = build_chat_model("nvidia/nemotron-3-super-120b-a12b")
    graph = run_investigation(llm, "demo", XlsxSource({"demo": demo_workbook_path}), engine_sandbox)
    config = {"configurable": {"thread_id": "live-planted"}}

    graph.invoke({"spreadsheet_id": "demo", "question": "Why did EBITDA 2027 jump on the P&L sheet?"}, config)
    state = graph.get_state(config).values

    cells = [h["cell"] for h in state["hypotheses"]]
    assert "P&L!H7" in cells


def test_open_hypothesis_budget_holds_across_a_retry(demo_workbook_path: Path) -> None:
    model = ScriptedDiagnosis(turns=[(["P&L!H7"], "P&L!H7"), (["P&L!H4", "P&L!H5", "P&L!H6"], "P&L!H5")])
    investigator = build_investigator(model, [get_cell, trace_precedents])
    graph = build_graph(
        InMemorySaver(),
        diagnose=make_diagnose_node(investigator, load_xlsx(demo_workbook_path)),
        overrides={"verify": verify_keep_open_then_confirm},
    )
    config = {"configurable": {"thread_id": "open-budget"}}

    graph.invoke({"spreadsheet_id": "demo", "question": "Why did EBITDA 2027 jump on the P&L sheet?"}, config)
    state = graph.get_state(config).values

    assert "Open hypotheses: 0/3" in model.briefs[0]
    assert "Open hypotheses: 1/3" in model.briefs[1]
    assert [h["id"] for h in state["hypotheses"]] == ["hyp-1", "hyp-2", "hyp-3"]
    assert sum(1 for h in state["hypotheses"] if h["status"] == "open") <= 3


def verify_keep_open_then_confirm(state: InvestigationState) -> dict:
    if state.get("attempts", 0) == 0:
        return {
            "verifications": [{
                "hypothesis_id": "hyp-1", "before": {}, "after": {}, "checks": {},
                "verdict": "inconclusive", "reason": "needs another diagnosis",
            }],
            "attempts": 1,
        }
    hypothesis = state["hypotheses"][-1]
    return {
        "verifications": [{"hypothesis_id": hypothesis["id"], "before": {}, "after": {}, "checks": {}, "verdict": "confirmed", "reason": "scripted"}],
        "hypotheses": [{"id": hypothesis["id"], "status": "confirmed"}],
        "attempts": 2,
    }


def test_approve_writes_a_corrected_copy_with_a_change_log(demo_workbook_path: Path, engine_sandbox, scripted_verdict) -> None:
    model = ScriptedDiagnosis(turns=[(["P&L!H7"], "P&L!H7")])
    graph = run_investigation(model, "demo", XlsxSource({"demo": demo_workbook_path}), engine_sandbox, verifier=scripted_verdict)
    config = {"configurable": {"thread_id": "approve-corrected"}}

    graph.invoke({"spreadsheet_id": "demo", "question": "Why did EBITDA 2027 jump on the P&L sheet?"}, config)
    assert graph.get_state(config).next == ("human_review",)
    graph.invoke(Command(resume={"action": "approve", "reason": "", "patch": None}), config)
    state = graph.get_state(config).values

    assert state["corrected_copy_id"] == "corrected:demo"
    assert engine_sandbox.writes[0]["spreadsheet_id"] == "demo"
    assert engine_sandbox.writes[0]["patch"]["cell"] == "P&L!H7"
    log_rows = engine_sandbox.writes[0]["log_rows"]
    assert log_rows[0] == ["Timestamp", "Cell", "Old formula", "New formula", "Reason"]
    assert log_rows[1][1:] == [
        "P&L!H7", "-45.2", "=G7*(1+Assumptions!$C$7)", "P&L!H7 is a typed number, not a formula",
    ]


def test_edit_replaces_the_patch_and_reruns_the_sandbox(demo_workbook_path: Path, engine_sandbox, scripted_verdict) -> None:
    model = ScriptedDiagnosis(turns=[(["P&L!H7"], "P&L!H7")])
    graph = run_investigation(model, "demo", XlsxSource({"demo": demo_workbook_path}), engine_sandbox, verifier=scripted_verdict)
    config = {"configurable": {"thread_id": "edit-patch"}}

    graph.invoke({"spreadsheet_id": "demo", "question": "Why did EBITDA 2027 jump on the P&L sheet?"}, config)
    assert graph.get_state(config).next == ("human_review",)
    confirmed_after = graph.get_state(config).values["verifications"][-1]["after"]["P&L!H8"]

    edited = {"cell": "P&L!H7", "old_formula": "-45.2", "new_formula": "=G7*(1+Assumptions!$C$6)", "source": "human"}
    graph.invoke(Command(resume={"action": "edit", "reason": "use the cost-ratio driver", "patch": edited}), config)
    state = graph.get_state(config).values

    assert state["patch"] == edited
    record = state["verifications"][-1]
    assert record["after"]["P&L!H8"] != confirmed_after
    patched = load_xlsx(demo_workbook_path).with_patch("P&L!H7", edited["new_formula"])
    assert record["after"]["P&L!H7"] == pytest.approx(patched.value("P&L!H7"))
    assert record["after"]["P&L!H8"] == pytest.approx(patched.value("P&L!H8"))
    assert record["verdict"] == "rejected"
    assert state["hypotheses"][0]["status"] == "rejected"
    assert graph.get_state(config).next == ("human_review",)

    graph.invoke(Command(resume={"action": "approve", "reason": "", "patch": None}), config)
    final = graph.get_state(config).values

    assert final["patch"] == edited
    assert final["corrected_copy_id"] == "corrected:demo"
    assert engine_sandbox.writes[0]["patch"]["new_formula"] == edited["new_formula"]
    assert engine_sandbox.writes[0]["log_rows"][1][3] == edited["new_formula"]


def test_graph_run_records_role_usage_for_the_evaluators(demo_workbook_path: Path, engine_sandbox, scripted_verdict) -> None:
    model = ScriptedDiagnosis(turns=[(["P&L!H7"], "P&L!H7")])
    graph = run_investigation(model, "demo", XlsxSource({"demo": demo_workbook_path}), engine_sandbox, verifier=scripted_verdict)
    config = {"configurable": {"thread_id": "usage-log"}}

    graph.invoke({"spreadsheet_id": "demo", "question": "Why did EBITDA 2027 jump on the P&L sheet?"}, config)
    run_log = graph.get_state(config).values["run_log"]

    assert {entry["role"] for entry in run_log} == {"investigator", "verifier"}
    assert len(run_log) >= 3
    by_role = {entry["role"]: entry for entry in run_log}
    assert by_role["investigator"]["model"] == "scripted-diagnosis"
    assert by_role["investigator"]["input_tokens"] == 1200
    assert by_role["investigator"]["output_tokens"] == 150
    assert by_role["verifier"]["model"] == "scripted-verdict"
    assert by_role["verifier"]["input_tokens"] == 800
    assert by_role["verifier"]["output_tokens"] == 50
    for entry in run_log:
        assert entry["latency_ms"] >= 0

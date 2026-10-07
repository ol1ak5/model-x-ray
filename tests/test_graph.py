from pathlib import Path

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from model_x_ray import nodes
from model_x_ray.graph import build_graph
from model_x_ray.memory import sqlite_checkpointer
from model_x_ray.state import InvestigationState

QUESTION = {"spreadsheet_id": "demo", "question": "Why did EBITDA 2027 jump on the P&L sheet?"}


def always_reject(state: InvestigationState) -> dict:
    hypothesis = state["hypotheses"][-1]
    return {
        "verifications": [{
            "hypothesis_id": hypothesis["id"], "before": {"P&L!H8": 52.0}, "after": {"P&L!H8": 52.0},
            "checks": {"anomaly_resolved": False}, "verdict": "rejected", "reason": "anomaly not resolved",
        }],
        "hypotheses": [{"id": hypothesis["id"], "status": "rejected"}],
        "attempts": state.get("attempts", 0) + 1,
    }


def test_confirmed_fix_pauses_for_approval_then_writes_a_corrected_copy() -> None:
    graph = build_graph(InMemorySaver(), diagnose=nodes.stub_diagnose)
    config = {"configurable": {"thread_id": "happy-path"}}

    paused = graph.invoke(QUESTION, config)

    assert graph.get_state(config).next == ("human_review",)
    assert paused["__interrupt__"][0].value["patch"]["cell"] == "P&L!H7"

    result = graph.invoke(Command(resume={"action": "approve", "reason": "", "patch": None}), config)

    assert result["corrected_copy_id"] == "corrected:demo"
    assert result["report"] == "Root cause found in P&L!H7."
    assert graph.get_state(config).next == ()


def always_diagnose_two(state: InvestigationState) -> dict:
    number = len(state.get("hypotheses", []))
    return {
        "hypotheses": [
            {"id": f"hyp-{number + offset}", "cell": cell, "error_type": error_type, "claim": claim,
             "evidence_ids": [], "confidence": "medium", "status": "open"}
            for offset, cell, error_type, claim in [
                (1, "P&L!H7", "typed_value", "Opex is typed"),
                (2, "P&L!H6", "inconsistent_range", "Gross profit range breaks the pattern"),
            ]
        ],
    }


def test_rejected_fixes_retry_three_times_then_report_inconclusive() -> None:
    graph = build_graph(InMemorySaver(), diagnose=always_diagnose_two, overrides={"verify": always_reject})
    config = {"configurable": {"thread_id": "exhausted"}}

    graph.invoke(QUESTION, config)
    state = graph.get_state(config).values

    assert state["attempts"] == 3
    assert [v["verdict"] for v in state["verifications"]] == ["rejected", "rejected", "rejected"]
    assert [h["status"] for h in state["hypotheses"]] == ["open", "rejected"] * 3
    assert state["report"].startswith("Inconclusive")
    assert graph.get_state(config).next == ("human_review",)


def test_rejection_with_no_untested_hypothesis_ends_inconclusive_on_first_attempt() -> None:
    graph = build_graph(InMemorySaver(), diagnose=nodes.stub_diagnose, overrides={"verify": always_reject})
    config = {"configurable": {"thread_id": "nothing-left"}}

    graph.invoke(QUESTION, config)
    state = graph.get_state(config).values

    assert state["attempts"] == 1
    assert [v["verdict"] for v in state["verifications"]] == ["rejected"]
    assert [h["status"] for h in state["hypotheses"]] == ["rejected"]
    assert state["report"].startswith("Inconclusive")
    assert graph.get_state(config).next == ("human_review",)


def test_human_rejection_ends_without_writing_anything() -> None:
    graph = build_graph(InMemorySaver(), diagnose=nodes.stub_diagnose)
    config = {"configurable": {"thread_id": "human-rejects"}}

    graph.invoke(QUESTION, config)
    result = graph.invoke(Command(resume={"action": "reject", "reason": "intentional override", "patch": None}), config)

    assert result.get("corrected_copy_id") is None
    assert graph.get_state(config).next == ()


def test_ambiguous_question_pauses_until_the_user_picks_a_cell() -> None:
    graph = build_graph(InMemorySaver(), diagnose=nodes.stub_diagnose)
    config = {"configurable": {"thread_id": "ambiguous"}}

    paused = graph.invoke({"spreadsheet_id": "demo", "question": "Why did EBITDA 2027 jump?"}, config)

    assert graph.get_state(config).next == ("locate",)
    assert paused["__interrupt__"][0].value["candidates"] == ["P&L!H8", "Summary!D10"]

    graph.invoke(Command(resume={"ref": "Summary!D10"}), config)
    state = graph.get_state(config).values

    assert state["target"]["sheet"] == "Summary"
    assert graph.get_state(config).next == ("human_review",)


def test_paused_investigation_survives_a_restart(tmp_path: Path) -> None:
    database = str(tmp_path / "investigations.db")
    config = {"configurable": {"thread_id": "restart"}}

    first_session = build_graph(sqlite_checkpointer(database), diagnose=nodes.stub_diagnose)
    first_session.invoke(QUESTION, config)
    assert first_session.get_state(config).next == ("human_review",)
    del first_session

    second_session = build_graph(sqlite_checkpointer(database), diagnose=nodes.stub_diagnose)
    assert second_session.get_state(config).next == ("human_review",)
    result = second_session.invoke(Command(resume={"action": "approve", "reason": "", "patch": None}), config)

    assert result["corrected_copy_id"] == "corrected:demo"
    assert second_session.get_state(config).next == ()

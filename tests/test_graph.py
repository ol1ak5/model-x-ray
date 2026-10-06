from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from model_x_ray.graph import build_graph
from model_x_ray.state import InvestigationState

QUESTION = {"spreadsheet_id": "demo", "question": "Why did EBITDA 2027 jump?"}


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
    graph = build_graph(InMemorySaver())
    config = {"configurable": {"thread_id": "happy-path"}}

    paused = graph.invoke(QUESTION, config)

    assert graph.get_state(config).next == ("human_review",)
    assert paused["__interrupt__"][0].value["patch"]["cell"] == "P&L!H7"

    result = graph.invoke(Command(resume={"action": "approve", "reason": "", "patch": None}), config)

    assert result["corrected_copy_id"] == "corrected:demo"
    assert result["report"] == "Root cause found in P&L!H7."
    assert graph.get_state(config).next == ()


def test_rejected_fixes_retry_three_times_then_report_inconclusive() -> None:
    graph = build_graph(InMemorySaver(), overrides={"verify": always_reject})
    config = {"configurable": {"thread_id": "exhausted"}}

    graph.invoke(QUESTION, config)
    state = graph.get_state(config).values

    assert state["attempts"] == 3
    assert [v["verdict"] for v in state["verifications"]] == ["rejected", "rejected", "rejected"]
    assert [h["status"] for h in state["hypotheses"]] == ["rejected", "rejected", "rejected"]
    assert state["report"].startswith("Inconclusive")
    assert graph.get_state(config).next == ("human_review",)


def test_human_rejection_ends_without_writing_anything() -> None:
    graph = build_graph(InMemorySaver())
    config = {"configurable": {"thread_id": "human-rejects"}}

    graph.invoke(QUESTION, config)
    result = graph.invoke(Command(resume={"action": "reject", "reason": "intentional override", "patch": None}), config)

    assert result.get("corrected_copy_id") is None
    assert graph.get_state(config).next == ()

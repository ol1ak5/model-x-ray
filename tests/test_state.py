from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from model_x_ray.state import InputState, InvestigationState, OutputState


def propose(state: InvestigationState) -> dict:
    return {
        "hypotheses": [
            {"id": "h1", "cell": "P&L!H7", "error_type": "typed_value", "claim": "Opex 2027 is a typed number, not a formula", "evidence_ids": ["e1"], "confidence": "high", "status": "open"},
            {"id": "h2", "cell": "P&L!H5", "error_type": "sign_or_period", "claim": "COGS 2027 has a flipped sign", "evidence_ids": [], "confidence": "low", "status": "open"},
        ],
        "evidence": [{"id": "e1", "cell": "P&L!H7", "kind": "anomaly", "text": "H7 is a typed number while G7 is a formula"}],
    }


def verify(state: InvestigationState) -> dict:
    return {
        "hypotheses": [{"id": "h2", "status": "rejected"}, {"id": "h1", "status": "confirmed"}],
        "evidence": [{"id": "e2", "cell": "P&L!H7", "kind": "verification", "text": "With the formula restored, EBITDA growth is 11.8%"}],
        "attempts": state.get("attempts", 0) + 1,
        "report": "EBITDA 2027 is overstated by 7.3m because P&L!H7 is a typed number.",
    }


def test_reducers_keep_the_audit_trail_through_a_real_graph_run() -> None:
    builder = StateGraph(InvestigationState, input_schema=InputState, output_schema=OutputState)
    builder.add_node("propose", propose)
    builder.add_node("verify", verify)
    builder.add_edge(START, "propose")
    builder.add_edge("propose", "verify")
    builder.add_edge("verify", END)
    graph = builder.compile(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "state-test"}}

    result = graph.invoke({"spreadsheet_id": "demo", "question": "Why did EBITDA 2027 jump?"}, config)
    full_state = graph.get_state(config).values

    assert "hypotheses" not in result
    assert result["report"].startswith("EBITDA 2027 is overstated")
    assert [(h["id"], h["status"]) for h in full_state["hypotheses"]] == [("h1", "confirmed"), ("h2", "rejected")]
    assert full_state["hypotheses"][0]["claim"] == "Opex 2027 is a typed number, not a formula"
    assert [e["id"] for e in full_state["evidence"]] == ["e1", "e2"]
    assert full_state["attempts"] == 1

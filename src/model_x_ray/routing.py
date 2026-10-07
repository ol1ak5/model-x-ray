from langgraph.graph import END

from model_x_ray.state import InvestigationState

MAX_ATTEMPTS = 3


def route_after_verify(state: InvestigationState) -> str:
    if state["verifications"][-1]["verdict"] == "confirmed":
        return "confirmed"
    if state["attempts"] < MAX_ATTEMPTS:
        return "retry"
    return "inconclusive"


def route_after_review(state: InvestigationState) -> str:
    action = state["human_decision"]["action"]
    if action == "approve":
        return "apply_fix"
    if action == "edit":
        return "test"
    return END

from model_x_ray.state import InvestigationState

MAX_ATTEMPTS = 3


def route_after_verify(state: InvestigationState) -> str:
    if state["verifications"][-1]["verdict"] == "confirmed":
        return "confirmed"
    untested_hypotheses = [h for h in state["hypotheses"] if h["status"] == "open"]
    if untested_hypotheses and state["attempts"] < MAX_ATTEMPTS:
        return "retry"
    return "inconclusive"


def route_after_review(state: InvestigationState) -> str:
    action = state["human_decision"]["action"]
    if action == "approve":
        return "approve"
    if action == "edit":
        return "edit"
    return "reject"

from langgraph.types import interrupt

from model_x_ray.state import InvestigationState


def load_sheet(state: InvestigationState) -> dict:
    return {}


def map_model(state: InvestigationState) -> dict:
    return {"model_map_ref": f"map:{state['spreadsheet_id']}"}


def locate(state: InvestigationState) -> dict:
    return {
        "target": {
            "sheet": "P&L", "cell": "H8", "label": "EBITDA", "period": "2027",
            "value": 52.0, "prior_cell": "G8", "prior_value": 40.0,
        }
    }


def trace(state: InvestigationState) -> dict:
    return {
        "contributions": [
            {"cell": "H6", "label": "Gross profit", "delta": 7.2},
            {"cell": "H7", "label": "Opex", "delta": 4.8},
        ]
    }


def diagnose(state: InvestigationState) -> dict:
    number = len(state.get("hypotheses", [])) + 1
    return {
        "hypotheses": [{
            "id": f"hyp-{number}", "cell": "P&L!H7", "error_type": "typed_value",
            "claim": "Opex 2027 is a typed number, not a formula",
            "evidence_ids": [], "confidence": 0.8, "status": "open",
        }],
        "patch": {"cell": "P&L!H7", "old_formula": "-45.2", "new_formula": "=G7*(1+Assumptions!C7)", "source": "agent"},
    }


def test(state: InvestigationState) -> dict:
    return {}


def verify(state: InvestigationState) -> dict:
    hypothesis = state["hypotheses"][-1]
    return {
        "verifications": [{
            "hypothesis_id": hypothesis["id"], "before": {"P&L!H8": 52.0}, "after": {"P&L!H8": 44.7},
            "checks": {"anomaly_resolved": True}, "verdict": "confirmed", "reason": "stub",
        }],
        "hypotheses": [{"id": hypothesis["id"], "status": "confirmed"}],
        "attempts": state.get("attempts", 0) + 1,
    }


def explain(state: InvestigationState) -> dict:
    if state["verifications"][-1]["verdict"] == "confirmed":
        return {"report": f"Root cause found in {state['patch']['cell']}."}
    return {"report": "Inconclusive: no hypothesis survived verification."}


def human_review(state: InvestigationState) -> dict:
    decision = interrupt({"report": state["report"], "patch": state.get("patch")})
    return {"human_decision": decision}


def apply_fix(state: InvestigationState) -> dict:
    return {"corrected_copy_id": f"corrected:{state['spreadsheet_id']}"}

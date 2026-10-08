from collections.abc import Callable
from datetime import datetime, timezone

from langchain_core.language_models import BaseChatModel
from langgraph.types import interrupt

from model_x_ray import causal
from model_x_ray.agents.verifier import build_verifier, deterministic_checks, invoke_verifier
from model_x_ray.spreadsheet.engine import Workbook
from model_x_ray.spreadsheet.sandbox import Sandbox, SandboxWithWrite, run_sandbox_test
from model_x_ray.spreadsheet.source import SpreadsheetSource
from model_x_ray.state import Hypothesis, InvestigationState, TargetCell


def load_sheet(state: InvestigationState) -> dict:
    return {}


def map_model(state: InvestigationState) -> dict:
    return {"model_map_ref": f"map:{state['spreadsheet_id']}"}


STUB_CELLS: list[TargetCell] = [
    {"sheet": "P&L", "cell": "H8", "label": "EBITDA", "period": "2027", "value": 52.0, "prior_cell": "G8", "prior_value": 40.0},
    {"sheet": "Summary", "cell": "D10", "label": "EBITDA", "period": "2027", "value": 52.0, "prior_cell": "C10", "prior_value": 40.0},
]


def find_candidates(question: str) -> list[TargetCell]:
    matches = [c for c in STUB_CELLS if c["label"] in question and c["period"] in question]
    named_sheet = [c for c in matches if c["sheet"] in question]
    return named_sheet or matches


def locate(state: InvestigationState) -> dict:
    candidates = find_candidates(state["question"])
    if len(candidates) == 1:
        return {"target": candidates[0]}
    choice = interrupt({
        "question": "Which cell do you mean?",
        "candidates": [f"{c['sheet']}!{c['cell']}" for c in candidates],
    })
    chosen = next(c for c in candidates if f"{c['sheet']}!{c['cell']}" == choice["ref"])
    return {"target": chosen}


def trace(state: InvestigationState) -> dict:
    return {
        "contributions": [
            {"cell": "H6", "label": "Gross profit", "delta": 7.2},
            {"cell": "H7", "label": "Opex", "delta": 4.8},
        ]
    }


def make_trace_node(book: Workbook) -> Callable[[InvestigationState], dict]:
    def trace_node(state: InvestigationState) -> dict:
        target = state["target"]
        ref = f"{target['sheet']}!{target['cell']}"
        prior_ref = target["prior_cell"] if "!" in target["prior_cell"] else f"{target['sheet']}!{target['prior_cell']}"
        from_period = book.column_header(prior_ref)
        if not from_period:
            raise ValueError(f"No period header for prior cell {prior_ref}")
        explanation = causal.explain_change(book, ref, from_period, target["period"])
        tree = causal.build_causal_tree(book, ref, from_period, target["period"])
        return {"contributions": explanation["contributions"], "causal_tree": tree}

    return trace_node


def stub_diagnose(state: InvestigationState) -> dict:
    number = len(state.get("hypotheses", [])) + 1
    return {
        "hypotheses": [{
            "id": f"hyp-{number}", "cell": "P&L!H7", "error_type": "typed_value",
            "claim": "Opex 2027 is a typed number, not a formula",
            "evidence_ids": [], "confidence": "high", "status": "open",
        }],
        "patch": {"cell": "P&L!H7", "old_formula": "-45.2", "new_formula": "=G7*(1+Assumptions!$C$7)", "source": "agent"},
    }


def test(state: InvestigationState) -> dict:
    return {}


def verify(state: InvestigationState) -> dict:
    if not state.get("hypotheses"):
        return {
            "verifications": [{
                "hypothesis_id": "", "before": {}, "after": {}, "checks": {},
                "verdict": "inconclusive", "reason": "no hypothesis to verify",
            }],
        }
    hypothesis = state["hypotheses"][-1]
    return {
        "verifications": [{
            "hypothesis_id": hypothesis["id"], "before": {"P&L!H8": 52.0}, "after": {"P&L!H8": 44.7},
            "checks": {"anomaly_resolved": True}, "verdict": "confirmed", "reason": "stub",
        }],
        "hypotheses": [{"id": hypothesis["id"], "status": "confirmed"}],
        "attempts": state.get("attempts", 0) + 1,
    }


def _same_cell(left: str, right: str) -> bool:
    if left == right:
        return True
    return left.endswith(f"!{right}") or right.endswith(f"!{left}")


def verification_target(state: InvestigationState) -> Hypothesis | None:
    patch = state.get("patch")
    open_hypotheses = [h for h in state.get("hypotheses", []) if h["status"] == "open"]
    if patch is not None:
        for hypothesis in open_hypotheses:
            if _same_cell(hypothesis["cell"], patch["cell"]):
                return hypothesis
    return open_hypotheses[0] if open_hypotheses else None


def make_test_node(source: SpreadsheetSource, sandbox: Sandbox) -> Callable[[InvestigationState], dict]:
    def test_node(state: InvestigationState) -> dict:
        patch = state.get("patch")
        hypothesis = verification_target(state)
        if patch is None or hypothesis is None:
            return {}
        result = run_sandbox_test(source, sandbox, state["spreadsheet_id"], patch)
        return {
            "verifications": [{
                "hypothesis_id": hypothesis["id"],
                "before": result["before"],
                "after": result["after"],
            }],
        }

    return test_node


def make_verify_node(llm: BaseChatModel, source: SpreadsheetSource) -> Callable[[InvestigationState], dict]:
    verifier = build_verifier(llm)

    def verify_node(state: InvestigationState) -> dict:
        attempts = state.get("attempts", 0) + 1
        hypothesis = verification_target(state)
        verification = None
        if hypothesis is not None:
            verification = next(
                (v for v in state.get("verifications", []) if v["hypothesis_id"] == hypothesis["id"]),
                None,
            )
        if hypothesis is None or verification is None or "before" not in verification:
            return {
                "verifications": [{
                    "hypothesis_id": hypothesis["id"] if hypothesis else "",
                    "before": {}, "after": {}, "checks": {},
                    "verdict": "inconclusive", "reason": "no sandbox result to verify",
                }],
                "attempts": attempts,
            }
        book = source.load(state["spreadsheet_id"])
        checks = deterministic_checks(book, state, verification)
        failed = [name for name, ok in checks.items() if not ok]
        if failed:
            final = "rejected"
            reason = f"deterministic checks failed: {', '.join(failed)}; the verifier was not consulted"
        else:
            verdict = invoke_verifier(verifier, state, verification, checks, book)
            final = verdict.verdict
            reason = verdict.reason
        return {
            "verifications": [{
                "hypothesis_id": hypothesis["id"],
                "checks": checks,
                "verdict": final,
                "reason": reason,
            }],
            "hypotheses": [{"id": hypothesis["id"], "status": "confirmed" if final == "confirmed" else "rejected"}],
            "attempts": attempts,
        }

    return verify_node


def explain(state: InvestigationState) -> dict:
    if state["verifications"][-1]["verdict"] == "confirmed":
        return {"report": f"Root cause found in {state['patch']['cell']}."}
    return {"report": "Inconclusive: no hypothesis survived verification."}


def human_review(state: InvestigationState) -> dict:
    decision = interrupt({"report": state["report"], "patch": state.get("patch")})
    return {"human_decision": decision}


def apply_fix(state: InvestigationState) -> dict:
    return {"corrected_copy_id": f"corrected:{state['spreadsheet_id']}"}


def make_apply_fix_node(sandbox: SandboxWithWrite) -> Callable[[InvestigationState], dict]:
    def apply_fix_node(state: InvestigationState) -> dict:
        patch = state.get("patch")
        if patch is None:
            return {"corrected_copy_id": None}
        reason = next((h["claim"] for h in state.get("hypotheses", []) if h["cell"] == patch["cell"]), "")
        log_rows = [
            ["Timestamp", "Cell", "Old formula", "New formula", "Reason"],
            [
                datetime.now(timezone.utc).isoformat(timespec="seconds"),
                patch["cell"],
                patch["old_formula"],
                patch["new_formula"],
                reason,
            ],
        ]
        return {"corrected_copy_id": sandbox.write_corrected_copy(state["spreadsheet_id"], patch, log_rows)}

    return apply_fix_node

import re
from collections.abc import Callable
from datetime import datetime, timezone

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.types import interrupt

from model_x_ray import causal
from model_x_ray.agents.verifier import build_verifier, deterministic_checks, invoke_verifier, settle_verdict
from model_x_ray.llm import invoke_with_usage, model_name_of
from model_x_ray.memory import ModelMemory
from model_x_ray.prompts import load_prompt
from model_x_ray.routing import MAX_ATTEMPTS
from model_x_ray.spreadsheet.engine import FormulaError, Workbook
from model_x_ray.spreadsheet.sandbox import Sandbox, SandboxWithWrite, run_sandbox_test
from model_x_ray.spreadsheet.source import SpreadsheetSource
from model_x_ray.state import CausalNode, Evidence, Hypothesis, InvestigationState, RunLog, TargetCell, Verification


def load_sheet(state: InvestigationState) -> dict:
    return {}


def make_load_sheet_node(book: Workbook, memory: ModelMemory | None = None) -> Callable[[InvestigationState], dict]:
    def load_sheet_node(state: InvestigationState) -> dict:
        readable = any(book.row_label(ref) and book.column_header(ref) for ref in book.cells())
        if not readable:
            raise ValueError(f"Spreadsheet {state['spreadsheet_id']!r} has no lines with a label on the left and a period header above, so Model X-Ray cannot read it")
        if memory is None:
            return {}
        return {"known_overrides": memory.overrides(state["spreadsheet_id"], book), "past_findings": memory.findings(state["spreadsheet_id"])}

    return load_sheet_node


def map_model(state: InvestigationState) -> dict:
    return {"model_map": None}


STUB_CELLS: list[TargetCell] = [
    {"sheet": "P&L", "cell": "H8", "label": "EBITDA", "period": "2027", "value": 52.0, "prior_cell": "G8", "prior_value": 40.0},
    {"sheet": "Summary", "cell": "D10", "label": "EBITDA", "period": "2027", "value": 52.0, "prior_cell": "C10", "prior_value": 40.0},
]


def find_candidates(question: str) -> list[TargetCell]:
    matches = [c for c in STUB_CELLS if c["label"] in question and c["period"] in question]
    named_sheet = [c for c in matches if c["sheet"] in question]
    return named_sheet or matches


def locate(state: InvestigationState) -> dict:
    candidates = find_candidates(state["question"]) or STUB_CELLS[:1]
    if len(candidates) == 1:
        return {"target": candidates[0], "target_choice": None}
    refs = [f"{c['sheet']}!{c['cell']}" for c in candidates]
    why = f"{len(refs)} cells match ({', '.join(refs)}); I investigated {refs[0]}, the source the other cells link to."
    return {"target": candidates[0], "target_choice": {"candidates": refs, "chosen": refs[0], "why": why}}


def trace(state: InvestigationState) -> dict:
    return {
        "contributions": [
            {"cell": "H6", "label": "Gross profit", "delta": 7.2},
            {"cell": "H7", "label": "Opex", "delta": 4.8},
        ]
    }


def _suspicious_cells(tree: CausalNode) -> set[str]:
    cells = {tree["cell"]} if tree["suspicious"] else set()
    for child in tree["children"]:
        cells |= _suspicious_cells(child)
    return cells


def make_trace_node(book: Workbook) -> Callable[[InvestigationState], dict]:
    def trace_node(state: InvestigationState) -> dict:
        target = state["target"]
        ref = f"{target['sheet']}!{target['cell']}"
        if target.get("mode") in ("table", "review"):
            start = len(state.get("evidence", []))
            text = f"{target['label']} = {target['value']:.2f}: {target['finding']}"
            if target.get("expected_formula"):
                text += f"; with {target['expected_formula']} it would be {target['prior_value']:.2f}"
            tree = {"cell": ref, "label": target["label"], "value_before": target["prior_value"], "value_after": target["value"], "delta": target["value"] - target["prior_value"], "share_of_change": 1.0, "suspicious": True, "children": []}
            return {"contributions": [], "causal_tree": tree, "evidence": [{"id": f"ev-{start + 1}", "cell": ref, "kind": "anomaly", "text": text}]}
        prior_ref = target["prior_cell"] if "!" in target["prior_cell"] else f"{target['sheet']}!{target['prior_cell']}"
        from_period = book.column_header(prior_ref) or ""
        try:
            if not from_period:
                raise ValueError(f"No period header for prior cell {prior_ref}")
            explanation = causal.explain_change(book, ref, from_period, target["period"])
            tree = causal.build_causal_tree(book, ref, from_period, target["period"])
        except (ValueError, FormulaError):
            explanation = {"contributions": []}
            tree = {"cell": ref, "label": target["label"], "value_before": target["prior_value"], "value_after": target["value"], "delta": target["value"] - target["prior_value"], "share_of_change": 1.0, "suspicious": False, "children": []}
        suspicious = _suspicious_cells(tree)
        start = len(state.get("evidence", []))
        records = [
            {
                "id": f"ev-{start + 1}",
                "cell": ref,
                "kind": "anomaly",
                "text": (
                    f"{target['label']} {target['period']} = {target['value']:.2f}"
                    f" versus {target['prior_cell']} = {target['prior_value']:.2f}"
                ),
            },
            *[
                {
                    "id": f"ev-{start + index + 2}",
                    "cell": contribution["cell"],
                    "kind": "anomaly" if contribution["cell"] in suspicious else "expected_pattern",
                    "text": f"{contribution['label']} contributes {contribution['delta']:+.2f}",
                }
                for index, contribution in enumerate(explanation["contributions"])
            ],
        ]
        return {
            "contributions": explanation["contributions"],
            "causal_tree": tree,
            "evidence": records,
        }

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
        try:
            result = run_sandbox_test(source, sandbox, state["spreadsheet_id"], patch)
        except FormulaError as error:
            return {"verifications": [{"hypothesis_id": hypothesis["id"], "before": {}, "after": {}, "error": str(error)}]}
        return {
            "verifications": [{
                "hypothesis_id": hypothesis["id"],
                "before": result["before"],
                "after": result["after"],
            }],
        }

    return test_node


def sandbox_proof(state: InvestigationState, verification: Verification) -> Evidence:
    target = state["target"]
    target_ref = f"{target['sheet']}!{target['cell']}"
    patched = state["patch"]["cell"]
    shown = target_ref if target_ref in verification["before"] else patched
    before = verification["before"].get(shown)
    after = verification["after"].get(shown)
    change = f"{before:.2f} -> {after:.2f}" if isinstance(before, (int, float)) and isinstance(after, (int, float)) else f"{before} -> {after}"
    return {
        "id": f"ev-{len(state.get('evidence', [])) + 1}",
        "cell": patched,
        "kind": "verification",
        "text": f"{shown} {change} in a sandbox copy after patching {patched}",
    }


def make_verify_node(llm: BaseChatModel | None, source: SpreadsheetSource) -> Callable[[InvestigationState], dict]:
    verifier = build_verifier(llm) if llm is not None else None
    model_name = model_name_of(llm) if llm is not None else None

    def verify_node(state: InvestigationState) -> dict:
        records: list[RunLog] = []
        attempts = state.get("attempts", 0) + 1
        patch = state.get("patch")
        hypothesis = verification_target(state)
        verification = None
        if hypothesis is not None:
            verification = next(
                (v for v in state.get("verifications", []) if v["hypothesis_id"] == hypothesis["id"]),
                None,
            )
        if verification is not None and verification.get("error"):
            return {
                "verifications": [{
                    "hypothesis_id": hypothesis["id"], "before": {}, "after": {}, "checks": {},
                    "verdict": "rejected", "reason": f"the fix could not be calculated on the copy: {verification['error']}",
                }],
                "hypotheses": [{"id": hypothesis["id"], "status": "rejected"}],
                "attempts": attempts,
            }
        if hypothesis is None or patch is None or verification is None or "before" not in verification or not verification["before"]:
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
        elif verifier is None:
            final = "confirmed"
            reason = "deterministic checks passed; no second opinion configured"
        else:
            verdict, records = invoke_verifier(verifier, state, verification, checks, book, model=model_name)
            final, reason, claims_hold = settle_verdict(verdict, book, state["patch"], verification["after"])
            if claims_hold is not None:
                checks = {**checks, "verifier_claims_hold": claims_hold}
        return {
            "verifications": [{
                "hypothesis_id": hypothesis["id"],
                "checks": checks,
                "verdict": final,
                "reason": reason,
            }],
            "hypotheses": [{"id": hypothesis["id"], "status": "confirmed" if final == "confirmed" else "rejected"}],
            "evidence": [sandbox_proof(state, verification)] if final == "confirmed" else [],
            "attempts": attempts,
            "run_log": records,
        }

    return verify_node


def explain(state: InvestigationState) -> dict:
    return with_choice(state, stub_report(state))


def stub_report(state: InvestigationState) -> dict:
    if state["verifications"][-1]["verdict"] == "confirmed":
        return {"report": f"Root cause found in {state['patch']['cell']}."}
    return {"report": "Inconclusive: no hypothesis survived verification."}


def _citations(state: InvestigationState, hypothesis: Hypothesis | None) -> list[str]:
    evidence = state.get("evidence", [])
    if hypothesis and hypothesis["evidence_ids"]:
        return list(hypothesis["evidence_ids"])
    if hypothesis:
        same_cell = [record["id"] for record in evidence if record["cell"] == hypothesis["cell"] and record["kind"] != "verification"]
        if same_cell:
            return same_cell
    return [record["id"] for record in evidence if record["kind"] == "anomaly"][:1]


def joined(parts: list[str]) -> str:
    return parts[0] if len(parts) == 1 else f"{', '.join(parts[:-1])} and {parts[-1]}"


CHECK_FAILURES = {
    "anomaly_resolved": "the fix did not remove the unusual change",
    "dependents_consistent": "the fix broke cells that depend on it",
    "pattern_restored": "the fix did not match the formulas next to it",
}


def no_error_report(state: InvestigationState) -> str:
    movement = movement_and_drivers(state)
    return f"No error found. {movement}." if movement else "No error found."


def why_unproven(verification: Verification | None) -> str:
    if verification is None:
        return f"it was not tested before the agent's {MAX_ATTEMPTS} attempts ran out"
    failed = [CHECK_FAILURES[name] for name, ok in verification.get("checks", {}).items() if not ok and name in CHECK_FAILURES]
    if failed:
        return joined(failed)
    if verification.get("verdict") == "rejected":
        return f"the independent check rejected the fix: {verification.get('reason', '').rstrip('.')}"
    return "it could not be tested on a copy"


def unproven_report(state: InvestigationState) -> str:
    verifications = {v["hypothesis_id"]: v for v in state.get("verifications", [])}
    suspects: dict[str, str] = {}
    tested: set[str] = set()
    for hypothesis in state.get("hypotheses", []):
        verification = verifications.get(hypothesis["id"])
        if hypothesis["status"] == "confirmed" or (hypothesis["cell"] in tested and verification is None):
            continue
        if verification is not None:
            tested.add(hypothesis["cell"])
        kind = hypothesis["error_type"].replace("_", " ")
        suspects[hypothesis["cell"]] = f"{hypothesis['cell']} ({kind}), because {why_unproven(verification)}"
    count = len(suspects)
    movement = movement_and_drivers(state)
    report = f"No confirmed error. {movement}. " if movement else "No confirmed error. "
    report += f"The agent checked {count} suspect{'s' if count != 1 else ''} but could not prove {'it' if count == 1 else 'any of them'}: {'; '.join(suspects.values())}. "
    return report + f"Nothing was changed; review {'this cell' if count == 1 else 'these cells'} before relying on the number."


def target_statement(target: TargetCell) -> str:
    if target.get("mode") in ("table", "review"):
        statement = f"{target['label']} ({target['sheet']}!{target['cell']}) is {target['value']:.2f}: {target['finding']}"
        return statement + (f", which gives {target['prior_value']:.2f}" if target.get("expected_formula") else "")
    return f"{target['label']} {target['period']} moved from {target['prior_value']:.2f} to {target['value']:.2f}"


def movement_and_drivers(state: InvestigationState) -> str:
    target = state.get("target")
    if not target:
        return ""
    evidence = state.get("evidence", [])
    target_ref = f"{target['sheet']}!{target['cell']}"
    target_id = next((e["id"] for e in evidence if e["cell"] == target_ref and e["kind"] == "anomaly"), None)
    report = target_statement(target)
    if target_id:
        report += f" ({target_id})"
    drivers = []
    for contribution in sorted(state.get("contributions", []), key=lambda c: abs(c["delta"]), reverse=True)[:3]:
        cited = next((e["id"] for e in evidence if e["cell"] == contribution["cell"] and e["kind"] != "verification"), None)
        detail = f"{contribution['cell']}, {contribution['delta']:+.2f}" + (f", {cited}" if cited else "")
        drivers.append(f"{contribution['label']} ({detail})")
    if drivers:
        report += f"; the change comes from {joined(drivers)}"
    return report


def narrative_brief(state: InvestigationState, hypothesis: Hypothesis | None, verification: Verification) -> str:
    lines = [f"Question: {state.get('question', '')}"]
    target = state.get("target")
    if target:
        lines.append(
            f"Target: {target['label']} {target['period']} moved from {target['prior_value']} to {target['value']} ({target['sheet']}!{target['cell']})"
        )
    if hypothesis:
        lines.append(f"Hypothesis: {hypothesis['cell']} ({hypothesis['error_type']}): {hypothesis['claim']}")
    patch = state.get("patch")
    if patch:
        lines.append(f"Patch: {patch['cell']}: {patch['old_formula']} -> {patch['new_formula']}")
    checks = verification.get("checks", {})
    check_text = ", ".join(f"{name}={str(value).lower()}" for name, value in checks.items())
    line = f"Verification: {verification['verdict']}"
    if verification.get("reason"):
        line += f": {verification['reason']}"
    if check_text:
        line += f"; checks: {check_text}"
    lines.append(line)
    lines.append("Evidence records you may cite as (ev-N):")
    for record in state.get("evidence", []):
        lines.append(f"{record['id']} | {record['cell']} | {record['kind']} | {record['text']}")
    return "\n".join(lines)


def with_choice(state: InvestigationState, update: dict) -> dict:
    choice = state.get("target_choice")
    if not choice:
        return update
    return {**update, "report": f"{choice['why']} {update['report']}"}


def make_explain_node(llm: BaseChatModel | None = None) -> Callable[[InvestigationState], dict]:
    def explain_node(state: InvestigationState) -> dict:
        return with_choice(state, explain_report(state))

    def explain_report(state: InvestigationState) -> dict:
        if not state.get("hypotheses"):
            return {"report": no_error_report(state)}
        verifications = state.get("verifications", [])
        latest = verifications[-1] if verifications else None
        if latest is None or latest["verdict"] != "confirmed":
            return {"report": unproven_report(state)}
        hypothesis = next(
            (h for h in state.get("hypotheses", []) if h["id"] == latest["hypothesis_id"]),
            None,
        )
        target = state.get("target")
        target_ref = f"{target['sheet']}!{target['cell']}" if target else None
        target_record = next(
            (e for e in state.get("evidence", []) if target_ref and e["cell"] == target_ref and e["kind"] == "anomaly"),
            None,
        )
        parts = []
        if target and target_record:
            parts.append(f"{target_statement(target)} ({target_record['id']}).")
        patch = state.get("patch")
        cell = patch["cell"] if patch else (hypothesis["cell"] if hypothesis else "")
        claim = hypothesis["claim"] if hypothesis else "the patch held in the sandbox"
        citations = _citations(state, hypothesis)
        if citations:
            parts.append(f"Root cause found in {cell}: {claim} (evidence: {', '.join(citations)}).")
        else:
            parts.append(f"Root cause found in {cell}: {claim}.")
        proofs = [e for e in state.get("evidence", []) if e["kind"] == "verification" and e["cell"] == cell]
        if proofs:
            parts.append(f"The fix was tested: {proofs[-1]['text']} ({proofs[-1]['id']}).")
        report = " ".join(parts)
        if llm is None:
            return {"report": report}
        narrative, records = invoke_with_usage(
            llm,
            [
                SystemMessage(content=load_prompt("explain")),
                HumanMessage(content=narrative_brief(state, hypothesis, latest)),
            ],
            role="explain",
            model=model_name_of(llm),
        )
        text = narrative.content if isinstance(narrative.content, str) else ""
        cited = re.findall(r"ev-\d+", text)
        known = {record["id"] for record in state.get("evidence", [])}
        if cited and set(cited) <= known:
            return {"report": text, "run_log": records}
        return {"report": report, "run_log": records}

    return explain_node


def human_review(state: InvestigationState) -> dict:
    decision = interrupt({"report": state["report"], "patch": state.get("patch")})
    update: dict = {"human_decision": decision}
    if decision.get("patch"):
        update["patch"] = {**decision["patch"], "source": "human"}
    if decision.get("action") == "edit":
        verifications = state.get("verifications", [])
        reopen_id = verifications[-1]["hypothesis_id"] if verifications else None
        if reopen_id and reopen_id in {h["id"] for h in state.get("hypotheses", [])}:
            update["hypotheses"] = [{"id": reopen_id, "status": "open"}]
    return update


def make_human_review_node(book: Workbook, memory: ModelMemory | None) -> Callable[[InvestigationState], dict]:
    def human_review_node(state: InvestigationState) -> dict:
        update = human_review(state)
        if memory is not None:
            remember_decision(memory, book, state, update["human_decision"])
        return update

    return human_review_node


def remember_decision(memory: ModelMemory, book: Workbook, state: InvestigationState, decision: dict) -> None:
    patch = state.get("patch")
    hypotheses = state.get("hypotheses", [])
    cell = patch["cell"] if patch else (hypotheses[-1]["cell"] if hypotheses else None)
    if cell is None:
        return
    if decision.get("action") == "reject" and decision.get("intentional"):
        memory.add_override(state["spreadsheet_id"], {"cell": cell, "content": str(book.raw(cell)), "reason": decision.get("reason", "")})
    if decision.get("action") == "approve" and patch is not None:
        error_type = next((h["error_type"] for h in hypotheses if h["cell"] == cell and h["status"] == "confirmed"), "")
        memory.add_finding(state["spreadsheet_id"], {"cell": cell, "error_type": error_type, "old_formula": patch["old_formula"], "new_formula": patch["new_formula"]})


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

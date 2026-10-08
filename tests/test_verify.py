import json
from pathlib import Path

import pytest

from test_investigator import ScriptedDiagnosis

from model_x_ray.graph import run_investigation
from model_x_ray.prompts import load_prompt
from model_x_ray.spreadsheet.source import XlsxSource

QUESTION = "Why did EBITDA 2027 jump on the P&L sheet?"


def test_verify_confirms_a_good_patch_and_sends_a_fixed_evidence_package(
    demo_workbook_path: Path, engine_sandbox, scripted_verdict,
) -> None:
    model = ScriptedDiagnosis(turns=[(["P&L!H7"], "P&L!H7")])
    graph = run_investigation(
        model, "demo", XlsxSource({"demo": demo_workbook_path}), engine_sandbox, verifier=scripted_verdict,
    )
    config = {"configurable": {"thread_id": "verify-confirmed"}}

    graph.invoke({"spreadsheet_id": "demo", "question": QUESTION}, config)
    state = graph.get_state(config).values

    assert graph.get_state(config).next == ("human_review",)
    assert state["attempts"] == 1
    assert state["hypotheses"][0]["status"] == "confirmed"
    record = state["verifications"][-1]
    assert record["hypothesis_id"] == "hyp-1"
    assert record["checks"] == {"anomaly_resolved": True, "dependents_consistent": True, "pattern_restored": True}
    assert record["verdict"] == "confirmed"
    assert record["reason"] == "the sandbox numbers hold"
    assert record["before"]["P&L!H8"] == pytest.approx(52.01, abs=0.01)
    assert record["after"]["P&L!H8"] == pytest.approx(44.73, abs=0.01)

    package = json.loads(scripted_verdict.human[0])
    assert set(package) == {"question", "target", "patch", "formulas", "sandbox", "deterministic_checks"}
    assert "hypotheses" not in package and "messages" not in package
    assert package["sandbox"]["after"]["P&L!H8"] == pytest.approx(44.73, abs=0.01)
    assert package["patch"]["old_formula"] == "-45.2"
    assert package["formulas"]["P&L!H8"] == "=H6+H7"
    assert scripted_verdict.system[0] == load_prompt("verifier")
    assert "disprove" in scripted_verdict.system[0].lower()


def test_verify_rejects_then_confirms_across_the_retry_loop(
    demo_workbook_path: Path, engine_sandbox, scripted_verdict,
) -> None:
    model = ScriptedDiagnosis(turns=[
        (["P&L!H7", "P&L!H5"], "P&L!H7"),
        (["P&L!H7"], "P&L!H7"),
    ])
    scripted_verdict.verdicts = [
        ("rejected", "the growth still looks implausible"),
        ("confirmed", "the numbers now hold"),
    ]
    graph = run_investigation(
        model, "demo", XlsxSource({"demo": demo_workbook_path}), engine_sandbox, verifier=scripted_verdict,
    )
    config = {"configurable": {"thread_id": "verify-retry"}}

    graph.invoke({"spreadsheet_id": "demo", "question": QUESTION}, config)
    state = graph.get_state(config).values

    assert graph.get_state(config).next == ("human_review",)
    assert "Root cause found in P&L!H7:" in state["report"]
    assert state["attempts"] == 2
    assert [(h["id"], h["cell"], h["status"]) for h in state["hypotheses"]] == [
        ("hyp-1", "P&L!H7", "rejected"),
        ("hyp-2", "P&L!H5", "open"),
        ("hyp-3", "P&L!H7", "confirmed"),
    ]
    assert [(v["hypothesis_id"], v["verdict"]) for v in state["verifications"]] == [
        ("hyp-1", "rejected"),
        ("hyp-3", "confirmed"),
    ]
    assert "Already rejected, do not propose again: P&L!H7" in model.briefs[1]
    assert len(scripted_verdict.human) == 2


def test_verify_goes_inconclusive_when_every_attempt_is_rejected(
    demo_workbook_path: Path, engine_sandbox, scripted_verdict,
) -> None:
    model = ScriptedDiagnosis(turns=[
        (["P&L!H7", "P&L!H5", "P&L!H6"], "P&L!H7"),
        (["P&L!H7"], "P&L!H7"),
        (["P&L!H7"], "P&L!H7"),
    ])
    scripted_verdict.verdicts = [("rejected", "the numbers still look wrong")]
    graph = run_investigation(
        model, "demo", XlsxSource({"demo": demo_workbook_path}), engine_sandbox, verifier=scripted_verdict,
    )
    config = {"configurable": {"thread_id": "verify-exhausted"}}

    graph.invoke({"spreadsheet_id": "demo", "question": QUESTION}, config)
    state = graph.get_state(config).values

    assert graph.get_state(config).next == ("human_review",)
    assert state["attempts"] == 3
    assert "Inconclusive" in state["report"]
    assert [(h["id"], h["status"]) for h in state["hypotheses"]] == [
        ("hyp-1", "rejected"),
        ("hyp-2", "open"),
        ("hyp-3", "open"),
        ("hyp-4", "rejected"),
        ("hyp-5", "rejected"),
    ]
    assert [(v["hypothesis_id"], v["verdict"]) for v in state["verifications"]] == [
        ("hyp-1", "rejected"),
        ("hyp-4", "rejected"),
        ("hyp-5", "rejected"),
    ]


def test_verify_cannot_confirm_a_patch_that_fails_the_deterministic_checks(
    demo_workbook_path: Path, engine_sandbox, scripted_verdict,
) -> None:
    model = ScriptedDiagnosis(turns=[(["P&L!H7"], "P&L!H7", "=H6+G7")])
    scripted_verdict.verdicts = [("confirmed", "trust the fix")]
    graph = run_investigation(
        model, "demo", XlsxSource({"demo": demo_workbook_path}), engine_sandbox, verifier=scripted_verdict,
    )
    config = {"configurable": {"thread_id": "verify-forced-reject"}}

    graph.invoke({"spreadsheet_id": "demo", "question": QUESTION}, config)
    state = graph.get_state(config).values

    assert graph.get_state(config).next == ("human_review",)
    record = state["verifications"][-1]
    assert record["checks"]["pattern_restored"] is False
    assert record["checks"]["anomaly_resolved"] is False
    assert record["checks"]["dependents_consistent"] is True
    assert record["verdict"] == "rejected"
    assert "deterministic checks failed" in record["reason"]
    assert "pattern_restored" in record["reason"]
    assert state["hypotheses"][0]["status"] == "rejected"
    assert "Inconclusive" in state["report"]
    assert scripted_verdict.human == []

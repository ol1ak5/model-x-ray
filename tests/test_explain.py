import re
from pathlib import Path

from langgraph.types import Command
from test_investigator import OutlierScanner, ScriptedDiagnosis

from model_x_ray.graph import run_investigation
from model_x_ray.spreadsheet.source import XlsxSource

QUESTION = "Why did EBITDA 2027 jump on the P&L sheet?"


def test_trace_writes_evidence_for_the_target_and_every_contribution(
    demo_workbook_path: Path, engine_sandbox, scripted_verdict,
) -> None:
    model = ScriptedDiagnosis(turns=[(["P&L!H7"], "P&L!H7")])
    graph = run_investigation(
        model, "demo", XlsxSource({"demo": demo_workbook_path}), engine_sandbox, verifier=scripted_verdict,
    )
    config = {"configurable": {"thread_id": "trace-evidence"}}

    graph.invoke({"spreadsheet_id": "demo", "question": QUESTION}, config)
    state = graph.get_state(config).values

    assert [(e["id"], e["cell"], e["kind"]) for e in state["evidence"]] == [
        ("ev-1", "P&L!H8", "anomaly"),
        ("ev-2", "P&L!H6", "expected_pattern"),
        ("ev-3", "P&L!H7", "anomaly"),
        ("ev-4", "P&L!H7", "verification"),
    ]
    assert "EBITDA 2027E = 52.01" in state["evidence"][0]["text"]
    assert "G8 = 40.03" in state["evidence"][0]["text"]
    assert "Gross profit" in state["evidence"][1]["text"]
    assert "+7.20" in state["evidence"][1]["text"]
    assert "Opex" in state["evidence"][2]["text"]
    assert "+4.78" in state["evidence"][2]["text"]


def test_explain_cites_only_ids_that_resolve_in_state(
    demo_workbook_path: Path, engine_sandbox, scripted_verdict,
) -> None:
    model = ScriptedDiagnosis(turns=[(["P&L!H7"], "P&L!H7")])
    graph = run_investigation(
        model, "demo", XlsxSource({"demo": demo_workbook_path}), engine_sandbox, verifier=scripted_verdict,
    )
    config = {"configurable": {"thread_id": "explain-citations"}}

    graph.invoke({"spreadsheet_id": "demo", "question": QUESTION}, config)
    state = graph.get_state(config).values

    report = state["report"]
    assert "Root cause found in P&L!H7" in report
    assert "typed number, not a formula" in report
    cited = re.findall(r"ev-\d+", report)
    assert cited, "the confirmed report must cite evidence"
    known = {e["id"] for e in state["evidence"]}
    assert set(cited) <= known
    assert "ev-1" in cited, "the target anomaly backs the movement claim"
    assert "ev-3" in cited, "the H7 evidence backs the root cause claim"
    assert "ev-4" in cited, "the sandbox proof backs the fix"
    assert state["evidence"][3]["text"] == "P&L!H8 52.01 -> 44.73 in a sandbox copy after patching P&L!H7"
    assert report.endswith(".")


def test_a_clean_answer_says_no_error_found_and_names_the_drivers_with_evidence(
    demo_workbook_with_override_note: Path, engine_sandbox,
) -> None:
    graph = run_investigation(
        OutlierScanner(), "demo", XlsxSource({"demo": demo_workbook_with_override_note}), engine_sandbox,
    )
    config = {"configurable": {"thread_id": "explain-no-error"}}

    graph.invoke({"spreadsheet_id": "demo", "question": QUESTION}, config)
    state = graph.get_state(config).values

    assert state["report"] == (
        "No error found. EBITDA 2027E moved from 40.03 to 52.01 (ev-1); the change comes from "
        "Gross profit (P&L!H6, +7.20, ev-2) and Opex (P&L!H7, +4.78, ev-3)."
    )
    known = {e["id"] for e in state["evidence"]}
    assert set(re.findall(r"ev-\d+", state["report"])) <= known
    assert "Inconclusive" not in state["report"]


def test_an_unproven_suspect_is_explained_not_reported_as_a_failure(
    demo_workbook_path: Path, engine_sandbox, scripted_verdict,
) -> None:
    model = ScriptedDiagnosis(turns=[(["P&L!H7"], "P&L!H7")])
    scripted_verdict.verdicts = [("rejected", "not convinced")]
    graph = run_investigation(
        model, "demo", XlsxSource({"demo": demo_workbook_path}), engine_sandbox, verifier=scripted_verdict,
    )
    config = {"configurable": {"thread_id": "explain-inconclusive"}}

    graph.invoke({"spreadsheet_id": "demo", "question": QUESTION}, config)
    state = graph.get_state(config).values

    assert state["report"] == (
        "No confirmed error. EBITDA 2027E moved from 40.03 to 52.01 (ev-1); the change comes from "
        "Gross profit (P&L!H6, +7.20, ev-2) and Opex (P&L!H7, +4.78, ev-3). "
        "The agent checked 1 suspect but could not prove it: P&L!H7 (typed value), because the independent check rejected the fix: not convinced. Checked by the engine: P&L!H8 is 44.73 after the fix, as stated. "
        "Nothing was changed; review this cell before relying on the number."
    )
    assert set(re.findall(r"ev-\d+", state["report"])) <= {e["id"] for e in state["evidence"]}
    assert state["evidence"], "trace evidence exists even when the run fails"
    assert [e for e in state["evidence"] if e["kind"] == "verification"] == []


def test_a_human_edit_is_proven_again_with_a_new_verification_record(
    demo_workbook_path: Path, engine_sandbox, scripted_verdict,
) -> None:
    model = ScriptedDiagnosis(turns=[(["P&L!H7"], "P&L!H7")])
    graph = run_investigation(
        model, "demo", XlsxSource({"demo": demo_workbook_path}), engine_sandbox, verifier=scripted_verdict,
    )
    config = {"configurable": {"thread_id": "edit-reverified"}}

    graph.invoke({"spreadsheet_id": "demo", "question": QUESTION}, config)
    edited = {"cell": "P&L!H7", "old_formula": "-45.2", "new_formula": "=G7*(1+Assumptions!$C$7)"}
    graph.invoke(Command(resume={"action": "edit", "reason": "same fix, written by me", "patch": edited}), config)
    state = graph.get_state(config).values

    ids = [e["id"] for e in state["evidence"]]
    assert len(ids) == len(set(ids))
    proofs = [e["id"] for e in state["evidence"] if e["kind"] == "verification"]
    assert proofs == ["ev-4", "ev-5"]
    assert "ev-5" in state["report"] and "ev-4" not in state["report"]
    assert graph.get_state(config).next == ("human_review",)


def test_a_cell_suspected_twice_is_reported_with_its_tested_attempt(
    demo_workbook_path: Path, engine_sandbox, scripted_verdict,
) -> None:
    model = ScriptedDiagnosis(turns=[
        (["P&L!H7", "P&L!H5"], "P&L!H7"),
        (["P&L!H5"], "P&L!H5", "=-H4*Assumptions!$C$6"),
        (["P&L!H4"], "P&L!H4", "=G4*(1+Assumptions!$C$5)"),
    ])
    scripted_verdict.verdicts = [("rejected", "the growth still looks implausible")]
    graph = run_investigation(
        model, "demo", XlsxSource({"demo": demo_workbook_path}), engine_sandbox, verifier=scripted_verdict,
    )
    config = {"configurable": {"thread_id": "explain-suspected-twice"}}

    graph.invoke({"spreadsheet_id": "demo", "question": QUESTION}, config)
    report = graph.get_state(config).values["report"]

    assert "The agent checked 3 suspects but could not prove any of them:" in report
    assert "P&L!H7 (typed value), because the independent check rejected the fix: the growth still looks implausible. Checked by the engine: P&L!H8 is 44.73 after the fix, as stated;" in report
    assert "P&L!H5 (typed value), because the fix did not remove the unusual change;" in report
    assert "not tested" not in report

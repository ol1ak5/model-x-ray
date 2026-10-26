import re
from pathlib import Path

from conftest import ScriptedNarrative
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
    assert state["evidence"][3]["text"] == "P&L!H8 from 52.01 to 44.73 in a sandbox copy after patching P&L!H7"
    assert report.endswith(".")


def test_a_confirmed_run_is_explained_by_the_narrative_model_with_valid_citations(
    demo_workbook_path: Path, engine_sandbox, scripted_verdict,
) -> None:
    model = ScriptedDiagnosis(turns=[(["P&L!H7"], "P&L!H7")])
    narrative = ScriptedNarrative(
        text="EBITDA 2027E moved from 40.03 to 52.01 (ev-1). "
        "P&L!H7 held a typed number where the row uses formulas (ev-3). "
        "Patching it to the row formula brought the result back in the sandbox (ev-4)."
    )
    graph = run_investigation(
        model, "demo", XlsxSource({"demo": demo_workbook_path}), engine_sandbox,
        verifier=scripted_verdict, explainer=narrative,
    )
    config = {"configurable": {"thread_id": "narrative-confirmed"}}

    graph.invoke({"spreadsheet_id": "demo", "question": QUESTION}, config)
    state = graph.get_state(config).values

    assert state["report"] == narrative.text
    assert set(re.findall(r"ev-\d+", state["report"])) <= {e["id"] for e in state["evidence"]}
    assert len(narrative.briefs) == 1
    brief = narrative.briefs[0]
    assert QUESTION in brief
    target = state["target"]
    assert f"{target['prior_value']}" in brief and f"{target['value']}" in brief
    assert "P&L!H7" in brief
    assert "anomaly_resolved" in brief and "pattern_restored" in brief
    for record in state["evidence"]:
        assert record["id"] in brief and record["text"] in brief
    assert "run_log" not in brief and "attempts" not in brief


def test_an_unknown_citation_falls_back_to_the_deterministic_report(
    demo_workbook_path: Path, engine_sandbox, scripted_verdict,
) -> None:
    model = ScriptedDiagnosis(turns=[(["P&L!H7"], "P&L!H7")])
    narrative = ScriptedNarrative(text="EBITDA jumped because of the weather (ev-99). Ask the desk about it (ev-4).")
    graph = run_investigation(
        model, "demo", XlsxSource({"demo": demo_workbook_path}), engine_sandbox,
        verifier=scripted_verdict, explainer=narrative,
    )
    config = {"configurable": {"thread_id": "narrative-unknown-id"}}

    graph.invoke({"spreadsheet_id": "demo", "question": QUESTION}, config)
    state = graph.get_state(config).values

    report = state["report"]
    assert narrative.text not in report
    assert "Root cause found in P&L!H7" in report
    cited = re.findall(r"ev-\d+", report)
    assert cited and set(cited) <= {e["id"] for e in state["evidence"]}


def test_a_narrative_that_leaks_its_reasoning_falls_back_to_the_deterministic_report(
    demo_workbook_path: Path, engine_sandbox, scripted_verdict,
) -> None:
    model = ScriptedDiagnosis(turns=[(["P&L!H7"], "P&L!H7")])
    leaked = (
        "Here's a thinking process:\n\n"
        "1.  **Analyze the Request:**\n"
        "    - I need to write a final report (3-6 sentences of plain prose).\n"
        "    - Numbers first: open with what moved, from which value to which value.\n"
        "    - Cite evidence inline as (ev-N) immediately after the claim it supports.\n\n"
        "2.  **Draft the report:**\n"
        "    - EBITDA 2027E moved from 40.03 to 52.01 (ev-1).\n"
        "    - The Opex cell held a typed number where the row uses formulas (ev-3).\n\n"
        "EBITDA 2027E moved from 40.03 to 52.01 (ev-1). P&L!H7 held a typed number "
        "where the row uses formulas (ev-3). Patching it to the row formula brought the "
        "result back in the sandbox (ev-4)."
    )
    narrative = ScriptedNarrative(text=leaked)
    graph = run_investigation(
        model, "demo", XlsxSource({"demo": demo_workbook_path}), engine_sandbox,
        verifier=scripted_verdict, explainer=narrative,
    )
    config = {"configurable": {"thread_id": "narrative-leaked-reasoning"}}

    graph.invoke({"spreadsheet_id": "demo", "question": QUESTION}, config)
    state = graph.get_state(config).values

    report = state["report"]
    assert len(narrative.briefs) == 1
    assert report == (
        "EBITDA 2027E moved from 40.03 to 52.01 (ev-1). P&L!H7 held a typed number "
        "where the row uses formulas (ev-3). Patching it to the row formula brought the "
        "result back in the sandbox (ev-4)."
    )
    assert "thinking process" not in report.lower()
    assert "**" not in report
    assert set(re.findall(r"ev-\d+", report)) <= {e["id"] for e in state["evidence"]}


def test_a_narrative_that_is_all_scaffolding_falls_back_to_the_deterministic_report(
    demo_workbook_path: Path, engine_sandbox, scripted_verdict,
) -> None:
    model = ScriptedDiagnosis(turns=[(["P&L!H7"], "P&L!H7")])
    narrative = ScriptedNarrative(
        text=(
            "Here's a thinking process:\n\n"
            "1.  **Analyze the Request:**\n"
            "    - Numbers first: open with what moved (ev-1).\n"
            "    - Cite evidence inline as (ev-N) (ev-3).\n\n"
            "2.  **Check the constraints:**\n"
            "    - Do not add arithmetic that is not in the brief (ev-4).\n"
        )
    )
    graph = run_investigation(
        model, "demo", XlsxSource({"demo": demo_workbook_path}), engine_sandbox,
        verifier=scripted_verdict, explainer=narrative,
    )
    config = {"configurable": {"thread_id": "narrative-all-scaffolding"}}

    graph.invoke({"spreadsheet_id": "demo", "question": QUESTION}, config)
    state = graph.get_state(config).values

    report = state["report"]
    assert "Root cause found in P&L!H7" in report
    assert "thinking process" not in report.lower()
    assert report.endswith(".")


def test_a_narrative_without_citations_falls_back_to_the_deterministic_report(
    demo_workbook_path: Path, engine_sandbox, scripted_verdict,
) -> None:
    model = ScriptedDiagnosis(turns=[(["P&L!H7"], "P&L!H7")])
    narrative = ScriptedNarrative(text="The fix looks right and the numbers now add up nicely.")
    graph = run_investigation(
        model, "demo", XlsxSource({"demo": demo_workbook_path}), engine_sandbox,
        verifier=scripted_verdict, explainer=narrative,
    )
    config = {"configurable": {"thread_id": "narrative-no-citations"}}

    graph.invoke({"spreadsheet_id": "demo", "question": QUESTION}, config)
    state = graph.get_state(config).values

    report = state["report"]
    assert narrative.text not in report
    assert "Root cause found in P&L!H7" in report
    assert re.findall(r"ev-\d+", report), "the deterministic report still cites its evidence"


def test_a_narrative_that_stops_mid_sentence_falls_back_to_the_deterministic_report(
    demo_workbook_path: Path, engine_sandbox, scripted_verdict,
) -> None:
    model = ScriptedDiagnosis(turns=[(["P&L!H7"], "P&L!H7")])
    narrative = ScriptedNarrative(
        text="Key numbers: EBITDA 2027E moved from 40.03 to 52.01 (ev-1). After patch, P&L!H8 moved from 52.01 to 44.73"
    )
    graph = run_investigation(
        model, "demo", XlsxSource({"demo": demo_workbook_path}), engine_sandbox,
        verifier=scripted_verdict, explainer=narrative,
    )
    config = {"configurable": {"thread_id": "narrative-cut-off"}}

    graph.invoke({"spreadsheet_id": "demo", "question": QUESTION}, config)
    state = graph.get_state(config).values

    report = state["report"]
    assert narrative.text not in report
    assert "Root cause found in P&L!H7" in report
    assert report.endswith(".")


def test_a_narrative_that_never_names_the_patched_cell_falls_back_to_the_deterministic_report(
    demo_workbook_path: Path, engine_sandbox, scripted_verdict,
) -> None:
    model = ScriptedDiagnosis(turns=[(["P&L!H7"], "P&L!H7")])
    narrative = ScriptedNarrative(
        text="EBITDA 2027E moved from 40.03 to 52.01 (ev-1). The cell held a typed number where the row uses formulas (ev-3)."
    )
    graph = run_investigation(
        model, "demo", XlsxSource({"demo": demo_workbook_path}), engine_sandbox,
        verifier=scripted_verdict, explainer=narrative,
    )
    config = {"configurable": {"thread_id": "narrative-no-cell"}}

    graph.invoke({"spreadsheet_id": "demo", "question": QUESTION}, config)
    state = graph.get_state(config).values

    assert "Root cause found in P&L!H7" in state["report"]


def test_an_unconfirmed_run_never_calls_the_narrative_model(
    demo_workbook_path: Path, engine_sandbox, scripted_verdict,
) -> None:
    model = ScriptedDiagnosis(turns=[(["P&L!H7"], "P&L!H7")])
    scripted_verdict.verdicts = [("rejected", "the numbers do not hold")]
    narrative = ScriptedNarrative(text="Anything the model would have said.")
    graph = run_investigation(
        model, "demo", XlsxSource({"demo": demo_workbook_path}), engine_sandbox,
        verifier=scripted_verdict, explainer=narrative,
    )
    config = {"configurable": {"thread_id": "narrative-unconfirmed"}}

    graph.invoke({"spreadsheet_id": "demo", "question": QUESTION}, config)
    state = graph.get_state(config).values

    assert state["report"].startswith("No confirmed error.")
    assert narrative.briefs == []


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

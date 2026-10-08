import re
from pathlib import Path

from test_investigator import ScriptedDiagnosis

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
    ]
    assert "EBITDA 2027 = 52.0" in state["evidence"][0]["text"]
    assert "G8 = 40.0" in state["evidence"][0]["text"]
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
    assert report.endswith(".")


def test_explain_reports_inconclusive_without_citing_anything(
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

    assert state["report"] == "Inconclusive: no hypothesis survived verification."
    assert re.findall(r"ev-\d+", state["report"]) == []
    assert state["evidence"], "trace evidence exists even when the run fails"

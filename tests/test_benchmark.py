import json
from pathlib import Path

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from conftest import ASSUMPTIONS, PNL, ScriptedDiagnosis, ScriptedVerdict
from model_x_ray.benchmark.evaluators import calibration, diagnose_metrics, explain_metrics, load_sheet_metrics, locate_metrics
from model_x_ray.benchmark.runner import (
    SETUP_RULES,
    Setup,
    aggregate,
    build_setup_graph,
    drive_graph,
    run_benchmark,
    run_variant,
)
from model_x_ray.benchmark.rules import make_rules_diagnose_node
from model_x_ray.benchmark.report import render_report
from model_x_ray.benchmark.wilson import wilson
from model_x_ray.dataset import generate
from model_x_ray.spreadsheet.engine import Workbook
from model_x_ray.spreadsheet.sandbox import XlsxSandbox
from model_x_ray.spreadsheet.source import XlsxSource
from model_x_ray.spreadsheet.xlsx import load_xlsx

SCRIPTED_DIAGNOSIS = "scripted-diagnosis"
SCRIPTED_VERDICT = "scripted-verdict"
SETUP_SCRIPTED = Setup(name="scripted", kind="investigator", model=SCRIPTED_DIAGNOSIS, verifier=SCRIPTED_VERDICT)


def dataset(tmp_path: Path) -> Path:
    root = tmp_path / "dataset"
    generate(root, per_set=2, seed=42)
    return root


def ground_truth(root: Path, set_name: str, index: int) -> dict:
    return json.loads((root / set_name / f"variant-{index:03d}.json").read_text())


def scripted_factory(model_id: str):
    if model_id == SCRIPTED_VERDICT:
        return ScriptedVerdict()
    raise AssertionError(f"the scripted setup must not ask for {model_id}")


def test_the_rules_setup_finds_the_planted_cell_end_to_end_without_any_llm(tmp_path: Path) -> None:
    root = dataset(tmp_path)
    gt = ground_truth(root, "type1", 0)
    planted = gt["planted"][0]
    question = gt["questions"][0]
    source = XlsxSource({"variant": root / "type1" / "variant-000.xlsx"})
    sandbox = XlsxSandbox(source, tmp_path / "corrected")
    graph = build_setup_graph(SETUP_RULES, source, sandbox, "variant")
    config = {"configurable": {"thread_id": "rules-type1"}}

    final = drive_graph(graph, {"spreadsheet_id": "variant", "question": question["text"]}, config)

    assert final["target"]["cell"] == question["target"].split("!", 1)[1]
    assert [h["cell"] for h in final["hypotheses"][:3]].count(planted["cell"]) == 1
    assert final["hypotheses"][0]["cell"] == planted["cell"]
    assert final["hypotheses"][0]["error_type"] == "typed_value"
    assert final["report"].startswith("No confirmed error.")
    assert "Nothing was changed" in final["report"]
    assert final["corrected_copy_id"] is None
    assert {entry["node"] for entry in final["node_log"]} >= {
        "load_sheet", "map_model", "locate", "trace", "diagnose",
        "test", "verify", "explain", "human_review", "apply_fix",
    }
    assert all(entry["latency_ms"] >= 0 for entry in final["node_log"])
    assert final["tool_call_counts"] == []
    assert final["run_log"] == []


def test_the_rules_setup_reports_a_false_alarm_on_the_clean_set(tmp_path: Path) -> None:
    root = dataset(tmp_path)
    gt = ground_truth(root, "clean", 0)
    question = gt["questions"][0]
    source = XlsxSource({"variant": root / "clean" / "variant-000.xlsx"})
    sandbox = XlsxSandbox(source, tmp_path / "corrected")
    graph = build_setup_graph(SETUP_RULES, source, sandbox, "variant")
    config = {"configurable": {"thread_id": "rules-clean"}}

    final = drive_graph(graph, {"spreadsheet_id": "variant", "question": question["text"]}, config)

    assert gt["planted"] == []
    assert final["hypotheses"] != []
    assert final["hypotheses"][0]["cell"] == "P&L!G4"


def test_the_scripted_investigator_fixes_a_planted_variant_and_scores_full_metrics(tmp_path: Path) -> None:
    root = dataset(tmp_path)
    gt = ground_truth(root, "type1", 0)
    planted = gt["planted"][0]
    question = gt["questions"][0]
    source = XlsxSource({"variant": root / "type1" / "variant-000.xlsx"})
    output_dir = tmp_path / "corrected"
    sandbox = XlsxSandbox(source, output_dir)

    def factory(model_id: str):
        if model_id == SCRIPTED_VERDICT:
            return ScriptedVerdict()
        return ScriptedDiagnosis(turns=[([planted["cell"]], planted["cell"], planted["original_formula"])])

    row = run_variant(SETUP_SCRIPTED, source, sandbox, "variant", gt, factory, output_dir, base=load_xlsx(root / "base.xlsx"))

    assert row["root_cause_top1"] is True
    assert row["root_cause_top3"] is True
    assert row["error_type_correct"] is True
    assert row["fix_accuracy"] == 1.0
    assert row["false_alarm"] is False
    assert row["inconclusive"] is False
    assert row["probe_correct"] == "confirmed"
    assert row["probe_wrong"] == "rejected"
    assert row["verdict_precision"] == 1.0
    assert row["verdict_recall"] == 1.0
    assert row["locate_exact"] is True
    assert row["locate_exact"] is True
    assert row["trace_recall"] == 1.0
    assert row["sandbox_ok"] is True
    assert row["citations_valid"] is True
    assert row["tool_call_counts"] == [0]
    assert row["budget_hit"] is False
    assert row["cost_usd"] == 0.0
    assert row["input_tokens"] == 4000
    assert row["attempts"] == 1
    assert row["latency_ms"] > 0
    assert row["confusion"] == "typed_value|typed_value"
    assert set(row["node_latencies"]) >= {"diagnose", "test", "verify", "explain", "apply_fix"}
    assert all(latency >= 0 for latencies in row["node_latencies"].values() for latency in latencies)
    assert [entry["role"] for entry in row["run_log"]] == ["investigator", "investigator", "verifier", "verifier"]
    assert row["run_log"][0]["input_tokens"] == 1200
    assert row["run_log"][2]["input_tokens"] == 800
    assert row["hypothesis_revisions"] == 0
    assert row["parse_share"] == 1.0
    assert row["edge_precision"] == 1.0
    assert 0.0 < row["edge_recall"] < 1.0
    assert row["locate_ambiguous"] is False
    assert row["confidence_calibration"] == {"high": 1.0}


def test_the_runner_writes_rows_and_aggregates_with_wilson_intervals(tmp_path: Path) -> None:
    root = dataset(tmp_path)

    results = run_benchmark(root, [SETUP_RULES], output=tmp_path / "results.json")

    written = json.loads((tmp_path / "results.json").read_text())
    assert written == results
    rows = results["rows"]
    assert {row["setup"] for row in rows} == {"rules"}
    assert {row["set"] for row in rows} == {"type1", "type2", "type3", "type4", "type5", "blended", "overrides", "clean"}
    assert len(rows) == 14
    rules_type1 = next(r for r in rows if r["set"] == "type1" and r["variant_index"] == 0)
    assert rules_type1["root_cause_top1"] is True
    assert rules_type1["fix_accuracy"] == 0.0
    assert rules_type1["inconclusive"] is True
    assert rules_type1["hypothesis_revisions"] >= 0
    assert rules_type1["parse_share"] == 1.0
    assert rules_type1["edge_precision"] == 1.0
    assert 0.0 < rules_type1["edge_recall"] < 1.0
    assert rules_type1["locate_ambiguous"] is False
    assert rules_type1["confidence_calibration"] == {"medium": 0.0}
    clean = next(r for r in rows if r["set"] == "clean")
    assert clean["false_alarm"] is True
    assert clean["inconclusive"] is False
    assert clean["parse_share"] == 1.0
    assert clean["edge_precision"] == 1.0
    assert clean["edge_recall"] == 1.0
    entry = next(a for a in results["aggregates"] if a["setup"] == "rules" and a["set"] == "type1")
    assert entry["n"] == 2
    low, high = entry["root_cause_top1_ci"]
    assert 0.0 <= low <= high <= 1.0
    assert entry["latency_p50_ms"] >= 0 and entry["latency_p95_ms"] >= entry["latency_p50_ms"]
    assert entry["cost_usd_mean"] == 0.0
    assert entry["hypothesis_revisions_mean"] >= 0
    assert entry["parse_share_mean"] == 1.0
    assert entry["auto_pick_accuracy"] == 1.0
    type2 = next(a for a in results["aggregates"] if a["setup"] == "rules" and a["set"] == "type2")
    assert type2["auto_pick_accuracy"] == 1.0
    assert "typed_value|typed_value" in results["confusion"]["rules"]


def test_the_evaluators_score_a_fixed_state_against_ground_truth() -> None:
    state = {
        "target": {"sheet": "P&L", "cell": "H10", "label": "EBITDA", "period": "2027E", "value": 1.0, "prior_cell": "G10", "prior_value": 2.0},
        "hypotheses": [
            {"id": "hyp-1", "cell": "P&L!H5", "error_type": "wrong_reference", "status": "rejected", "claim": "", "evidence_ids": [], "confidence": "high"},
            {"id": "hyp-2", "cell": "P&L!H7", "error_type": "typed_value", "status": "confirmed", "claim": "", "evidence_ids": [], "confidence": "high"},
        ],
        "verifications": [{"hypothesis_id": "hyp-2", "verdict": "confirmed", "before": {}, "after": {}, "checks": {}, "reason": ""}],
        "report": "Root cause found in P&L!H7: typed value (evidence: ev-1, ev-9).",
        "evidence": [{"id": "ev-1", "cell": "P&L!H7", "kind": "anomaly", "text": "typed"}],
        "attempts": 2,
    }
    question = {"target": "P&L!H10", "expected_error_cells": ["P&L!H7"], "expected_verdict": "root_cause"}
    planted = [{"cell": "P&L!H7", "error_type": "typed_value"}]

    metrics = diagnose_metrics(state, question, planted)

    assert metrics["top1"] is True
    assert metrics["top3"] is True
    assert metrics["error_type_correct"] is True
    assert metrics["false_alarm"] is False
    assert metrics["revisions"] == 1
    assert metrics["confusion"] == "typed_value|typed_value"

    assert explain_metrics(state)["citations_valid"] is False
    assert explain_metrics({**state, "report": "Root cause found in P&L!H7 (evidence: ev-1)."})["citations_valid"] is True
    assert locate_metrics(state, question) == {"exact": True, "auto_picked": False}
    picked = {**state, "target_choice": {"candidates": ["P&L!H10", "Summary!D10"], "chosen": "P&L!H10", "why": "source"}}
    assert locate_metrics(picked, question) == {"exact": True, "auto_picked": True}
    assert calibration(state) == {"high": 0.5}

    base = Workbook(
        {f"P&L!{ref}": content for ref, content in PNL.items()}
        | {f"Assumptions!{ref}": content for ref, content in ASSUMPTIONS.items()}
    )
    assert load_sheet_metrics(base, base) == {"parse_share": 1.0, "edge_precision": 1.0, "edge_recall": 1.0}
    typed = load_sheet_metrics(base.with_patch("P&L!G6", 25.4), base)
    assert typed["parse_share"] == 1.0
    assert typed["edge_precision"] == 1.0
    assert 0.0 < typed["edge_recall"] < 1.0
    wrong = load_sheet_metrics(base.with_patch("P&L!G6", "=G4+G7"), base)
    assert 0.0 < wrong["edge_precision"] < 1.0
    assert 0.0 < wrong["edge_recall"] < 1.0
    broken = load_sheet_metrics(base.with_patch("P&L!G6", "=SUMX(G4)"), base)
    assert 0.0 < broken["parse_share"] < 1.0

    clean_state = {
        **state,
        "hypotheses": [{"id": "hyp-9", "cell": "P&L!G4", "error_type": "typed_value", "status": "open", "claim": "", "evidence_ids": [], "confidence": "medium"}],
        "report": "No confirmed error. The agent checked 1 suspect but could not prove it.",
    }
    clean_question = {"target": "P&L!H10", "expected_error_cells": [], "expected_verdict": "no_error"}
    assert diagnose_metrics(clean_state, clean_question, [])["false_alarm"] is True


def test_wilson_intervals_bracket_every_observed_rate() -> None:
    low, high = wilson(8, 10)
    assert 0.4 <= low <= 0.8 <= high <= 1.0
    assert wilson(0, 0) == (0.0, 1.0)
    low, high = wilson(0, 10)
    assert low == 0.0 and 0.0 < high < 0.3


def test_the_runner_captures_failed_investigations_without_losing_the_rest(tmp_path: Path) -> None:
    root = dataset(tmp_path)
    broken = Setup(name="broken", kind="investigator", model="missing-model", verifier="missing-model")

    def broken_factory(model_id: str):
        raise RuntimeError("model unavailable")

    results = run_benchmark(root, [broken], factory=broken_factory)

    errors = [row for row in results["rows"] if "error" in row]
    assert len(errors) == 14
    assert errors[0]["error"] == "RuntimeError: model unavailable"
    assert all(row["setup"] == "broken" and row["set"] and isinstance(row["variant_index"], int) for row in errors)
    assert results["meta"]["errors"] == 14
    assert results["aggregates"] == []
    report = render_report(results)
    assert "14 of 14 investigations failed" in report


def test_the_runner_produces_identical_results_when_variants_run_in_parallel(tmp_path: Path) -> None:
    root = dataset(tmp_path)

    serial = run_benchmark(root, [SETUP_RULES])
    parallel = run_benchmark(root, [SETUP_RULES], workers=3)

    key = lambda row: (row["set"], row["variant_index"])
    assert [key(row) for row in parallel["rows"]] == [key(row) for row in serial["rows"]]
    assert [row["root_cause_top1"] for row in parallel["rows"]] == [row["root_cause_top1"] for row in serial["rows"]]
    assert [row["confusion"] for row in parallel["rows"]] == [row["confusion"] for row in serial["rows"]]
    assert [(a["setup"], a["set"]) for a in parallel["aggregates"]] == [(a["setup"], a["set"]) for a in serial["aggregates"]]


def test_build_setup_graph_rejects_an_unknown_setup() -> None:
    with pytest.raises(ValueError, match="unknown setup"):
        build_setup_graph(Setup(name="gpt", kind="unknown", model=None), None, None, "x")



def test_every_model_the_agent_can_use_has_a_price_so_benchmark_costs_are_never_silently_zero() -> None:
    from model_x_ray.benchmark.runner import PRICES, SETUP_SUPER, SETUP_SUPER_3, cost_of
    from model_x_ray.llm import ROLE_MODELS

    assert set(ROLE_MODELS.values()) | {SETUP_SUPER.model, SETUP_SUPER_3.model} <= set(PRICES)
    assert SETUP_SUPER.model == "nvidia/Nemotron-3.5-Super-VL"
    assert SETUP_SUPER_3.model == "nvidia/nemotron-3-super-120b-a12b"
    log = [{"role": "investigator", "model": SETUP_SUPER.model, "input_tokens": 1_000_000, "output_tokens": 1_000_000, "reasoning_tokens": 0, "latency_ms": 1.0}]
    assert cost_of(log) == 0.30 + 0.90

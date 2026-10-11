from pathlib import Path

from model_x_ray.benchmark.report import chart_svg, render_report
from model_x_ray.benchmark.runner import SETUP_RULES, run_benchmark
from model_x_ray.dataset import generate


def aggregate(setup: str, set_name: str, **overrides) -> dict:
    entry = {
        "setup": setup,
        "set": set_name,
        "n": 2,
        "root_cause_top1_rate": 1.0,
        "root_cause_top1_ci": [0.34, 1.0],
        "root_cause_top3_ci": [0.34, 1.0],
        "error_type_ci": [0.34, 1.0],
        "fix_accuracy_mean": 0.0,
        "false_alarm_rate": 0.0,
        "false_alarm_ci": [0.0, 0.66],
        "inconclusive_rate": 1.0,
        "inconclusive_ci": [0.34, 1.0],
        "attempts_mean": 3.0,
        "hypothesis_revisions_mean": 0.0,
        "latency_p50_ms": 300.0,
        "latency_p95_ms": 400.0,
        "cost_usd_mean": 0.0,
        "input_tokens_mean": 0.0,
        "verdict_precision_mean": None,
        "verdict_recall_mean": None,
        "locate_exact_rate": 1.0,
        "clarification_precision": 0.5,
        "clarification_recall": 1.0,
        "trace_recall_mean": 1.0,
        "parse_share_mean": 1.0,
        "edge_precision_mean": 1.0,
        "edge_recall_mean": 0.9,
    }
    entry.update(overrides)
    return entry


def row(setup: str, set_name: str, **overrides) -> dict:
    entry = {
        "setup": setup,
        "set": set_name,
        "variant_index": 0,
        "root_cause_top1": True,
        "root_cause_top3": True,
        "error_type_correct": True,
        "fix_accuracy": 0.0,
        "false_alarm": False,
        "inconclusive": False,
        "probe_correct": "confirmed",
        "probe_wrong": "rejected",
        "verdict_precision": None,
        "verdict_recall": None,
        "locate_exact": True,
        "locate_asked": True,
        "locate_ambiguous": True,
        "trace_recall": 1.0,
        "sandbox_ok": True,
        "citations_valid": True,
        "parse_share": 1.0,
        "edge_precision": 1.0,
        "edge_recall": 0.9,
        "tool_call_counts": [3],
        "budget_hit": False,
        "cost_usd": 0.0,
        "input_tokens": 0,
        "attempts": 3,
        "hypothesis_revisions": 0,
        "latency_ms": 300.0,
        "confusion": "typed_value|typed_value",
        "confidence_calibration": {"high": 1.0},
        "node_latencies": {"diagnose": [50.0], "verify": [20.0]},
        "run_log": [],
    }
    entry.update(overrides)
    return entry


def synthetic_results() -> dict:
    super_row = row(
        "super",
        "type1",
        verdict_precision=1.0,
        verdict_recall=1.0,
        cost_usd=0.012,
        input_tokens=28000,
        latency_ms=90000.0,
        node_latencies={"diagnose": [70000.0], "verify": [15000.0]},
        run_log=[
            {"role": "investigator", "model": "nvidia/nemotron-3-super-120b-a12b", "input_tokens": 20000, "output_tokens": 400, "reasoning_tokens": 0, "latency_ms": 30000.0},
            {"role": "verifier", "model": "nvidia/nemotron-3-super-120b-a12b", "input_tokens": 8000, "output_tokens": 100, "reasoning_tokens": 0, "latency_ms": 10000.0},
        ],
    )
    return {
        "meta": {"variants": 4, "seed": 42, "setups": ["rules", "super"]},
        "rows": [
            row("rules", "type1", locate_ambiguous=False),
            row("rules", "clean", root_cause_top1=False, false_alarm=True, locate_ambiguous=False, confusion=None),
            super_row,
            row("super", "clean", root_cause_top1=False, false_alarm=False, locate_ambiguous=False, confusion=None, node_latencies={}),
        ],
        "aggregates": [
            aggregate("rules", "type1"),
            aggregate("rules", "clean", root_cause_top1_rate=0.0, root_cause_top1_ci=[0.0, 0.79], false_alarm_rate=1.0, false_alarm_ci=[0.2, 1.0], clarification_precision=None, clarification_recall=None, verdict_precision_mean=None),
            aggregate("super", "type1", root_cause_top1_rate=0.5, root_cause_top1_ci=[0.09, 0.91], fix_accuracy_mean=1.0, inconclusive_rate=0.0, inconclusive_ci=[0.0, 0.66], cost_usd_mean=0.012, input_tokens_mean=28000.0, latency_p50_ms=90000.0, latency_p95_ms=120000.0, verdict_precision_mean=1.0, verdict_recall_mean=1.0, clarification_precision=None, clarification_recall=None),
            aggregate("super", "clean", root_cause_top1_rate=0.0, root_cause_top1_ci=[0.0, 0.79], fix_accuracy_mean=None, false_alarm_rate=0.0, false_alarm_ci=[0.0, 0.79], inconclusive_rate=0.0, inconclusive_ci=[0.0, 0.79], cost_usd_mean=0.012, input_tokens_mean=28000.0, latency_p50_ms=90000.0, latency_p95_ms=120000.0, clarification_precision=None, clarification_recall=None, verdict_precision_mean=None),
        ],
        "confusion": {"rules": {"typed_value|typed_value": 2}, "super": {"typed_value|typed_value": 1, "wrong_reference|typed_value": 1}},
    }


def test_the_report_renders_every_section_from_fixed_results() -> None:
    report = render_report(synthetic_results())

    assert report.startswith("# Benchmark results")
    assert "4 variants" in report and "seed 42" in report
    assert "Set-ups in this report: rules, super" in report
    assert "| rules | type1 | 2 | 100% [34%, 100%] | 0.00 | 0% | 100% | 0.3 / 0.4 s | $0.0000 |" in report
    assert "| super | type1 | 2 | 50% [9%, 91%] | 1.00 | 0% | 0% | 90.0 / 120.0 s | $0.0120 |" in report
    assert "| super | clean | 2 | 0% [0%, 79%] | - | 0% | 0% | 90.0 / 120.0 s | $0.0120 |" in report
    assert "| rules | 100% | 0.00 / - | 1.00 | - | 1.00 | 0.90 |" in report
    assert "| super | 100% | 0.50 / 1.00 | 1.00 | 1.00 / 1.00 | 1.00 | 0.90 |" in report
    assert "| rules | diagnose | 50 |" in report
    assert "| super | diagnose | 70,000 |" in report
    assert "| super | verify | 15,000 |" in report
    assert "| super | investigator | 1 | 20,000 | $0.0064 |" in report
    assert "| super | verifier | 1 | 8,000 | $0.0025 |" in report
    assert "| rules | typed_value → typed_value | 2 |" in report
    assert "| super | wrong_reference → typed_value | 1 |" in report
    assert "type1 rules 100% (34%-100%)" in report
    assert "False alarms on the overrides set" not in report
    assert "False alarms on the clean set range from 0% (super) to 100% (rules)" in report
    assert "The inconclusive rate ranges from 0% (super) to 100% (rules)" in report
    assert "Cost per investigation averages $0.0120 for super and $0.0000 for rules" in report
    assert "Fix accuracy" in report
    assert "The full four-way comparison needs the live set-ups" in report
    assert "![Root-cause accuracy per set](benchmark.svg)" in report


def test_the_chart_draws_one_bar_per_set_up_and_set() -> None:
    svg = chart_svg(synthetic_results()["aggregates"])

    assert svg.startswith("<svg")
    assert svg.count("<rect") == 4
    assert 'width="600"' in svg
    assert 'width="300"' in svg
    assert "type1" in svg and "clean" in svg
    assert "rules" in svg and "super" in svg


def test_the_report_renders_from_a_real_rules_run(tmp_path: Path) -> None:
    root = tmp_path / "dataset"
    generate(root, per_set=2, seed=42)

    results = run_benchmark(root, [SETUP_RULES])

    report = render_report(results)
    assert "Set-ups in this report: rules" in report
    assert "seed 42" in report
    assert "| rules | type1 | 2 | 100% [34%, 100%] |" in report
    assert "The full four-way comparison needs the live set-ups; re-run scripts/benchmark.sh" in report
    svg = chart_svg(results["aggregates"])
    assert svg.count("<rect") == len(results["aggregates"])

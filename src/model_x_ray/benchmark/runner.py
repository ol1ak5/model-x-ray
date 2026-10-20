import json
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from uuid import uuid4

from langchain_core.language_models import BaseChatModel
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from model_x_ray import nodes
from model_x_ray.agents.investigator import MAX_TOOL_CALLS, build_investigator, make_diagnose_node
from model_x_ray.agents.locator import make_locate_node
from model_x_ray.benchmark.evaluators import (
    calibration,
    diagnose_metrics,
    explain_metrics,
    load_sheet_metrics,
    locate_metrics,
    trace_recall,
    verdict_metrics,
)
from model_x_ray.benchmark.rules import make_rules_diagnose_node
from model_x_ray.benchmark.wilson import wilson
from model_x_ray.graph import build_graph
from model_x_ray.llm import build_chat_model
from model_x_ray.spreadsheet.engine import Workbook, normalize_ref
from model_x_ray.spreadsheet.sandbox import XlsxSandbox
from model_x_ray.spreadsheet.source import SpreadsheetSource, XlsxSource
from model_x_ray.spreadsheet.xlsx import load_xlsx
from model_x_ray.state import InvestigationState, NodeLog, RunLog
from model_x_ray.tools import find_cells, make_read_only_tools

SUPER = "nvidia/Nemotron-3.5-Super-VL"
SUPER_3 = "nvidia/nemotron-3-super-120b-a12b"
LIGHTNING = "nvidia/Nemotron-3_5-Lightning"
NANO = "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B"
PRICES: dict[str, tuple[float, float]] = {SUPER: (0.30, 0.90), SUPER_3: (0.30, 0.90), LIGHTNING: (0.06, 0.24), NANO: (0.06, 0.24)}


@dataclass(frozen=True)
class Setup:
    name: str
    kind: str
    model: str | None = None
    verifier: str | None = None
    plain_text: bool = False


SETUP_RULES = Setup(name="rules", kind="rules")
SETUP_NANO = Setup(name="nano", kind="investigator", model=NANO, verifier=NANO)
SETUP_SUPER = Setup(name="super", kind="investigator", model=SUPER, verifier=SUPER)
SETUP_SUPER_3 = Setup(name="super-3", kind="investigator", model=SUPER_3, verifier=SUPER_3)
SETUP_NO_TOOLS = Setup(name="no-tools", kind="investigator", model=SUPER, verifier=SUPER, plain_text=True)


def setup_functions(
    setup: Setup,
    source: SpreadsheetSource,
    sandbox: XlsxSandbox,
    spreadsheet_id: str,
    factory: Callable[[str], BaseChatModel] | None = None,
) -> dict[str, Callable]:
    if setup.kind not in ("rules", "investigator"):
        raise ValueError(f"unknown setup kind {setup.kind!r}; known: rules, investigator")
    book = source.load(spreadsheet_id)
    make = factory or build_chat_model
    if setup.kind == "rules":
        diagnose = make_rules_diagnose_node(book)
        verifier_llm = None
    else:
        llm = make(setup.model)
        tools = [] if setup.plain_text else make_read_only_tools(book)
        diagnose = make_diagnose_node(build_investigator(llm, tools), book, plain_text=setup.plain_text)
        verifier_llm = make(setup.verifier) if setup.verifier else None
    return {
        "diagnose": diagnose,
        "load_sheet": nodes.make_load_sheet_node(book),
        "map_model": nodes.map_model,
        "locate": make_locate_node(None, book),
        "trace": nodes.make_trace_node(book),
        "test": nodes.make_test_node(source, sandbox),
        "verify": nodes.make_verify_node(verifier_llm, source),
        "explain": nodes.make_explain_node(),
        "human_review": nodes.human_review,
        "apply_fix": nodes.make_apply_fix_node(sandbox),
    }


def build_setup_graph(
    setup: Setup,
    source: SpreadsheetSource | None,
    sandbox: XlsxSandbox | None,
    spreadsheet_id: str,
    factory: Callable[[str], BaseChatModel] | None = None,
):
    functions = setup_functions(setup, source, sandbox, spreadsheet_id, factory)
    diagnose = functions.pop("diagnose")
    return build_graph(InMemorySaver(), diagnose=diagnose, overrides=functions)


def drive_graph(graph, inputs: dict, config: dict) -> dict:
    outcome = graph.invoke(inputs, config)
    while "__interrupt__" in outcome:
        outcome = graph.invoke(
            Command(resume={"action": "approve", "reason": "benchmark auto-approval", "patch": None}),
            config,
        )
    return graph.get_state(config).values


def run_probe(
    test_node: Callable,
    verify_node: Callable,
    spreadsheet_id: str,
    question: dict,
    target: dict | None,
    cell: str,
    new_formula: object,
) -> tuple[str, list[RunLog]]:
    state: InvestigationState = {
        "spreadsheet_id": spreadsheet_id,
        "question": question["text"],
        "target": target,
        "hypotheses": [
            {"id": "probe", "cell": cell, "error_type": "typed_value", "claim": "probe", "evidence_ids": [], "confidence": "high", "status": "open"}
        ],
        "patch": {"cell": cell, "old_formula": "", "new_formula": str(new_formula), "source": "agent"},
        "verifications": [],
        "evidence": [],
        "attempts": 0,
    }
    state = {**state, **test_node(state)}
    result = verify_node(state)
    return result["verifications"][-1]["verdict"], result.get("run_log", [])


def matches(expected: object, actual: object) -> bool:
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        return abs(actual - expected) <= 1e-6 * max(1.0, abs(expected))
    return actual == expected


def fix_accuracy_of(ground_truth: dict, final: dict, output_dir: Path | None, has_error: bool) -> float | None:
    if not has_error:
        return None
    name = final.get("corrected_copy_id")
    if not name or output_dir is None:
        return 0.0
    path = output_dir / name
    if not path.is_file():
        return 0.0
    book = load_xlsx(path)
    expected = ground_truth["expected_outputs"]
    if not expected:
        return 1.0
    return sum(1 for ref, value in expected.items() if matches(value, book.value(ref))) / len(expected)


def group_latencies(node_log: list[NodeLog]) -> dict[str, list[float]]:
    grouped: dict[str, list[float]] = {}
    for entry in node_log:
        grouped.setdefault(entry["node"], []).append(entry["latency_ms"])
    return grouped


def is_ambiguous(book: Workbook, target_ref: str) -> bool:
    label = book.row_label(target_ref)
    period = book.column_header(target_ref)
    if label is None or period is None:
        return False
    return len(find_cells(book, label, period)) > 1


def cost_of(run_log: list[RunLog]) -> float:
    total = 0.0
    for entry in run_log:
        price = PRICES.get(entry.get("model") or "")
        if price is None:
            continue
        total += (entry.get("input_tokens") or 0) / 1_000_000 * price[0]
        total += (entry.get("output_tokens") or 0) / 1_000_000 * price[1]
    return total


def run_variant(
    setup: Setup,
    source: SpreadsheetSource,
    sandbox: XlsxSandbox,
    spreadsheet_id: str,
    ground_truth: dict,
    factory: Callable[[str], BaseChatModel] | None = None,
    output_dir: Path | None = None,
    base: Workbook | None = None,
) -> dict:
    question = ground_truth["questions"][0]
    planted = ground_truth["planted"]
    has_error = question.get("expected_verdict") == "root_cause"
    book = source.load(spreadsheet_id)
    functions = setup_functions(setup, source, sandbox, spreadsheet_id, factory)
    diagnose = functions.pop("diagnose")
    graph = build_graph(InMemorySaver(), diagnose=diagnose, overrides=functions)
    config = {"configurable": {"thread_id": f"{setup.name}-{ground_truth['set']}-{ground_truth['variant_index']}-{uuid4().hex[:6]}"}}
    started = time.perf_counter()
    final = drive_graph(graph, {"spreadsheet_id": spreadsheet_id, "question": question["text"]}, config)
    latency_ms = (time.perf_counter() - started) * 1000
    probe_correct = probe_wrong = None
    verdict_events: list[tuple[str, bool]] = []
    probe_log: list[RunLog] = []
    if has_error and planted:
        record = planted[0]
        correct, correct_log = run_probe(
            functions["test"], functions["verify"], spreadsheet_id, question, final.get("target"),
            record["cell"], record["original_formula"],
        )
        wrong, wrong_log = run_probe(
            functions["test"], functions["verify"], spreadsheet_id, question, final.get("target"),
            record["cell"], record["new_content"],
        )
        probe_correct, probe_wrong = correct, wrong
        probe_log = correct_log + wrong_log
        verdict_events = [(correct, True), (wrong, False)]
    verifications = final.get("verifications", [])
    inconclusive = has_error and (not verifications or verifications[-1]["verdict"] != "confirmed")
    if has_error and verifications:
        patch = final.get("patch")
        if patch is not None:
            planted_refs = {normalize_ref(p["cell"]) for p in planted}
            verdict_events.append((verifications[-1]["verdict"], normalize_ref(patch["cell"]) in planted_refs))
    run_log = [*final.get("run_log", []), *probe_log]
    verdicts = verdict_metrics(verdict_events)
    metrics = diagnose_metrics(final, question, planted)
    sheet = load_sheet_metrics(book, base)
    tool_counts = final.get("tool_call_counts", [])
    return {
        "setup": setup.name,
        "set": ground_truth["set"],
        "variant_index": ground_truth["variant_index"],
        "root_cause_top1": metrics["top1"],
        "root_cause_top3": metrics["top3"],
        "error_type_correct": metrics["error_type_correct"],
        "fix_accuracy": fix_accuracy_of(ground_truth, final, output_dir, has_error),
        "false_alarm": metrics["false_alarm"],
        "inconclusive": inconclusive,
        "probe_correct": probe_correct,
        "probe_wrong": probe_wrong,
        "verdict_precision": verdicts["verdict_precision"],
        "verdict_recall": verdicts["verdict_recall"],
        "locate_exact": locate_metrics(final, question)["exact"],
        "locate_auto_picked": locate_metrics(final, question)["auto_picked"],
        "locate_ambiguous": is_ambiguous(book, question["target"]),
        "trace_recall": trace_recall(final, question),
        "sandbox_ok": bool(verifications and verifications[-1].get("before")),
        "citations_valid": explain_metrics(final)["citations_valid"],
        "parse_share": sheet["parse_share"],
        "edge_precision": sheet["edge_precision"],
        "edge_recall": sheet["edge_recall"],
        "tool_call_counts": tool_counts,
        "budget_hit": any(count >= MAX_TOOL_CALLS for count in tool_counts),
        "cost_usd": cost_of(run_log),
        "input_tokens": sum(entry.get("input_tokens") or 0 for entry in run_log),
        "attempts": final.get("attempts", 0),
        "hypothesis_revisions": metrics["revisions"],
        "latency_ms": latency_ms,
        "confusion": metrics["confusion"],
        "confidence_calibration": calibration(final),
        "node_latencies": group_latencies(final.get("node_log", [])),
        "run_log": run_log,
    }


def percentile(ordered: list[float], fraction: float) -> float:
    if not ordered:
        return 0.0
    index = min(len(ordered) - 1, max(0, round(fraction * (len(ordered) - 1))))
    return ordered[index]


def mean_of(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def aggregate(rows: list[dict]) -> list[dict]:
    groups: dict[tuple[str, str], list[dict]] = {}
    for row in rows:
        if is_error_row(row):
            continue
        groups.setdefault((row["setup"], row["set"]), []).append(row)
    entries = []
    for (setup, set_name), group in sorted(groups.items()):
        n = len(group)

        def count(key: str) -> int:
            return sum(1 for row in group if row[key])

        latencies = sorted(row["latency_ms"] for row in group)
        ambiguous_rows = [row for row in group if row["locate_ambiguous"]]
        entries.append(
            {
                "setup": setup,
                "set": set_name,
                "n": n,
                "root_cause_top1_rate": count("root_cause_top1") / n,
                "root_cause_top1_ci": list(wilson(count("root_cause_top1"), n)),
                "root_cause_top3_ci": list(wilson(count("root_cause_top3"), n)),
                "error_type_ci": list(wilson(count("error_type_correct"), n)),
                "fix_accuracy_mean": mean_of([row["fix_accuracy"] for row in group if row["fix_accuracy"] is not None]),
                "false_alarm_rate": count("false_alarm") / n,
                "false_alarm_ci": list(wilson(count("false_alarm"), n)),
                "inconclusive_rate": count("inconclusive") / n,
                "inconclusive_ci": list(wilson(count("inconclusive"), n)),
                "attempts_mean": mean_of([float(row["attempts"]) for row in group]),
                "hypothesis_revisions_mean": mean_of([float(row["hypothesis_revisions"]) for row in group]),
                "latency_p50_ms": percentile(latencies, 0.5),
                "latency_p95_ms": percentile(latencies, 0.95),
                "cost_usd_mean": mean_of([row["cost_usd"] for row in group]),
                "input_tokens_mean": mean_of([float(row["input_tokens"]) for row in group]),
                "verdict_precision_mean": mean_of([row["verdict_precision"] for row in group if row["verdict_precision"] is not None]),
                "verdict_recall_mean": mean_of([row["verdict_recall"] for row in group if row["verdict_recall"] is not None]),
                "locate_exact_rate": count("locate_exact") / n,
                "auto_pick_accuracy": sum(1 for row in ambiguous_rows if row["locate_exact"]) / len(ambiguous_rows) if ambiguous_rows else None,
                "trace_recall_mean": mean_of([row["trace_recall"] for row in group if row["trace_recall"] is not None]),
                "parse_share_mean": mean_of([row["parse_share"] for row in group if row["parse_share"] is not None]),
                "edge_precision_mean": mean_of([row["edge_precision"] for row in group if row["edge_precision"] is not None]),
                "edge_recall_mean": mean_of([row["edge_recall"] for row in group if row["edge_recall"] is not None]),
            }
        )
    return entries


def confusion(rows: list[dict]) -> dict[str, dict[str, int]]:
    table: dict[str, dict[str, int]] = {}
    for row in rows:
        if is_error_row(row) or not row.get("confusion"):
            continue
        counts = table.setdefault(row["setup"], {})
        counts[row["confusion"]] = counts.get(row["confusion"], 0) + 1
    return table


def is_error_row(row: dict) -> bool:
    return "error" in row


def guarded(task: Callable[[], dict], label: dict) -> dict:
    try:
        return task()
    except Exception as error:
        return {**label, "error": f"{type(error).__name__}: {error}"}


def run_job(job: tuple[Callable[[], dict], dict]) -> dict:
    task, label = job
    return guarded(task, label)


def run_benchmark(
    root: Path,
    setups: list[Setup],
    output: Path | None = None,
    factory: Callable[[str], BaseChatModel] | None = None,
    workers: int = 1,
) -> dict:
    manifest = json.loads((root / "manifest.json").read_text())
    base_path = root / "base.xlsx"
    base = load_xlsx(base_path) if base_path.is_file() else None
    tasks: list[tuple[Callable[[], dict], dict]] = []
    for variant in manifest["variants"]:
        ground_truth = json.loads((root / variant["ground_truth"]).read_text())
        for setup in setups:
            source = XlsxSource({"variant": root / variant["file"]})
            output_dir = root / "corrected" / setup.name / variant["set"]
            sandbox = XlsxSandbox(source, output_dir)
            task = partial(run_variant, setup, source, sandbox, "variant", ground_truth, factory, output_dir, base=base)
            label = {"setup": setup.name, "set": ground_truth["set"], "variant_index": ground_truth["variant_index"]}
            tasks.append((task, label))
    if workers > 1:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            rows = list(pool.map(run_job, tasks))
    else:
        rows = [run_job(job) for job in tasks]
    results = {
        "meta": {
            "variants": len(manifest["variants"]),
            "seed": manifest.get("seed"),
            "setups": [setup.name for setup in setups],
            "errors": sum(1 for row in rows if is_error_row(row)),
        },
        "rows": rows,
        "aggregates": aggregate(rows),
        "confusion": confusion(rows),
    }
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(results, indent=2, sort_keys=True) + "\n")
    return results

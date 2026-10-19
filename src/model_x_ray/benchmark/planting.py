import json
import random
import re
import time
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from uuid import uuid4

from langchain_core.language_models import BaseChatModel
from openpyxl import load_workbook

from model_x_ray.benchmark.runner import Setup, build_setup_graph, cost_of, drive_graph, matches, percentile
from model_x_ray.rules import is_period_cell
from model_x_ray.spreadsheet.engine import FormulaError, Workbook, column_letters, is_number, normalize_ref, split_ref
from model_x_ray.spreadsheet.sandbox import XlsxSandbox
from model_x_ray.spreadsheet.source import XlsxSource
from model_x_ray.spreadsheet.xlsx import load_xlsx

ERROR_TYPES = ("typed_value", "wrong_reference", "range", "sign", "period_lag")
RELATIVE_CELL = re.compile(r"(?<![A-Za-z$!'])([A-Za-z]{1,3})([0-9]+)(?![0-9(])")
SUM_RANGE = re.compile(r"(SUM\(\s*\$?[A-Za-z]{1,3}\$?[0-9]+:\$?)([A-Za-z]{1,3})(\$?)([0-9]+)", re.IGNORECASE)


def copied_rows(book: Workbook) -> list[list[str]]:
    rows: dict[tuple[str, int], list[str]] = {}
    for ref in book.cells():
        if book.formula(ref) is not None and is_period_cell(book, ref):
            sheet, address = split_ref(ref)
            rows.setdefault((sheet, address.row), []).append(ref)
    found = []
    for refs in rows.values():
        patterns = Counter(book.formula_pattern(ref) for ref in refs)
        common, count = patterns.most_common(1)[0]
        if count >= 3:
            ordered = sorted((ref for ref in refs if book.formula_pattern(ref) == common), key=lambda ref: split_ref(ref)[1].column)
            found.append(ordered)
    return found


def shift_reference(formula: str, rows: int = 0, columns: int = 0) -> str | None:
    match = next((m for m in RELATIVE_CELL.finditer(formula) if not formula[max(0, m.start() - 1)] == "$"), None)
    if match is None:
        return None
    column = sum((ord(c) - 64) * 26 ** i for i, c in enumerate(reversed(match.group(1).upper()))) + columns
    row = int(match.group(2)) + rows
    if column < 1 or row < 1:
        return None
    return formula[: match.start()] + f"{column_letters(column)}{row}" + formula[match.end():]


def lag_all(formula: str) -> str | None:
    changed = False

    def lag(match: re.Match) -> str:
        nonlocal changed
        start = match.start()
        if start > 0 and match.string[start - 1] == "$":
            return match.group(0)
        column = sum((ord(c) - 64) * 26 ** i for i, c in enumerate(reversed(match.group(1).upper()))) - 1
        if column < 1:
            return match.group(0)
        changed = True
        return f"{column_letters(column)}{match.group(2)}"

    lagged = RELATIVE_CELL.sub(lag, formula)
    return lagged if changed else None


def planted_content(book: Workbook, ref: str, error_type: str, row: list[str]) -> object | None:
    formula = book.formula(ref) or ""
    if error_type == "typed_value":
        prior = row[row.index(ref) - 1]
        value = book.value(prior)
        return float(value) if is_number(value) else None
    if error_type == "wrong_reference":
        return shift_reference(formula, rows=1)
    if error_type == "range":
        match = SUM_RANGE.search(formula)
        if match is None or int(match.group(4)) <= 1:
            return None
        return formula[: match.start()] + match.group(1) + match.group(2) + match.group(3) + str(int(match.group(4)) - 1) + formula[match.end():]
    if error_type == "sign":
        return "=-(" + formula[1:] + ")"
    if error_type == "period_lag":
        return lag_all(formula)
    return None


def changes_the_model(book: Workbook, ref: str, content: object) -> bool:
    try:
        before = book.value(ref)
        after = book.with_patch(ref, content).value(ref)
    except (FormulaError, RecursionError):
        return False
    return is_number(before) and is_number(after) and abs(float(after) - float(before)) > 1e-6 * max(1.0, abs(float(before)))


def plant_model(source: Path, output: Path, seed: int = 42) -> list[dict]:
    book = load_xlsx(source)
    rows = [row for row in copied_rows(book) if len(row) >= 3]
    rng = random.Random(f"{seed}-{source.stem}")
    records = []
    for error_type in ERROR_TYPES:
        sites = [(row, ref) for row in rows for ref in row[1:-1]]
        rng.shuffle(sites)
        for row, ref in sites:
            content = planted_content(book, ref, error_type, row)
            if content is None or content == book.formula(ref) or not changes_the_model(book, ref, content):
                continue
            workbook = load_workbook(source)
            sheet, address = split_ref(ref)
            workbook[sheet][f"{column_letters(address.column)}{address.row}"] = content
            path = output / source.stem / f"{error_type}.xlsx"
            path.parent.mkdir(parents=True, exist_ok=True)
            workbook.save(path)
            record = {"model": source.stem, "error_type": error_type, "cell": ref, "original": book.formula(ref), "planted": content, "original_value": book.value(ref), "file": str(path)}
            path.with_suffix(".json").write_text(json.dumps(record, indent=1, default=str))
            records.append(record)
            break
    return records


def split_models(models: list[str], seed: int = 42, test_share: float = 0.2) -> dict[str, list[str]]:
    order = sorted(models)
    random.Random(seed).shuffle(order)
    count = max(1, round(test_share * len(order)))
    return {"tune": sorted(order[count:]), "test": sorted(order[:count])}


def run_planted(setup: Setup, record: dict, workdir: Path, factory: Callable[[str], BaseChatModel] | None = None, clean_file: Path | None = None) -> dict:
    path = clean_file or Path(record["file"])
    row: dict = {"setup": setup.name, "model": record["model"], "error_type": "clean" if clean_file else record["error_type"], "error": None}
    spreadsheet_id = f"{record['model']}-{row['error_type']}"
    source = XlsxSource({spreadsheet_id: path})
    started = time.perf_counter()
    try:
        graph = build_setup_graph(setup, source, XlsxSandbox(source, workdir), spreadsheet_id, factory)
        final = drive_graph(graph, {"spreadsheet_id": spreadsheet_id, "question": ""}, {"configurable": {"thread_id": f"{spreadsheet_id}-{uuid4().hex[:6]}"}})
    except Exception as error:
        return {**row, "error": f"{type(error).__name__}: {str(error)[:160]}", "latency_ms": (time.perf_counter() - started) * 1000, "cost_usd": 0.0}
    verifications = final.get("verifications", [])
    patch = final.get("patch")
    confirmed = patch is not None and bool(verifications) and verifications[-1]["verdict"] == "confirmed"
    patched = normalize_ref(patch["cell"]) if patch else None
    run_log = final.get("run_log", [])
    result = {**row, "patched_cell": patched, "verdict": verifications[-1]["verdict"] if verifications else None, "latency_ms": (time.perf_counter() - started) * 1000, "cost_usd": cost_of(run_log)}
    if clean_file:
        return {**result, "false_alarm": confirmed}
    planted = normalize_ref(record["cell"])
    target = final.get("target") or {}
    seen = {normalize_ref(h["cell"]) for h in final.get("hypotheses", [])} | {normalize_ref(f["cell"]) for f in target.get("other_findings", [])}
    restored = False
    copy_name = final.get("corrected_copy_id")
    if confirmed and patched == planted and copy_name:
        try:
            restored = matches(record["original_value"], load_xlsx(workdir / copy_name).value(planted))
        except Exception:
            restored = False
    return {**result, "root_cause_found": confirmed and patched == planted, "error_seen": planted in seen or patched == planted, "fix_restores_value": restored}


def summarize(rows: list[dict]) -> dict:
    ran = [row for row in rows if row["error"] is None]
    planted = [row for row in ran if row["error_type"] != "clean"]
    clean = [row for row in ran if row["error_type"] == "clean"]
    latencies = sorted(row["latency_ms"] / 1000 for row in ran)

    def count(group: list[dict], field: str) -> str:
        return f"{sum(1 for row in group if row[field])} of {len(group)}"

    by_type = {kind: count([row for row in planted if row["error_type"] == kind], "root_cause_found") for kind in ERROR_TYPES if any(row["error_type"] == kind for row in planted)}
    return {
        "cases": len(planted),
        "root_cause_found": count(planted, "root_cause_found"),
        "error_seen": count(planted, "error_seen"),
        "fix_restores_value": count(planted, "fix_restores_value"),
        "by_error_type": by_type,
        "false_alarms": count(clean, "false_alarm"),
        "skipped": len(rows) - len(ran),
        "latency_p50_s": round(percentile(latencies, 0.5), 1),
        "latency_p95_s": round(percentile(latencies, 0.95), 1),
        "cost_usd_total": round(sum(row.get("cost_usd", 0.0) for row in rows), 4),
    }

import datetime

from model_x_ray.benchmark.runner import PRICES, mean_of, percentile

SET_ORDER = ["type1", "type2", "type3", "type4", "type5", "blended", "overrides", "clean"]
COLORS = ["#2563eb", "#dc2626", "#16a34a", "#9333ea", "#ea580c", "#0891b2", "#65a30d", "#db2777"]


def pct(value: float | None) -> str:
    return "-" if value is None else f"{value:.0%}"


def rate2(value: float | None) -> str:
    return "-" if value is None else f"{value:.2f}"


def ci_text(bounds: list[float] | None) -> str:
    return f"[{bounds[0]:.0%}, {bounds[1]:.0%}]" if bounds else "-"


def results_row(entry: dict) -> str:
    fix = "-" if entry["fix_accuracy_mean"] is None else f"{entry['fix_accuracy_mean']:.2f}"
    cost = entry["cost_usd_mean"] or 0.0
    return (
        f"| {entry['setup']} | {entry['set']} | {entry['n']} | {pct(entry['root_cause_top1_rate'])} {ci_text(entry['root_cause_top1_ci'])} |"
        f" {fix} | {pct(entry['false_alarm_rate'])} | {pct(entry['inconclusive_rate'])} |"
        f" {entry['latency_p50_ms'] / 1000:.1f} / {entry['latency_p95_ms'] / 1000:.1f} s | ${cost:.4f} |"
    )


def step_row(setup: str, rows: list[dict]) -> str:
    asked = [row for row in rows if row["locate_asked"]]
    ambiguous = [row for row in rows if row["locate_ambiguous"]]
    clarified = [row for row in rows if row["locate_asked"] and row["locate_ambiguous"]]
    precisions = [row["verdict_precision"] for row in rows if row["verdict_precision"] is not None]
    recalls = [row["verdict_recall"] for row in rows if row["verdict_recall"] is not None]
    verdict = f"{rate2(mean_of(precisions))} / {rate2(mean_of(recalls))}" if precisions or recalls else "-"
    clarification = (
        f"{rate2(len(clarified) / len(asked) if asked else None)} / {rate2(len(clarified) / len(ambiguous) if ambiguous else None)}"
    )
    trace = rate2(mean_of([row["trace_recall"] for row in rows if row["trace_recall"] is not None]))
    parse = rate2(mean_of([row["parse_share"] for row in rows if row["parse_share"] is not None]))
    edge = rate2(mean_of([row["edge_recall"] for row in rows if row["edge_recall"] is not None]))
    exact = pct(mean_of([1.0 if row["locate_exact"] else 0.0 for row in rows]))
    return f"| {setup} | {exact} | {clarification} | {trace} | {verdict} | {parse} | {edge} |"


def node_p50(rows: list[dict]) -> dict[str, float]:
    latencies: dict[str, list[float]] = {}
    for row in rows:
        for node, values in row.get("node_latencies", {}).items():
            latencies.setdefault(node, []).extend(values)
    return {node: percentile(sorted(values), 0.5) for node, values in sorted(latencies.items())}


def role_totals(rows: list[dict]) -> list[tuple[str, str, int, int, float]]:
    totals: dict[tuple[str, str], dict] = {}
    for row in rows:
        for entry in row.get("run_log", []):
            key = (row["setup"], entry.get("role") or "unknown")
            bucket = totals.setdefault(key, {"calls": 0, "input": 0, "cost": 0.0})
            bucket["calls"] += 1
            bucket["input"] += entry.get("input_tokens") or 0
            price = PRICES.get(entry.get("model") or "")
            if price:
                bucket["cost"] += (entry.get("input_tokens") or 0) / 1_000_000 * price[0]
                bucket["cost"] += (entry.get("output_tokens") or 0) / 1_000_000 * price[1]
    return [
        (setup, role, bucket["calls"], bucket["input"], bucket["cost"])
        for (setup, role), bucket in sorted(totals.items())
    ]


def conclusion(aggregates: list[dict]) -> str:
    by_set: dict[str, list[dict]] = {}
    per_setup: dict[str, dict] = {}
    for entry in aggregates:
        by_set.setdefault(entry["set"], []).append(entry)
        bucket = per_setup.setdefault(entry["setup"], {"cost": [], "p50": [], "inconclusive": []})
        bucket["cost"].append(entry["cost_usd_mean"] or 0.0)
        bucket["p50"].append(entry["latency_p50_ms"])
        bucket["inconclusive"].append(entry["inconclusive_rate"])
    parts = []
    winners = []
    for set_name in SET_ORDER:
        entries = by_set.get(set_name, [])
        best = max(entries, key=lambda e: e["root_cause_top1_rate"]) if entries else None
        if best and best["root_cause_top1_rate"] > 0:
            low, high = best["root_cause_top1_ci"]
            winners.append(f"{set_name} {best['setup']} {best['root_cause_top1_rate']:.0%} ({low:.0%}-{high:.0%})")
    if winners:
        parts.append(f"Top-1 root-cause accuracy: {', '.join(winners)}.")
    for set_name in ("overrides", "clean"):
        entries = by_set.get(set_name, [])
        if not entries:
            continue
        lowest = min(entries, key=lambda e: e["false_alarm_rate"])
        highest = max(entries, key=lambda e: e["false_alarm_rate"])
        parts.append(
            f"False alarms on the {set_name} set range from {lowest['false_alarm_rate']:.0%} ({lowest['setup']})"
            f" to {highest['false_alarm_rate']:.0%} ({highest['setup']})."
        )
    fixes: dict[str, list[float]] = {}
    for entry in aggregates:
        if entry["fix_accuracy_mean"] is not None:
            fixes.setdefault(entry["setup"], []).append(entry["fix_accuracy_mean"])
    if fixes:
        ranked = sorted(((setup, sum(values) / len(values)) for setup, values in fixes.items()), key=lambda pair: -pair[1])
        parts.append("Fix accuracy on the error sets averages " + " and ".join(f"{rate:.0%} for {setup}" for setup, rate in ranked) + ".")
    costs = sorted(
        ((setup, sum(b["cost"]) / len(b["cost"]), sum(b["p50"]) / len(b["p50"])) for setup, b in per_setup.items()),
        key=lambda item: -item[1],
    )
    inconclusive = sorted(
        ((setup, sum(b["inconclusive"]) / len(b["inconclusive"])) for setup, b in per_setup.items()),
        key=lambda item: item[1],
    )
    if inconclusive:
        parts.append(
            f"The inconclusive rate ranges from {inconclusive[0][1]:.0%} ({inconclusive[0][0]})"
            f" to {inconclusive[-1][1]:.0%} ({inconclusive[-1][0]})."
        )
    if len(costs) >= 2:
        top, bottom = costs[0], costs[-1]
        parts.append(
            f"Cost per investigation averages ${top[1]:.4f} for {top[0]} and ${bottom[1]:.4f} for {bottom[0]},"
            f" with p50 latencies of {top[2] / 1000:.1f} s and {bottom[2] / 1000:.1f} s."
        )
    elif costs:
        parts.append(f"Cost per investigation averages ${costs[0][1]:.4f} for {costs[0][0]}, with a p50 latency of {costs[0][2] / 1000:.1f} s.")
    return " ".join(parts)


def chart_svg(aggregates: list[dict]) -> str:
    setups = sorted({entry["setup"] for entry in aggregates})
    sets = [name for name in SET_ORDER if any(entry["set"] == name for entry in aggregates)]
    width, left, bar_height, gap, plot = 780, 120, 18, 14, 600
    group_height = len(setups) * bar_height + gap
    height = 40 + len(sets) * group_height + 10
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" font-family="sans-serif" font-size="12">'
    ]
    for index, setup in enumerate(setups):
        color = COLORS[index % len(COLORS)]
        lines.append(f'<text x="{left + index * 140}" y="17" fill="{color}">{setup}</text>')
    for set_index, set_name in enumerate(sets):
        top = 40 + set_index * group_height
        lines.append(f'<text x="0" y="{top + group_height / 2}">{set_name}</text>')
        for setup_index, setup in enumerate(setups):
            entry = next((e for e in aggregates if e["setup"] == setup and e["set"] == set_name), None)
            rate = entry["root_cause_top1_rate"] if entry else 0.0
            y = top + setup_index * bar_height
            bar_width = round(rate * plot)
            lines.append(
                f'<rect x="{left}" y="{y}" width="{bar_width}" height="{bar_height - 4}" fill="{COLORS[setup_index % len(COLORS)]}"/>'
            )
            lines.append(f'<text x="{left + bar_width + 6}" y="{y + bar_height - 8}">{rate:.0%}</text>')
    lines.append("</svg>")
    return "\n".join(lines)


def render_report(results: dict, chart_name: str = "benchmark.svg") -> str:
    meta = results.get("meta", {})
    aggregates = results["aggregates"]
    rows = results["rows"]
    setups = meta.get("setups") or sorted({entry["setup"] for entry in aggregates})
    rows_by_setup: dict[str, list[dict]] = {}
    for row in rows:
        if "error" in row:
            continue
        rows_by_setup.setdefault(row["setup"], []).append(row)
    lines = [
        "# Benchmark results",
        "",
        f"{meta.get('variants', len(rows))} variants, dataset seed {meta.get('seed', 'unknown')}, run {datetime.date.today().isoformat()}."
        f" Set-ups in this report: {', '.join(setups)}.",
        "",
    ]
    errors = meta.get("errors") or sum(1 for row in rows if "error" in row)
    if errors:
        lines += [
            f"{errors} of {len(rows)} investigations failed with errors; their rows carry an `error` field and are excluded from every table.",
            "",
        ]
    if len(setups) < 4:
        lines += ["The full four-way comparison needs the live set-ups; re-run scripts/benchmark.sh.", ""]
    lines += [
        "## Results per set",
        "",
        "| Set-up | Set | n | Root cause top-1 (95% CI) | Fix accuracy | False alarms | Inconclusive | Latency p50 / p95 | Cost / investigation |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    lines += [results_row(entry) for entry in aggregates]
    lines += [
        "",
        "## Per step",
        "",
        "Aggregated across all sets in this run.",
        "",
        "| Set-up | Locate exact | Clarification P / R | Trace recall | Verdict P / R | Parse share | Edge recall |",
        "|---|---|---|---|---|---|---|",
    ]
    for setup in setups:
        group = rows_by_setup.get(setup, [])
        if group:
            lines.append(step_row(setup, group))
    lines += [
        "",
        "## Latency and tokens per step",
        "",
        "| Set-up | Node | Latency p50 (ms) |",
        "|---|---|---|",
    ]
    for setup in setups:
        for node, value in node_p50(rows_by_setup.get(setup, [])).items():
            lines.append(f"| {setup} | {node} | {value:,.0f} |")
    lines += [
        "",
        "| Set-up | LLM role | Calls | Input tokens | Cost |",
        "|---|---|---|---|---|",
    ]
    roles = role_totals(rows)
    if roles:
        lines += [
            f"| {setup} | {role} | {calls} | {input_tokens:,} | ${cost:.4f} |"
            for setup, role, calls, input_tokens, cost in roles
        ]
    else:
        lines.append("No LLM calls in this run.")
    lines += [
        "",
        "## Confusion matrix (predicted → planted)",
        "",
        "| Set-up | Prediction | Count |",
        "|---|---|---|",
    ]
    for setup, counts in sorted(results["confusion"].items()):
        for combo, count in sorted(counts.items(), key=lambda pair: -pair[1]):
            lines.append(f"| {setup} | {combo.replace('|', ' → ')} | {count} |")
    lines += [
        "",
        "## Conclusion",
        "",
        conclusion(aggregates),
        "",
        "## Chart",
        "",
        f"![Root-cause accuracy per set]({chart_name})",
        "",
    ]
    return "\n".join(lines)

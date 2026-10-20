import argparse
import json
from pathlib import Path

from model_x_ray.benchmark.report import chart_svg, render_report
from model_x_ray.benchmark.runner import (
    SETUP_NANO,
    SETUP_NO_TOOLS,
    SETUP_RULES,
    SETUP_SUPER,
    SETUP_SUPER_3,
    Setup,
    run_benchmark,
)
from model_x_ray.dataset import generate

SETUPS: dict[str, Setup] = {
    "rules": SETUP_RULES,
    "nano": SETUP_NANO,
    "super": SETUP_SUPER,
    "super-3": SETUP_SUPER_3,
    "no-tools": SETUP_NO_TOOLS,
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the planted-error benchmark")
    parser.add_argument("--dataset", type=Path, default=Path("dataset"))
    parser.add_argument("--output", type=Path, default=Path("docs/benchmark-results.json"))
    parser.add_argument("--report", type=Path, default=Path("docs/benchmark.md"))
    parser.add_argument(
        "--setups",
        default="rules",
        help=f"comma-separated set-ups or 'all' ({', '.join(SETUPS)}); the live ones spend Token Factory credits",
    )
    parser.add_argument("--per-set", type=int, default=25)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--workers", type=int, default=6, help="parallel investigations; latency figures stay per investigation")
    parser.add_argument("--regenerate", action="store_true", help="regenerate the dataset before running")
    parser.add_argument("--render-only", action="store_true", help="render the report from an existing results file")
    args = parser.parse_args()

    names = list(SETUPS) if args.setups == "all" else [name.strip() for name in args.setups.split(",") if name.strip()]
    unknown = [name for name in names if name not in SETUPS]
    if unknown:
        parser.error(f"unknown set-ups: {', '.join(unknown)}; known: {', '.join(SETUPS)}")
    if args.render_only:
        if not args.output.is_file():
            parser.error(f"no results file at {args.output}; run the benchmark first")
        results = json.loads(args.output.read_text())
    else:
        if args.regenerate or not (args.dataset / "manifest.json").is_file():
            manifest = generate(args.dataset, per_set=args.per_set, seed=args.seed)
            print(f"{len(manifest['variants'])} variants generated in {args.dataset}")
        results = run_benchmark(
            args.dataset,
            [SETUPS[name] for name in names],
            output=args.output,
            workers=args.workers,
        )
        for entry in results["aggregates"]:
            low, high = entry["root_cause_top1_ci"]
            print(
                f"{entry['setup']:>8}  {entry['set']:<10} n={entry['n']:<3}"
                f" top1={entry['root_cause_top1_rate']:5.0%} [{low:.0%}, {high:.0%}]"
                f" false_alarm={entry['false_alarm_rate']:4.0%}"
                f" p50={entry['latency_p50_ms']:.0f}ms"
                f" cost=${entry['cost_usd_mean']:.4f}"
            )
        print(f"{len(results['rows'])} rows written to {args.output}")
        if results["meta"]["errors"]:
            print(f"{results['meta']['errors']} investigations failed with errors; see the rows carrying an error field")

    chart_path = args.report.with_suffix(".svg")
    chart_path.parent.mkdir(parents=True, exist_ok=True)
    chart_path.write_text(chart_svg(results["aggregates"]) + "\n")
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(render_report(results, chart_name=chart_path.name))
    print(f"report written to {args.report} and {chart_path}")


if __name__ == "__main__":
    main()

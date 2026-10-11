import argparse
from pathlib import Path

from model_x_ray.benchmark.runner import (
    SETUP_NANO,
    SETUP_NO_TOOLS,
    SETUP_RULES,
    SETUP_SUPER,
    Setup,
    run_benchmark,
)
from model_x_ray.dataset import generate

SETUPS: dict[str, Setup] = {
    "rules": SETUP_RULES,
    "nano": SETUP_NANO,
    "super": SETUP_SUPER,
    "no-tools": SETUP_NO_TOOLS,
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the planted-error benchmark")
    parser.add_argument("--dataset", type=Path, default=Path("dataset"))
    parser.add_argument("--output", type=Path, default=Path("docs/benchmark-results.json"))
    parser.add_argument(
        "--setups",
        default="rules",
        help=f"comma-separated set-ups or 'all' ({', '.join(SETUPS)}); the live ones spend Token Factory credits",
    )
    parser.add_argument("--per-set", type=int, default=25)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--regenerate", action="store_true", help="regenerate the dataset before running")
    args = parser.parse_args()

    names = list(SETUPS) if args.setups == "all" else [name.strip() for name in args.setups.split(",") if name.strip()]
    unknown = [name for name in names if name not in SETUPS]
    if unknown:
        parser.error(f"unknown set-ups: {', '.join(unknown)}; known: {', '.join(SETUPS)}")
    if args.regenerate or not (args.dataset / "manifest.json").is_file():
        manifest = generate(args.dataset, per_set=args.per_set, seed=args.seed)
        print(f"{len(manifest['variants'])} variants generated in {args.dataset}")

    results = run_benchmark(args.dataset, [SETUPS[name] for name in names], output=args.output)
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


if __name__ == "__main__":
    main()

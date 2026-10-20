import argparse
from pathlib import Path

from model_x_ray.benchmark.logic_sets import generate


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the simple budget and the SaaS forecast, each with a clean copy and one planted error per file")
    parser.add_argument("--output", type=Path, default=Path("demo"))
    args = parser.parse_args()
    for path in generate(args.output):
        print(path)


if __name__ == "__main__":
    main()

import argparse
from pathlib import Path

from model_x_ray.dataset import generate


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the planted-error benchmark dataset")
    parser.add_argument("--output", type=Path, default=Path("dataset"))
    parser.add_argument("--per-set", type=int, default=25)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    manifest = generate(args.output, per_set=args.per_set, seed=args.seed)
    print(f"{len(manifest['variants'])} variants in {args.output}")


if __name__ == "__main__":
    main()

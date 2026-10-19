import argparse
from pathlib import Path

from model_x_ray.demo_model import generate


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the NVIDIA demo model and its planted-error variant")
    parser.add_argument("--output", type=Path, default=Path("demo"))
    args = parser.parse_args()
    for path in generate(args.output):
        print(path)


if __name__ == "__main__":
    main()

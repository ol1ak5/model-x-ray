import argparse
from pathlib import Path

from model_x_ray.finance import render_markdown


def main() -> None:
    parser = argparse.ArgumentParser(description="Write the financial formula library as Markdown")
    parser.add_argument("--output", type=Path, default=Path("docs/financial-formulas.md"))
    args = parser.parse_args()
    args.output.write_text(render_markdown() + "\n")
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()

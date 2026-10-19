import argparse
import json
import urllib.request
from pathlib import Path


def fetch(url: str) -> dict:
    with urllib.request.urlopen(url) as response:
        return json.load(response)


def main() -> None:
    parser = argparse.ArgumentParser(description="Export recorded investigations for the dev demo stories")
    parser.add_argument("--base", default="http://localhost:8000")
    parser.add_argument("--review", required=True, help="investigation id paused for review")
    parser.add_argument("--done", required=True, help="investigation id closed after approval")
    parser.add_argument("--out", type=Path, default=Path("frontend/src/test/recorded"))
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    review = fetch(f"{args.base}/investigations/{args.review}")
    done = fetch(f"{args.base}/investigations/{args.done}")
    sheet = fetch(f"{args.base}/investigations/{args.review}/sheet")

    (args.out / "review.json").write_text(json.dumps(review, indent=2) + "\n")
    (args.out / "done.json").write_text(json.dumps(done, indent=2) + "\n")
    (args.out / "sheet.json").write_text(json.dumps(sheet, indent=2) + "\n")
    print(f"review {review['status']} target {review['target'] and review['target']['cell']}")
    print(f"done {done['status']} copy {done['corrected_copy_id']}")
    print(f"{len(sheet['rows'])} rows written to {args.out}")


if __name__ == "__main__":
    main()

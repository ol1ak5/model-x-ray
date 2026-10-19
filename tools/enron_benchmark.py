import argparse
import json
import shutil
import subprocess
import urllib.request
import zipfile
from pathlib import Path

from model_x_ray.benchmark.enron import INDEX_FILE, read_cases, run_case, split_by_spreadsheet, summarize
from model_x_ray.benchmark.runner import SETUP_RULES, SETUP_SUPER, Setup

CORPUS_URL = "https://ls13-www.cs.tu-dortmund.de/homepage/spreadsheets/enron-errors.zip"
SPLIT_FILE = Path("docs/enron-split.json")
SETUPS: dict[str, Setup] = {"rules": SETUP_RULES, "super": SETUP_SUPER}


def prepare(data: Path) -> None:
    archive = data / "enron-errors.zip"
    data.mkdir(parents=True, exist_ok=True)
    if not archive.is_file():
        urllib.request.urlretrieve(CORPUS_URL, archive)
    with zipfile.ZipFile(archive) as files:
        files.extractall(data / "original")
    index = next((data / "original").rglob(INDEX_FILE))
    shutil.copy(index, data / INDEX_FILE)
    for workbook in sorted(path for path in (data / "original").rglob("*") if path.suffix.lower() == ".xls"):
        target = data / "xlsx" / workbook.parent.name
        target.mkdir(parents=True, exist_ok=True)
        subprocess.run(["soffice", "--headless", "--convert-to", "xlsx", "--outdir", str(target), str(workbook)], check=False, capture_output=True)
    converted = len(list((data / "xlsx").rglob("*.xlsx")))
    print(f"{converted} workbooks converted into {data / 'xlsx'}")


def freeze_split(data: Path) -> dict:
    if SPLIT_FILE.is_file():
        return json.loads(SPLIT_FILE.read_text())
    split = {"seed": 42, "test_share": 0.2, **split_by_spreadsheet(read_cases(data), seed=42, test_share=0.2)}
    SPLIT_FILE.write_text(json.dumps(split, indent=1) + "\n")
    print(f"split frozen in {SPLIT_FILE}")
    return split


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate check mode on the Enron Errors Corpus (Schmitz and Jannach, 2016)")
    parser.add_argument("command", choices=["prepare", "run"])
    parser.add_argument("--data", type=Path, default=Path("enron_data"), help="where the corpus is downloaded and converted; never committed")
    parser.add_argument("--setup", choices=list(SETUPS), default="rules", help="'super' spends Token Factory credits")
    parser.add_argument("--split", choices=["tune", "test"], default="tune")
    parser.add_argument("--final", action="store_true", help="required to run the held-out test split")
    parser.add_argument("--limit", type=int, default=None, help="run only the first N cases")
    parser.add_argument("--controls", action="store_true", help="also run each corrected file to count false alarms")
    args = parser.parse_args()

    if args.command == "prepare":
        prepare(args.data)
        freeze_split(args.data)
        return
    if args.split == "test" and not args.final:
        parser.error("the test split is held out; pass --final only for the last run")
    split = freeze_split(args.data)
    cases = [case for case in read_cases(args.data) if case.spreadsheet in split[args.split]][: args.limit]
    setup = SETUPS[args.setup]
    rows = []
    for case in cases:
        rows.append(run_case(setup, case, args.data / "work"))
        if args.controls:
            rows.append(run_case(setup, case, args.data / "work", corrected=True))
        last = rows[-1]
        print(f"error {case.error}: {last.get('excluded') or last.get('error') or ('found' if last.get('root_cause_found') else 'not found')}", flush=True)
    output = args.data / f"results-{args.setup}-{args.split}.json"
    summary = summarize(rows)
    output.write_text(json.dumps({"summary": summary, "rows": rows}, indent=1, default=str))
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()

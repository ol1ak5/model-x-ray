import argparse
import json
import re
import subprocess
import urllib.request
from pathlib import Path

from model_x_ray.benchmark.planting import plant_model, run_planted, split_models, summarize
from model_x_ray.benchmark.runner import SETUP_RULES, SETUP_SUPER, SETUP_SUPER_3, Setup

PAGE = "https://pages.stern.nyu.edu/~adamodar/New_Home_Page/spreadsh.htm"
SPLIT_FILE = Path("docs/damodaran-split.json")
SETUPS: dict[str, Setup] = {"rules": SETUP_RULES, "super": SETUP_SUPER, "super-3": SETUP_SUPER_3}


def download(data: Path) -> None:
    originals = data / "original"
    originals.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(PAGE, headers={"User-Agent": "Mozilla/5.0"})
    page = urllib.request.urlopen(request).read().decode("latin-1")
    for link in sorted(set(re.findall(r'href="([^"]+\.xlsx?)"', page, re.IGNORECASE))):
        target = originals / Path(link).name
        if not target.is_file():
            urllib.request.urlretrieve(link, target)
    converted = data / "xlsx"
    converted.mkdir(exist_ok=True)
    for workbook in sorted(originals.iterdir()):
        if workbook.suffix.lower() == ".xls":
            subprocess.run(["soffice", "--headless", "--convert-to", "xlsx", "--outdir", str(converted), str(workbook)], check=False, capture_output=True)
        elif workbook.suffix.lower() == ".xlsx":
            (converted / workbook.name).write_bytes(workbook.read_bytes())


def prepare(data: Path) -> None:
    download(data)
    planted = []
    for workbook in sorted((data / "xlsx").glob("*.xlsx")):
        try:
            planted += plant_model(workbook, data / "variants")
        except Exception as error:
            print(f"{workbook.name}: not planted ({type(error).__name__})")
    (data / "planted.json").write_text(json.dumps(planted, indent=1, default=str))
    models = sorted({record["model"] for record in planted})
    if not SPLIT_FILE.is_file():
        SPLIT_FILE.write_text(json.dumps({"seed": 42, "test_share": 0.2, **split_models(models)}, indent=1) + "\n")
    print(f"{len(planted)} planted cases in {len(models)} models; split in {SPLIT_FILE}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate check mode on Aswath Damodaran's public models with planted errors")
    parser.add_argument("command", choices=["prepare", "run"])
    parser.add_argument("--data", type=Path, default=Path("damodaran_data"), help="downloaded and planted models; never committed")
    parser.add_argument("--setup", choices=list(SETUPS), default="rules", help="'super' spends Token Factory credits")
    parser.add_argument("--split", choices=["tune", "test"], default="tune")
    parser.add_argument("--final", action="store_true", help="required to run the held-out test split")
    parser.add_argument("--controls", action="store_true", help="also run each original model to count false alarms")
    parser.add_argument("--budget", type=float, default=1.0, help="stop once this many US dollars are spent")
    args = parser.parse_args()
    if args.command == "prepare":
        prepare(args.data)
        return
    if args.split == "test" and not args.final:
        parser.error("the test split is held out; pass --final only for the last run")
    split = json.loads(SPLIT_FILE.read_text())
    records = [record for record in json.loads((args.data / "planted.json").read_text()) if record["model"] in split[args.split]]
    setup = SETUPS[args.setup]
    rows, spent = [], 0.0
    jobs = [(record, None) for record in records]
    if args.controls:
        jobs += [(record, args.data / "xlsx" / f"{record['model']}.xlsx") for record in {r["model"]: r for r in records}.values()]
    for record, clean in jobs:
        if spent >= args.budget:
            print(f"budget of {args.budget} USD reached; stopping")
            break
        row = run_planted(setup, record, args.data / "work", clean_file=clean)
        rows.append(row)
        spent += row.get("cost_usd", 0.0)
        outcome = row["error"] or ("false alarm" if row.get("false_alarm") else "clean") if clean else row["error"] or ("found" if row.get("root_cause_found") else "not found")
        print(f"{row['model']} {row['error_type']}: {outcome} (spent {spent:.3f} USD)", flush=True)
    summary = summarize(rows)
    (args.data / f"results-{args.setup}-{args.split}.json").write_text(json.dumps({"summary": summary, "rows": rows}, indent=1, default=str))
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()

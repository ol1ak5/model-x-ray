import json
from pathlib import Path

from model_x_ray.benchmark.planting import ERROR_TYPES, plant_model, run_planted, split_models, summarize
from model_x_ray.benchmark.runner import SETUP_RULES
from model_x_ray.spreadsheet.xlsx import load_xlsx


def test_errors_are_planted_in_any_model_with_a_timeline_and_change_its_numbers(demo_workbook_path: Path, tmp_path: Path) -> None:
    records = plant_model(demo_workbook_path, tmp_path / "variants")

    kinds = {record["error_type"] for record in records}
    assert {"typed_value", "wrong_reference", "sign", "period_lag"} <= kinds <= set(ERROR_TYPES)
    for record in records:
        planted = load_xlsx(Path(record["file"]))
        assert planted.raw(record["cell"]) != record["original"]
        assert planted.value(record["cell"]) != record["original_value"]
        assert json.loads(Path(record["file"]).with_suffix(".json").read_text())["cell"] == record["cell"]
    assert plant_model(demo_workbook_path, tmp_path / "again") == [{**r, "file": r["file"].replace("variants", "again")} for r in records]


def test_models_are_split_by_model_and_the_rules_baseline_is_scored(demo_workbook_path: Path, tmp_path: Path) -> None:
    split = split_models([f"model-{i}" for i in range(10)], seed=42)
    assert split == split_models([f"model-{i}" for i in range(10)], seed=42)
    assert len(split["test"]) == 2 and not set(split["test"]) & set(split["tune"])

    records = plant_model(demo_workbook_path, tmp_path / "variants")
    typed = next(record for record in records if record["error_type"] == "typed_value")
    row = run_planted(SETUP_RULES, typed, tmp_path / "work")
    assert row["error"] is None and row["error_seen"] is True
    control = run_planted(SETUP_RULES, typed, tmp_path / "work", clean_file=demo_workbook_path)
    assert control["false_alarm"] is False

    summary = summarize([row, control])
    assert summary["cases"] == 1 and summary["false_alarms"] == "0 of 1"

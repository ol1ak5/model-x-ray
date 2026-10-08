import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from model_x_ray.dataset import generate
from model_x_ray.spreadsheet.xlsx import load_xlsx

ROOT = Path(__file__).resolve().parents[1]

PLANTED_SETS = ("type1", "type2", "type3", "type4", "blended")
ALL_SETS = ("type1", "type2", "type3", "type4", "blended", "overrides", "clean")
ERROR_TYPES = {
    "typed_value",
    "wrong_reference",
    "inconsistent_range",
    "sign_inconsistency",
    "period_inconsistency",
    "documented_override",
}
OVERRIDE_COMMENT = "Per budget meeting: keep as entered."


def ground_truth(output_dir: Path, set_name: str, index: int) -> dict:
    return json.loads((output_dir / set_name / f"variant-{index:03d}.json").read_text())


def test_generator_writes_every_set_with_the_design_counts(tmp_path: Path) -> None:
    manifest = generate(tmp_path, per_set=2, seed=42)

    expected = {"type1": 2, "type2": 2, "type3": 2, "type4": 2, "blended": 2, "overrides": 1, "clean": 1}
    assert manifest["seed"] == 42
    assert manifest["per_set"] == 2
    assert manifest["counts"] == expected
    assert len(manifest["variants"]) == sum(expected.values())
    assert (tmp_path / "base.xlsx").exists()
    for record in manifest["variants"]:
        assert record["set"] in ALL_SETS
        assert (tmp_path / record["file"]).exists()
        assert (tmp_path / record["ground_truth"]).exists()
    for set_name, count in expected.items():
        assert len(list((tmp_path / set_name).glob("variant-*.xlsx"))) == count


def test_planted_variants_differ_from_the_base_and_record_the_original_formula(tmp_path: Path) -> None:
    generate(tmp_path, per_set=2, seed=42)
    base = load_xlsx(tmp_path / "base.xlsx")

    plants_checked = 0
    for set_name in PLANTED_SETS:
        expected_plants = (2, 3) if set_name == "blended" else (1, 1)
        for index in range(2):
            ground = ground_truth(tmp_path, set_name, index)
            variant = load_xlsx(tmp_path / set_name / f"variant-{index:03d}.xlsx")
            assert expected_plants[0] <= len(ground["planted"]) <= expected_plants[1]
            assert ground["set"] == set_name
            for plant in ground["planted"]:
                assert plant["error_type"] in ERROR_TYPES
                assert plant["original_formula"] == base.formula(plant["cell"])
                assert variant.raw(plant["cell"]) != base.raw(plant["cell"])
                assert ground["expected_outputs"][plant["cell"]] == pytest.approx(base.value(plant["cell"]))
                plants_checked += 1
            assert len(ground["questions"]) == len(ground["planted"])
            for question in ground["questions"]:
                assert question["expected_verdict"] == "root_cause"
                assert question["text"].startswith("Why did ")
                assert re.search(r"change by -?\d+(?:\.\d+)?%", question["text"]), question["text"]
                assert question["target"] not in question["expected_error_cells"]
                assert question["target"] in ground["expected_outputs"]
                for cell in question["expected_error_cells"]:
                    assert cell in variant.all_precedents(question["target"]), (cell, question["target"])
    assert plants_checked >= 8


def test_clean_and_override_variants_keep_every_base_output(tmp_path: Path) -> None:
    generate(tmp_path, per_set=2, seed=42)
    base = load_xlsx(tmp_path / "base.xlsx")

    for set_name in ("clean", "overrides"):
        ground = ground_truth(tmp_path, set_name, 0)
        variant = load_xlsx(tmp_path / set_name / "variant-000.xlsx")
        assert ground["questions"][0]["expected_verdict"] == "no_error"
        assert ground["questions"][0]["expected_error_cells"] == []
        for ref, expected in ground["expected_outputs"].items():
            assert variant.value(ref) == pytest.approx(expected)
            if set_name == "clean":
                assert variant.formula(ref) == base.formula(ref)

    clean = ground_truth(tmp_path, "clean", 0)
    assert clean["planted"] == []

    override = ground_truth(tmp_path, "overrides", 0)
    assert len(override["planted"]) == 1
    plant = override["planted"][0]
    assert plant["error_type"] == "documented_override"
    assert plant["comment"] == OVERRIDE_COMMENT
    variant = load_xlsx(tmp_path / "overrides" / "variant-000.xlsx")
    assert variant.formula(plant["cell"]) is None
    assert variant.note(plant["cell"]) == OVERRIDE_COMMENT
    assert variant.raw(plant["cell"]) == pytest.approx(base.value(plant["cell"]))


def test_the_same_seed_reproduces_the_same_dataset(tmp_path: Path) -> None:
    first = generate(tmp_path / "first", per_set=2, seed=7)
    second = generate(tmp_path / "second", per_set=2, seed=7)

    assert first == second
    for record in first["variants"]:
        first_json = (tmp_path / "first" / record["ground_truth"]).read_text()
        second_json = (tmp_path / "second" / record["ground_truth"]).read_text()
        assert first_json == second_json


def test_the_cli_wrapper_generates_the_dataset(tmp_path: Path) -> None:
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "generate_dataset.py"),
            "--output",
            str(tmp_path),
            "--per-set",
            "2",
            "--seed",
            "42",
        ],
        check=True,
        capture_output=True,
        text=True,
        cwd=ROOT,
    )

    assert (tmp_path / "manifest.json").exists()
    assert (tmp_path / "type1" / "variant-000.xlsx").exists()
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert len(manifest["variants"]) == 12

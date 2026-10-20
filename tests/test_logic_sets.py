import json
from pathlib import Path
from uuid import uuid4

from conftest import ScriptedVerdict
from test_investigator import ScriptedDiagnosis

from model_x_ray.benchmark.logic_sets import generate
from model_x_ray.benchmark.runner import Setup, build_setup_graph, drive_graph
from model_x_ray.spreadsheet.sandbox import XlsxSandbox
from model_x_ray.spreadsheet.source import XlsxSource
from model_x_ray.spreadsheet.xlsx import load_xlsx

DEMO = Path(__file__).resolve().parents[1] / "demo"


def test_the_committed_logic_sets_match_their_generator_and_each_file_plants_exactly_its_listed_cells(tmp_path: Path) -> None:
    generate(tmp_path)
    for folder in ("simple-errors", "saas-errors"):
        assert (DEMO / folder / "cases.json").read_text() == (tmp_path / folder / "cases.json").read_text()
        clean = load_xlsx(DEMO / folder / "00-clean.xlsx")
        for ref in clean.cells():
            assert clean.value(ref) is not None, f"{folder} {ref} does not calculate"
        for case in json.loads((DEMO / folder / "cases.json").read_text()):
            committed, fresh = load_xlsx(DEMO / folder / case["file"]), load_xlsx(tmp_path / folder / case["file"])
            assert {ref: committed.raw(ref) for ref in committed.cells()} == {ref: fresh.raw(ref) for ref in fresh.cells()}
            assert sorted(ref for ref in committed.cells() if committed.raw(ref) != clean.raw(ref)) == sorted(case["cells"])


def test_with_rules_alone_the_agent_fixes_the_six_mechanical_budget_errors_and_leaves_clean_copies_alone(tmp_path: Path) -> None:
    setup = Setup(name="offline", kind="investigator", model="silent", verifier="scripted-verifier")
    fixed = set()
    for folder in ("simple-errors", "saas-errors"):
        cases = [*json.loads((DEMO / folder / "cases.json").read_text()), {"file": "00-clean.xlsx", "cells": []}]
        for case in cases:
            source = XlsxSource({"m": DEMO / folder / case["file"]})
            graph = build_setup_graph(setup, source, XlsxSandbox(source, tmp_path), "m", lambda model_id: ScriptedVerdict() if model_id == "scripted-verifier" else ScriptedDiagnosis(turns=[([], None)]))
            final = drive_graph(graph, {"spreadsheet_id": "m", "question": ""}, {"configurable": {"thread_id": uuid4().hex}})
            patch, verifications = final.get("patch"), final.get("verifications", [])
            confirmed = bool(patch) and bool(verifications) and verifications[-1]["verdict"] == "confirmed"
            if not case["cells"]:
                assert not confirmed, f"false alarm on {folder}/00-clean.xlsx: {patch}"
            elif confirmed:
                assert patch["cell"] in case["cells"], f"{folder}/{case['file']} patched {patch['cell']}"
                fixed.add(f"{folder}/{case['file'][:2]}")
    assert fixed == {f"simple-errors/0{n}" for n in range(1, 7)}

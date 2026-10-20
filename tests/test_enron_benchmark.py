import shutil
from pathlib import Path

import openpyxl
from conftest import ScriptedVerdict
from test_investigator import ScriptedDiagnosis

from model_x_ray.benchmark.enron import read_cases, run_case, split_by_spreadsheet, summarize
from model_x_ray.benchmark.runner import SETUP_RULES, Setup

SCRIPTED = Setup(name="scripted", kind="investigator", model="scripted-investigator", verifier="scripted-verifier")


def scripted(model_id: str):
    if model_id == "scripted-verifier":
        return ScriptedVerdict()
    return ScriptedDiagnosis(turns=[(["P&L!H7"], "P&L!H7", "=G7*(1+Assumptions!$C$7)")])

HEADER = ["Error Nr", "Spreadsheet Nr", "Faulty Spreadsheet", "Faulty worksheet", "Faulty cells", "Corrected Spreadsheet", "Corrected worksheet", "Corrected cells", "Type", "Subtype", "Cell type", "Change", "Additional information"]


def write_corpus(root: Path, demo_workbook_path: Path) -> Path:
    root.mkdir(parents=True)
    index = openpyxl.Workbook()
    sheet = index.active
    for row in (["The Enron Errors Corpus"], ["Authors"], ["Download"], []):
        sheet.append(row)
    sheet.append(HEADER)
    sheet.append([1, 1, "1_Demo Model.xls", "P&L", "H7", "2_Demo Model.xls", "P&L", "H7", "Quantitative", "Mechanical", "Value", "Fixed", "Wrong values"])
    sheet.append([2, None, None, None, "G7", "2_Demo Model.xls", "P&L", "G7", "Quantitative", "Mechanical", "Formula", "Unchanged", "Second error in the same file"])
    for number in range(2, 11):
        sheet.append([number + 1, number, f"1_Model {number}.xls", "Sheet1", "B2", f"2_Model {number}.xls", "Sheet1", "B2", "Quantitative", "Logical", "Formula", "Fixed", "Wrong calculation"])
    index.save(root / "Enron-Errors.xlsx")
    folder = root / "xlsx" / "1"
    folder.mkdir(parents=True, exist_ok=True)
    shutil.copy(demo_workbook_path, folder / "1_Demo Model.xlsx")
    corrected = openpyxl.load_workbook(demo_workbook_path)
    corrected["P&L"]["H7"] = "=G7*(1+Assumptions!$C$7)"
    corrected.save(folder / "2_Demo Model.xlsx")
    return root


def test_cases_are_read_split_by_spreadsheet_and_scored_against_the_corrected_file(demo_workbook_path: Path, tmp_path: Path) -> None:
    corpus = write_corpus(tmp_path / "enron", demo_workbook_path)
    cases = read_cases(corpus)

    assert len(cases) == 11
    first, second = cases[0], cases[1]
    assert (first.spreadsheet, first.faulty_cells, first.corrected_cells) == (1, ["P&L!H7"], ["P&L!H7"])
    assert (second.spreadsheet, second.faulty_file, second.faulty_cells) == (1, first.faulty_file, ["P&L!G7"])
    assert first.faulty_file == corpus / "xlsx" / "1" / "1_Demo Model.xlsx"

    split = split_by_spreadsheet(cases, seed=42, test_share=0.2)
    assert split == split_by_spreadsheet(cases, seed=42, test_share=0.2)
    assert not set(split["tune"]) & set(split["test"])
    assert sorted(split["tune"] + split["test"]) == list(range(1, 11))
    assert sum(1 for case in cases if case.spreadsheet in split["test"]) == 2

    baseline = run_case(SETUP_RULES, first, tmp_path / "rules")
    assert (baseline["error"], baseline["error_seen"], baseline["root_cause_found"]) == (None, True, False)

    row = run_case(SCRIPTED, first, tmp_path / "work", factory=scripted)
    assert row["error"] is None
    assert row["root_cause_found"] is True
    assert row["error_seen"] is True
    assert row["fix_matches_correction"] is True
    assert row["latency_ms"] > 0

    control = run_case(SCRIPTED, first, tmp_path / "work", corrected=True, factory=scripted)
    assert control["false_alarm"] is False

    missing = run_case(SETUP_RULES, cases[2], tmp_path / "work")
    assert missing["excluded"].startswith("file not in the corpus download")

    summary = summarize([row, control, missing])
    assert summary["cases"] == 1
    assert summary["root_cause_found"] == "1 of 1"
    assert summary["false_alarms"] == "0 of 1"
    assert (summary["skipped"], summary["excluded"]) == (0, 1)


def test_a_control_fix_on_a_listed_error_the_correction_left_unchanged_is_not_a_false_alarm(demo_workbook_path: Path, tmp_path: Path) -> None:
    corpus = write_corpus(tmp_path / "enron", demo_workbook_path)
    first = read_cases(corpus)[0]
    known = {cell for case in read_cases(corpus) if case.spreadsheet == first.spreadsheet for cell in case.faulty_cells}

    fixed = run_case(SCRIPTED, first, tmp_path / "work", corrected=True, factory=scripted, known_errors=known)
    shutil.copy(first.faulty_file, first.corrected_file)
    kept = run_case(SCRIPTED, first, tmp_path / "work", corrected=True, factory=scripted, known_errors=known)

    assert (fixed["false_alarm"], fixed["known_error_kept"]) == (False, False)
    assert (kept["patched_cell"], kept["verdict"]) == ("P&L!H7", "confirmed")
    assert (kept["false_alarm"], kept["known_error_kept"]) == (False, True)
    summary = summarize([fixed, kept])
    assert (summary["false_alarms"], summary["known_errors_kept"]) == ("0 of 2", "1 of 2")

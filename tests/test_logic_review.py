import json
from pathlib import Path
from uuid import uuid4

import openpyxl

from conftest import ScriptedDiagnosis, ScriptedVerdict

from model_x_ray.benchmark.runner import Setup, build_setup_graph, drive_graph
from model_x_ray.spreadsheet.sandbox import XlsxSandbox
from model_x_ray.spreadsheet.source import XlsxSource

YEARS = "BCDEF"
INPUTS = {4: ("Revenue", [500, 540, 590, 640, 700]), 5: ("Cost of goods sold", [200, 214, 232, 250, 272]), 7: ("Salaries", [120, 126, 133, 140, 147]), 8: ("Rent", [30, 30, 32, 32, 34]), 9: ("Marketing", [25, 28, 30, 33, 36])}
FORMULAS = {6: ("Gross profit", "={c}4-{c}5"), 10: ("Total operating costs", "=SUM({c}7:{c}9)"), 11: ("EBITDA", "={c}6-{c}10"), 12: ("Taxes", "={c}11*$B$17"), 13: ("Net income", "={c}11-{c}12")}


def write_budget(path: Path, changes: dict[str, object] | None = None) -> Path:
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Budget"
    sheet["A3"] = "EUR k"
    for index, column in enumerate(YEARS):
        sheet[f"{column}3"] = str(2022 + index)
    for row, (label, values) in INPUTS.items():
        sheet[f"A{row}"] = label
        for column, value in zip(YEARS, values):
            sheet[f"{column}{row}"] = value
    for row, (label, formula) in FORMULAS.items():
        sheet[f"A{row}"] = label
        for column in YEARS:
            sheet[f"{column}{row}"] = formula.format(c=column)
    sheet["G3"] = "Total"
    for row in range(4, 14):
        sheet[f"G{row}"] = f"=SUM(B{row}:F{row})"
    sheet["A17"], sheet["B17"] = "Tax rate", 0.25
    for ref, content in (changes or {}).items():
        sheet[ref] = content
    workbook.save(path)
    return path


def investigate(tmp_path: Path, path: Path, model: ScriptedDiagnosis, verdict: ScriptedVerdict | None = None) -> dict:
    setup = Setup(name="scripted", kind="investigator", model="scripted-investigator", verifier="scripted-verifier")
    source = XlsxSource({"budget": path})
    judge = verdict or ScriptedVerdict()
    graph = build_setup_graph(setup, source, XlsxSandbox(source, tmp_path / "corrected"), "budget", lambda model_id: judge if model_id == "scripted-verifier" else model)
    return drive_graph(graph, {"spreadsheet_id": "budget", "question": ""}, {"configurable": {"thread_id": uuid4().hex}})


def test_a_gross_profit_line_that_adds_its_costs_in_every_year_reaches_the_model_as_words_and_is_reported(tmp_path: Path) -> None:
    path = write_budget(tmp_path / "budget.xlsx", {f"{c}6": f"={c}4+{c}5" for c in YEARS})
    model = ScriptedDiagnosis(briefs=[], turns=[(["Budget!D6"], None, "", "logic_error")])

    final = investigate(tmp_path, path, model)

    brief = model.briefs[0]
    assert "Gross profit = Revenue + Cost of goods sold" in brief
    assert "Net income = EBITDA - Taxes" in brief
    assert "Taxes = EBITDA * Tax rate" in brief
    assert "Total operating costs = SUM(Salaries to Marketing)" in brief
    assert "same in 2022 to 2026" in brief
    assert "Budget total column G: each line summed over 2022 to 2026" in brief
    assert "Revenue = SUM(" not in brief
    assert "values: Revenue 700, Cost of goods sold 272 -> 972" in brief
    assert "Suspicious inputs:" not in brief
    assert [(h["cell"], h["error_type"]) for h in final["hypotheses"]] == [("Budget!D6", "logic_error")]
    assert "D6" in final["report"]
    assert final.get("corrected_copy_id") is None


def test_an_ebitda_that_skips_the_cost_total_shows_the_total_as_a_line_nothing_uses(tmp_path: Path) -> None:
    path = write_budget(tmp_path / "budget.xlsx", {f"{c}11": f"={c}6-{c}7" for c in YEARS})
    model = ScriptedDiagnosis(briefs=[], turns=[([], None)])

    investigate(tmp_path, path, model)

    brief = model.briefs[0]
    assert "EBITDA = Gross profit - Salaries" in brief
    assert "Total operating costs = SUM(Salaries to Marketing)" in brief
    assert "Calculated but used by no other line: Total operating costs (row 10), Net income (row 13)" in brief


def test_a_rent_typed_ten_times_too_large_is_shown_as_a_suspicious_input(tmp_path: Path) -> None:
    path = write_budget(tmp_path / "budget.xlsx", {"D8": 320})
    model = ScriptedDiagnosis(briefs=[], turns=[(["Budget!D8"], None, "", "input_outlier")])

    final = investigate(tmp_path, path, model)

    brief = model.briefs[0]
    assert "Suspicious inputs:" in brief
    assert "Budget!D8 Rent 2024 = 320" in brief
    assert [(h["cell"], h["error_type"]) for h in final["hypotheses"]] == [("Budget!D8", "input_outlier")]
    assert "D8" in final["report"]


def test_the_clean_budget_gets_the_logic_map_and_no_suspicious_inputs(tmp_path: Path) -> None:
    model = ScriptedDiagnosis(briefs=[], turns=[([], None)])

    final = investigate(tmp_path, write_budget(tmp_path / "budget.xlsx"), model)

    assert "Gross profit = Revenue - Cost of goods sold" in model.briefs[0]
    assert "Calculated but used by no other line: Net income (row 13)" in model.briefs[0]
    assert "Suspicious inputs:" not in model.briefs[0]
    assert final["hypotheses"] == []
    assert final["report"].startswith("No error found")


def test_each_line_is_shown_next_to_the_standard_finance_definition_its_label_names(tmp_path: Path) -> None:
    path = write_budget(tmp_path / "budget.xlsx", {f"{c}11": f"={c}6-{c}7" for c in YEARS})
    model = ScriptedDiagnosis(briefs=[], turns=[([], None)])

    investigate(tmp_path, path, model)

    lines = {line.split(": ", 1)[1].split(" = ", 1)[0]: line for line in model.briefs[0].splitlines() if line.startswith("- Budget row")}
    assert "standard: revenue - cost_of_goods_sold" in lines["Gross profit"]
    assert "standard: gross_profit - total_operating_costs" in lines["EBITDA"]
    assert "standard: pre_tax_income - taxes" in lines["Net income"]
    assert "standard: sum of the operating cost lines" in lines["Total operating costs"]
    assert "enterprise" not in model.briefs[0]


def test_a_gross_profit_that_adds_its_costs_in_every_year_is_fixed_on_the_whole_line_and_verified(tmp_path: Path) -> None:
    from model_x_ray.spreadsheet.xlsx import load_xlsx

    path = write_budget(tmp_path / "budget.xlsx", {f"{c}6": f"={c}4+{c}5" for c in YEARS})
    model = ScriptedDiagnosis(briefs=[], turns=[(["Budget!F6"], "Budget!F6", "=F4-F5", "logic_error")])
    verdict = ScriptedVerdict(human=[])

    final = investigate(tmp_path, path, model, verdict)

    package = json.loads(verdict.human[0])
    assert package["anomaly"]["kind"] == "line logic error"
    assert "Gross profit: from Revenue + Cost of goods sold to Revenue - Cost of goods sold in 5 periods" in package["anomaly"]["finding"]
    assert "standard: revenue - cost_of_goods_sold" in package["anomaly"]["finding"]

    patch = final["patch"]
    assert (patch["cell"], patch["new_formula"]) == ("Budget!F6", "=F4-F5")
    assert [(c["cell"], c["new_formula"]) for c in patch["also"]] == [("Budget!B6", "=B4-B5"), ("Budget!C6", "=C4-C5"), ("Budget!D6", "=D4-D5"), ("Budget!E6", "=E4-E5")]
    assert final["verifications"][-1]["verdict"] == "confirmed"
    assert final["verifications"][-1]["checks"] == {"anomaly_resolved": True, "dependents_consistent": True, "pattern_restored": True}
    corrected = load_xlsx(tmp_path / "corrected" / final["corrected_copy_id"])
    assert [corrected.formula(f"Budget!{c}6") for c in YEARS] == [f"={c}4-{c}5" for c in YEARS]
    assert corrected.value("Budget!D13") == (590 - 232 - (133 + 32 + 30)) * 0.75


def test_a_net_income_that_never_subtracts_taxes_is_fixed_on_the_whole_line_even_when_the_reviewed_result_is_another_line(tmp_path: Path) -> None:
    path = write_budget(tmp_path / "budget.xlsx", {f"{c}13": f"={c}11" for c in YEARS})
    model = ScriptedDiagnosis(briefs=[], turns=[(["Budget!D13"], "Budget!D13", "=D11-D12", "logic_error")])

    final = investigate(tmp_path, path, model)

    assert len(final["patch"]["also"]) == 4
    assert final["verifications"][-1]["verdict"] == "confirmed"
    assert "Budget!D13" in final["report"]


def test_the_logic_review_asks_three_times_and_keeps_only_what_a_majority_finds(tmp_path: Path) -> None:
    path = write_budget(tmp_path / "budget.xlsx", {f"{c}6": f"={c}4+{c}5" for c in YEARS})
    found, silent = (["Budget!F6"], "Budget!F6", "=F4-F5", "logic_error"), ([], None)
    model = ScriptedDiagnosis(briefs=[], turns=[found, silent, found])

    final = investigate(tmp_path, path, model)

    assert len(model.briefs) == 3
    assert [(h["cell"], h["error_type"]) for h in final["hypotheses"]] == [("Budget!F6", "logic_error")]
    assert final["verifications"][-1]["verdict"] == "confirmed"
    assert final["decisions"][0]["votes"] == {"Budget!F6": 2}
    ballots = final["decisions"][0]["ballots"]
    assert [[h["cell"] for h in ballot["hypotheses"]] for ballot in ballots] == [["Budget!F6"], [], ["Budget!F6"]]
    assert ballots[0]["hypotheses"][0]["error_type"] == "logic_error" and ballots[0]["patch"] == "Budget!F6 =F4-F5"


def test_a_finding_only_one_of_the_three_reviews_makes_is_dropped(tmp_path: Path) -> None:
    path = write_budget(tmp_path / "budget.xlsx", {"D8": 320})
    once = (["Budget!D8"], None, "", "input_outlier")
    model = ScriptedDiagnosis(briefs=[], turns=[([], None), once, ([], None)])

    final = investigate(tmp_path, path, model)

    assert len(model.briefs) == 3
    assert final["hypotheses"] == []
    assert final["decisions"][0]["votes"] == {"Budget!D8": 1}
    assert final["report"].startswith("No error found")

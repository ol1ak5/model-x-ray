from datetime import date, datetime
from pathlib import Path

import openpyxl
import pytest
from conftest import EngineSandbox, ScriptedAnswer
from langgraph.checkpoint.memory import InMemorySaver
from test_investigator import ScriptedDiagnosis

from model_x_ray.agents.locator import read_question, workbook_catalogue
from model_x_ray.graph import run_investigation
from model_x_ray.spreadsheet.source import XlsxSource
from model_x_ray.spreadsheet.xlsx import load_xlsx

COLUMNS = "MNOPQ"
EPOCH = date(1899, 12, 30)


def serial(day: date) -> float:
    return float((day - EPOCH).days)


def write_project_model(path: Path, planted: float | None = None) -> Path:
    book = openpyxl.Workbook()
    inputs = book.active
    inputs.title = "Inputs"
    inputs["E5"], inputs["F5"] = "Spain", "Italy"
    inputs["C7"], inputs["I7"] = "Annual Usage", 1000
    inputs["C10"], inputs["I10"] = "Discount Rate", 0.07
    inputs["C11"], inputs["I11"] = "Contract Length", 3
    inputs["C17"], inputs["E17"], inputs["F17"] = "PPA Price", 50, 90

    fm = book.create_sheet("FM")
    fm["C3"], fm["C4"], fm["C5"], fm["C6"] = "BoP", "EoP", "Year", "# Year"
    fm["M3"], fm["M6"] = datetime(2026, 1, 1), 0
    fm["M4"], fm["M5"] = "=EOMONTH(M3,11)", "=YEAR(M4)"
    for prior, column in zip(COLUMNS, COLUMNS[1:]):
        fm[f"{column}3"] = f"={prior}4+1"
        fm[f"{column}4"] = f"=EOMONTH({column}3,11)"
        fm[f"{column}5"] = f"=YEAR({column}4)"
        fm[f"{column}6"] = f"={prior}6+1"
    fm["B9"], fm["I9"] = "Financial Model", "Units"
    fm["C13"], fm["E13"] = "Start", "=N3"
    fm["C14"], fm["E14"] = "Period", "=Inputs!I11"
    fm["C15"], fm["E15"] = "End", "=EDATE(E13,E14*12)-1"
    fm["B17"], fm["C17"] = "=MAX($B$1:B16)+1", "Production"
    fm["C19"], fm["I19"] = "Annual Net Production", "text"
    fm["C20"], fm["E20"], fm["I20"] = "Spain", "=Inputs!$I$7", "MWh"
    fm["C21"], fm["E21"], fm["I21"] = "Italy", "=Inputs!$I$7", "MWh"
    fm["C23"] = "Annual Cash Flow"
    fm["C24"], fm["I24"], fm["M24"] = "Spain", "€'k", 0
    fm["C25"], fm["I25"], fm["M25"] = "Italy", "€'k", 0
    fm["N26"] = " "
    fm["C27"], fm["E27"] = "Discount rate", "=Inputs!I10"
    fm["C29"] = "NPV"
    fm["C30"], fm["E30"] = "Spain", "=XNPV($E$27,M24:Q24,$M$4:$Q$4)"
    fm["C31"], fm["E31"] = "Italy", "=NPV($E$27,N25:Q25)"
    for column in COLUMNS[1:]:
        fm[f"{column}14"] = f"=IF(AND($E13<={column}$3,$E15>={column}$4),1,0)"
        fm[f"{column}20"] = f"=$E20*{column}$14"
        fm[f"{column}21"] = f"=$E21*{column}$14"
        fm[f"{column}24"] = f"={column}20*Inputs!$E$17/1000"
        fm[f"{column}25"] = f"={column}21*Inputs!$F$17/1000"
    if planted is not None:
        fm["O24"] = planted
    book.save(path)
    return path


def test_formula_timelines_block_labels_and_date_and_valuation_functions_are_understood(tmp_path: Path) -> None:
    book = load_xlsx(write_project_model(tmp_path / "project.xlsx"))

    assert book.value("FM!O5") == 2028.0
    assert book.value("FM!E15") == serial(date(2029, 12, 31))
    assert [book.value(f"FM!{c}14") for c in COLUMNS[1:]] == [1, 1, 1, 0]
    assert book.value("FM!O24") == 50.0

    flows = {date(2026, 12, 31): 0.0, date(2027, 12, 31): 50.0, date(2028, 12, 31): 50.0, date(2029, 12, 31): 50.0, date(2030, 12, 31): 0.0}
    xnpv = sum(value / 1.07 ** ((day - date(2026, 12, 31)).days / 365) for day, value in flows.items())
    assert book.value("FM!E30") == pytest.approx(xnpv)
    assert book.value("FM!E31") == pytest.approx(sum(90 / 1.07 ** year for year in (1, 2, 3)))

    assert book.column_header("FM!O24") == "2028"
    assert book.header_row("FM!O24") == 5
    assert book.column_header("FM!M24") == "2026"
    assert book.column_header("FM!N27") != " "
    assert book.row_label("FM!O24") == "Annual Cash Flow – Spain"
    assert book.row_label("FM!O20") == "Annual Net Production – Spain"
    assert book.row_label("FM!E30") == "NPV – Spain"
    assert book.row_label("FM!E27") == "Discount rate"

    catalogue = workbook_catalogue(book)
    assert {"2027", "2028", "2029"} <= set(catalogue.periods)
    assert "Annual Cash Flow – Italy" in catalogue.labels
    assert "Spain" not in catalogue.labels
    request = read_question("Why did the annual cash flow for Spain jump in 2028?", catalogue)
    assert (request.label, request.period) == ("Annual Cash Flow – Spain", "2028")


def test_an_investigation_finds_a_typed_cash_flow_in_a_project_model(tmp_path: Path, scripted_verdict) -> None:
    path = write_project_model(tmp_path / "project.xlsx", planted=55.0)
    source = XlsxSource({"project": path})
    diagnosis = ScriptedDiagnosis(turns=[(["FM!O24"], "FM!O24", "=O20*Inputs!$E$17/1000")])
    graph = run_investigation(diagnosis, "project", source, EngineSandbox(source), InMemorySaver(), verifier=scripted_verdict, locator=ScriptedAnswer(tool="LocateRequest"))
    config = {"configurable": {"thread_id": "project"}}

    graph.invoke({"spreadsheet_id": "project", "question": "Why did the annual cash flow for Spain jump in 2028?"}, config)
    state = graph.get_state(config).values

    assert (state["target"]["cell"], state["target"]["prior_cell"], state["target"]["period"]) == ("O24", "N24", "2028")
    assert state["target"]["label"] == "Annual Cash Flow – Spain"
    assert state["hypotheses"][0]["status"] == "confirmed"
    assert state["verifications"][-1]["after"]["FM!O24"] == 50.0
    assert state["verifications"][-1]["after"]["FM!E30"] < state["verifications"][-1]["before"]["FM!E30"]

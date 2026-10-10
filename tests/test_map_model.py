from pathlib import Path

import pytest
from conftest import ScriptedAnswer
from langgraph.checkpoint.memory import InMemorySaver
from openpyxl import Workbook as OpenpyxlWorkbook

from model_x_ray import nodes
from model_x_ray.agents.investigator import investigation_brief
from model_x_ray.agents.locator import make_choose_target_node, make_locate_node
from model_x_ray.agents.mapper import make_map_model_node
from model_x_ray.graph import build_graph
from model_x_ray.llm import build_chat_model
from model_x_ray.spreadsheet.source import XlsxSource
from model_x_ray.spreadsheet.xlsx import load_xlsx

DEMO_MAP = {
    "rows": [
        {"label": "Revenue", "kind": "revenue"},
        {"label": "COGS", "kind": "cost"},
        {"label": "Gross profit", "kind": "subtotal"},
        {"label": "Opex", "kind": "cost"},
        {"label": "EBITDA", "kind": "subtotal"},
        {"label": "EBITDA growth", "kind": "ratio"},
        {"label": "Net income", "kind": "subtotal"},
    ],
    "columns": [
        {"period": "2025A", "kind": "actual"},
        {"period": "2026E", "kind": "forecast"},
        {"period": "2027E", "kind": "forecast"},
        {"period": "2028E", "kind": "forecast"},
    ],
}


def investigate(book, mapper, locator, question: str):
    overrides = {
        "load_sheet": nodes.make_load_sheet_node(book),
        "map_model": make_map_model_node(mapper, book),
        "locate": make_locate_node(locator, book),
        "choose_target": make_choose_target_node(book),
    }
    graph = build_graph(InMemorySaver(), diagnose=nodes.stub_diagnose, overrides=overrides)
    config = {"configurable": {"thread_id": question}}
    graph.invoke({"spreadsheet_id": "demo", "question": question}, config)
    return graph.get_state(config).values


def test_the_model_map_labels_every_line_and_period_and_drops_invented_names(demo_workbook_path: Path) -> None:
    book = load_xlsx(demo_workbook_path)
    mapper = ScriptedAnswer(tool="ModelMapAnswer", answer=DEMO_MAP)
    state = investigate(book, mapper, ScriptedAnswer(tool="LocateRequest"), "Why did EBITDA jump in 2027?")

    brief = mapper.prompts[0]
    assert "Periods: 2025A, 2026E, 2027E" in brief
    assert "EBITDA: =H6+H7; uses Gross profit, Opex" in brief
    assert "Opex: typed number" in brief

    rows = {r["label"]: r["kind"] for r in state["model_map"]["rows"]}
    assert rows == {"Revenue": "revenue", "COGS": "cost", "Gross profit": "subtotal", "Opex": "cost", "EBITDA": "subtotal", "EBITDA growth": "ratio"}
    assert [c["period"] for c in state["model_map"]["columns"]] == ["2025A", "2026E", "2027E"]
    assert [entry["role"] for entry in state["run_log"]] == ["mapper"]


def test_locate_and_the_investigator_both_read_the_model_map(demo_workbook_path: Path) -> None:
    book = load_xlsx(demo_workbook_path)
    locator = ScriptedAnswer(tool="LocateRequest", answer={"label": "EBITDA", "period": "2027E", "sheet": None})
    state = investigate(book, ScriptedAnswer(tool="ModelMapAnswer", answer=DEMO_MAP), locator, "Why did operating profit before depreciation jump next year?")

    assert "Actual periods: 2025A" in locator.prompts[0]
    assert "Forecast periods: 2026E, 2027E" in locator.prompts[0]
    assert state["target"]["cell"] == "H8"

    brief = investigation_brief(state)
    assert "Model map: Revenue (revenue), COGS (cost), Gross profit (subtotal), Opex (cost), EBITDA (subtotal), EBITDA growth (ratio)" in brief
    assert "Periods: 2025A (actual), 2026E (forecast), 2027E (forecast)" in brief


def test_a_missing_or_unreadable_workbook_fails_with_a_clear_message(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Unknown spreadsheet 'other'"):
        XlsxSource({"demo": tmp_path / "demo.xlsx"}).load("other")
    with pytest.raises(ValueError, match="does not exist"):
        XlsxSource({"demo": tmp_path / "demo.xlsx"}).load("demo")

    blank = OpenpyxlWorkbook()
    blank.active["B2"] = 12.5
    blank.save(tmp_path / "blank.xlsx")
    book = XlsxSource({"blank": tmp_path / "blank.xlsx"}).load("blank")
    with pytest.raises(ValueError, match="cannot read it"):
        investigate(book, ScriptedAnswer(tool="ModelMapAnswer", answer=DEMO_MAP), ScriptedAnswer(tool="LocateRequest"), "Why?")


@pytest.mark.live
def test_lightning_maps_the_demo_model(demo_workbook_path: Path) -> None:
    book = load_xlsx(demo_workbook_path)
    state = investigate(book, build_chat_model(role="mapper"), ScriptedAnswer(tool="LocateRequest"), "Why did EBITDA jump in 2027?")

    rows = {r["label"]: r["kind"] for r in state["model_map"]["rows"]}
    columns = {c["period"]: c["kind"] for c in state["model_map"]["columns"]}
    assert (rows["Revenue"], rows["COGS"], rows["EBITDA"], rows["EBITDA growth"]) == ("revenue", "cost", "subtotal", "ratio")
    assert columns == {"2025A": "actual", "2026E": "forecast", "2027E": "forecast"}

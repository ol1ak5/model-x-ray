from pathlib import Path

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from model_x_ray import nodes
from model_x_ray.agents.locator import make_choose_target_node, make_locate_node
from model_x_ray.graph import build_graph
from model_x_ray.llm import build_chat_model
from model_x_ray.spreadsheet.engine import Workbook
from model_x_ray.spreadsheet.xlsx import load_xlsx
from conftest import ScriptedAnswer


def ScriptedLocator(answer: dict | None = None) -> ScriptedAnswer:
    return ScriptedAnswer(tool="LocateRequest", answer=answer or {})


TWO_SHEETS = Workbook({
    "P&L!F3": "2025A", "P&L!G3": "2026E", "P&L!H3": "2027E",
    "P&L!A8": "EBITDA", "P&L!F8": 35.7, "P&L!G8": 40.0, "P&L!H8": 52.0,
    "Summary!B3": "2025A", "Summary!C3": "2026E", "Summary!D3": "2027E",
    "Summary!A10": "EBITDA", "Summary!B10": "='P&L'!F8", "Summary!C10": "='P&L'!G8", "Summary!D10": "='P&L'!H8",
})


def run(model, book: Workbook, question: str, thread: str, trace=None):
    overrides = {"locate": make_locate_node(model, book), "choose_target": make_choose_target_node(book)}
    if trace is not None:
        overrides["trace"] = trace
    graph = build_graph(InMemorySaver(), diagnose=nodes.stub_diagnose, overrides=overrides)
    config = {"configurable": {"thread_id": thread}}
    result = graph.invoke({"spreadsheet_id": "demo", "question": question}, config)
    return graph, config, result


def test_a_question_naming_a_line_and_year_is_located_without_calling_nemotron(demo_workbook_path: Path) -> None:
    book = load_xlsx(demo_workbook_path)
    model = ScriptedLocator()
    graph, config, _ = run(model, book, "Why did EBITDA jump in 2027?", "exact", nodes.make_trace_node(book))
    target = graph.get_state(config).values["target"]

    assert model.prompts == []
    assert graph.get_state(config).values.get("run_log", []) == []
    assert (target["sheet"], target["cell"], target["label"], target["period"]) == ("P&L", "H8", "EBITDA", "2027E")
    assert (target["prior_cell"], target["value"], target["prior_value"]) == ("G8", pytest.approx(52.01, abs=0.01), pytest.approx(40.03, abs=0.01))
    assert {c["cell"] for c in graph.get_state(config).values["contributions"]} >= {"P&L!H6", "P&L!H7"}
    assert graph.get_state(config).next == ("human_review",)


def test_a_question_naming_an_a_or_e_suffixed_period_resolves_without_nemotron(demo_workbook_path: Path) -> None:
    book = load_xlsx(demo_workbook_path)
    model = ScriptedLocator()
    graph, config, _ = run(model, book, "Why did EBITDA jump in 2026E?", "suffixed", nodes.make_trace_node(book))

    assert model.prompts == []
    target = graph.get_state(config).values["target"]
    assert (target["sheet"], target["cell"], target["label"], target["period"]) == ("P&L", "G8", "EBITDA", "2026E")
    assert (target["prior_cell"], target["value"]) == ("F8", pytest.approx(40.03, abs=0.01))


def test_a_suffixed_period_naming_a_line_on_two_sheets_still_pauses() -> None:
    graph, config, paused = run(ScriptedLocator(), TWO_SHEETS, "Why did EBITDA jump in 2026E?", "suffixed-ambiguous")

    assert graph.get_state(config).next == ("choose_target",)
    assert paused["__interrupt__"][0].value["candidates"] == ["P&L!G8", "Summary!C10"]


def test_other_wording_asks_nemotron_using_only_lines_and_periods_that_exist(demo_workbook_path: Path) -> None:
    book = load_xlsx(demo_workbook_path)
    model = ScriptedLocator(answer={"label": "EBITDA", "period": "2027E", "sheet": None})
    graph, config, _ = run(model, book, "Why did operating profit before depreciation jump next year?", "synonym")
    target = graph.get_state(config).values["target"]

    assert len(model.prompts) == 1
    assert [entry["role"] for entry in graph.get_state(config).values["run_log"]] == ["locate"]
    assert "Lines: Revenue, COGS, Gross profit, Opex, EBITDA, EBITDA growth" in model.prompts[0]
    assert "Periods: 2025A, 2026E, 2027E" in model.prompts[0]
    assert f"{target['sheet']}!{target['cell']}" == "P&L!H8"


def test_the_same_line_on_two_sheets_pauses_until_the_user_picks_one() -> None:
    graph, config, paused = run(ScriptedLocator(), TWO_SHEETS, "Why did EBITDA jump in 2027?", "ambiguous")

    assert graph.get_state(config).next == ("choose_target",)
    assert paused["__interrupt__"][0].value["candidates"] == ["P&L!H8", "Summary!D10"]

    graph.invoke(Command(resume={"ref": "Summary!D10"}), config)
    target = graph.get_state(config).values["target"]

    assert (target["sheet"], target["cell"], target["prior_cell"], target["value"]) == ("Summary", "D10", "C10", 52.0)


def test_resuming_after_a_pause_does_not_ask_nemotron_again() -> None:
    model = ScriptedLocator(answer={"label": "EBITDA", "period": "2027E", "sheet": None})
    graph, config, paused = run(model, TWO_SHEETS, "Why did operating profit before depreciation jump next year?", "one-call")

    assert paused["__interrupt__"][0].value["candidates"] == ["P&L!H8", "Summary!D10"]
    graph.invoke(Command(resume={"ref": "P&L!H8"}), config)

    assert len(model.prompts) == 1
    assert [entry["role"] for entry in graph.get_state(config).values["run_log"]] == ["locate"]
    assert graph.get_state(config).values["target"]["cell"] == "H8"


def test_naming_the_sheet_removes_the_ambiguity() -> None:
    graph, config, _ = run(ScriptedLocator(), TWO_SHEETS, "Why did EBITDA jump in 2027 on the Summary sheet?", "named-sheet")

    assert graph.get_state(config).values["target"]["sheet"] == "Summary"
    assert graph.get_state(config).next == ("human_review",)


def test_a_line_that_does_not_exist_pauses_and_asks_for_the_cell(demo_workbook_path: Path) -> None:
    book = load_xlsx(demo_workbook_path)
    model = ScriptedLocator(answer={"label": "Net income", "period": "2027E", "sheet": None})
    graph, config, paused = run(model, book, "Why did net income fall in 2027?", "missing")

    question = paused["__interrupt__"][0].value
    assert question["candidates"] == []
    assert "Net income" in question["question"]

    graph.invoke(Command(resume={"ref": "P&L!H8"}), config)
    assert graph.get_state(config).values["target"]["cell"] == "H8"


@pytest.mark.live
def test_nemotron_locates_a_reworded_question(demo_workbook_path: Path) -> None:
    book = load_xlsx(demo_workbook_path)
    graph, config, _ = run(build_chat_model(role="locate"), book, "Why did operating profit before depreciation and amortisation jump next year compared with this year?", "live")
    target = graph.get_state(config).values["target"]

    assert f"{target['sheet']}!{target['cell']}" == "P&L!H8"

import json
from pathlib import Path

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from model_x_ray import nodes
from model_x_ray.causal import build_causal_tree, explain_change
from model_x_ray.graph import build_graph
from model_x_ray.rules import row_fix
from model_x_ray.spreadsheet.engine import Workbook
from model_x_ray.spreadsheet.xlsx import load_xlsx


def test_explain_change_attributes_the_ebitda_jump_to_its_inputs(demo_workbook_path: Path) -> None:
    book = load_xlsx(demo_workbook_path)

    explanation = explain_change(book, "P&L!H8", "2026", "2027")

    assert explanation["cell"] == "P&L!H8"
    assert explanation["value_before"] == pytest.approx(40.03, abs=0.01)
    assert explanation["value_after"] == pytest.approx(52.01, abs=0.01)
    assert explanation["delta"] == pytest.approx(11.98, abs=0.01)

    contributions = {c["cell"]: c for c in explanation["contributions"]}
    assert set(contributions) == {"P&L!H6", "P&L!H7"}
    assert contributions["P&L!H6"]["label"] == "Gross profit"
    assert contributions["P&L!H6"]["delta"] == pytest.approx(7.20, abs=0.01)
    assert contributions["P&L!H7"]["label"] == "Opex"
    assert contributions["P&L!H7"]["delta"] == pytest.approx(4.78, abs=0.01)

    total = sum(c["delta"] for c in explanation["contributions"])
    assert total == pytest.approx(explanation["delta"], abs=0.01)


def test_causal_tree_marks_the_suspicious_branch_and_serializes(demo_workbook_path: Path) -> None:
    book = load_xlsx(demo_workbook_path)

    tree = build_causal_tree(book, "P&L!H8", "2026", "2027")

    assert tree["cell"] == "P&L!H8"
    assert tree["label"] == "EBITDA"
    assert tree["value_before"] == pytest.approx(40.03, abs=0.01)
    assert tree["value_after"] == pytest.approx(52.01, abs=0.01)
    assert tree["delta"] == pytest.approx(11.98, abs=0.01)
    assert tree["share_of_change"] == pytest.approx(1.0)
    assert tree["suspicious"] is False

    children = {c["cell"]: c for c in tree["children"]}
    assert set(children) == {"P&L!H6", "P&L!H7"}
    assert children["P&L!H7"]["label"] == "Opex"
    assert children["P&L!H7"]["delta"] == pytest.approx(4.78, abs=0.01)
    assert children["P&L!H7"]["suspicious"] is True
    assert children["P&L!H6"]["suspicious"] is False
    assert children["P&L!H6"]["share_of_change"] == pytest.approx(7.20 / 11.98, abs=0.01)

    gross_profit_children = {c["cell"]: c for c in children["P&L!H6"]["children"]}
    assert set(gross_profit_children) == {"P&L!H4", "P&L!H5"}
    revenue_children = {c["cell"] for c in gross_profit_children["P&L!H4"]["children"]}
    assert revenue_children == {"P&L!G4"}

    json.dumps(tree)


def test_causal_tree_before_and_after_a_fix_shows_the_change_collapse(demo_workbook_path: Path) -> None:
    book = load_xlsx(demo_workbook_path)
    patched = book.with_patch("P&L!H7", "=G7*(1+Assumptions!$C$7)")

    before_tree = build_causal_tree(book, "P&L!H8", "2026", "2027")
    after_tree = build_causal_tree(patched, "P&L!H8", "2026", "2027")

    assert before_tree["delta"] == pytest.approx(11.98, abs=0.01)
    assert after_tree["delta"] == pytest.approx(4.70, abs=0.05)
    assert after_tree["value_after"] == pytest.approx(44.73, abs=0.01)

    before_opex = {c["cell"]: c for c in before_tree["children"]}["P&L!H7"]
    after_opex = {c["cell"]: c for c in after_tree["children"]}["P&L!H7"]
    assert before_opex["suspicious"] is True
    assert after_opex["suspicious"] is False


def test_the_graph_trace_node_writes_contributions_and_the_causal_tree(demo_workbook_path: Path) -> None:
    book = load_xlsx(demo_workbook_path)
    graph = build_graph(InMemorySaver(), diagnose=nodes.stub_diagnose, overrides={"trace": nodes.make_trace_node(book)})
    config = {"configurable": {"thread_id": "trace-node"}}

    graph.invoke({"spreadsheet_id": "demo", "question": "Why did EBITDA 2027 jump on the P&L sheet?"}, config)
    state = graph.get_state(config).values

    assert {c["cell"] for c in state["contributions"]} == {"P&L!H6", "P&L!H7"}
    assert sum(c["delta"] for c in state["contributions"]) == pytest.approx(state["causal_tree"]["delta"], abs=0.01)
    assert state["causal_tree"]["cell"] == "P&L!H8"
    assert any(c["suspicious"] for c in state["causal_tree"]["children"])


def test_a_trailing_twelve_month_bridge_traces_without_shifting_off_the_sheet() -> None:
    book = Workbook({
        "TTM!A1": "Item", "TTM!B1": "Last 10K", "TTM!C1": "Year-ago 10Q", "TTM!D1": "Latest 10Q", "TTM!E1": "Trailing 12 month",
        "TTM!A2": "Revenues", "TTM!B2": 1200.0, "TTM!C2": 280.0, "TTM!D2": 330.0, "TTM!E2": "=B2-C2+D2",
        "TTM!A3": "EBIT", "TTM!B3": 240.0, "TTM!C3": 50.0, "TTM!D3": 70.0, "TTM!E3": "=B3-C3+D3",
    })

    explanation = explain_change(book, "TTM!E2", "Last 10K", "Trailing 12 month")
    tree = build_causal_tree(book, "TTM!E2", "Last 10K", "Trailing 12 month")

    assert explanation["value_before"] == pytest.approx(1200.0)
    assert explanation["value_after"] == pytest.approx(1250.0)
    assert explanation["delta"] == pytest.approx(50.0)
    assert explanation["contributions"] == []
    assert tree["cell"] == "TTM!E2"
    assert tree["delta"] == pytest.approx(50.0)
    assert tree["children"] == []


def test_a_two_year_growth_row_offers_no_fix_where_the_copied_formula_would_leave_the_sheet() -> None:
    book = Workbook({
        "Growth!B1": "2024", "Growth!C1": "2025", "Growth!D1": "2026", "Growth!E1": "2027", "Growth!F1": "2028",
        "Growth!B2": 100.0, "Growth!C2": 110.0, "Growth!D2": 125.0, "Growth!E2": 140.0, "Growth!F2": 150.0,
        "Growth!B3": 0.08, "Growth!C3": 0.1, "Growth!D3": "=D2/B2-1", "Growth!E3": "=E2/C2-1", "Growth!F3": "=F2/D2-1",
    })

    assert row_fix(book, "Growth!B3") is None
    assert row_fix(book, "Growth!C3") == "=C2/A2-1"
    assert row_fix(book, "Growth!E3") == "=E2/C2-1"
    assert book.shifted_formula("Growth!D3", "Growth!A3") is None

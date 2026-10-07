from pathlib import Path

from model_x_ray.spreadsheet.source import SpreadsheetSource, XlsxSource
from model_x_ray.spreadsheet.xlsx import load_xlsx
from model_x_ray.tools import (
    compare_formulas,
    find_cells,
    find_formula_outliers,
    get_cell,
    get_cell_metadata,
    make_read_only_tools,
    trace_dependents,
    trace_precedents,
)


def test_read_only_tools_expose_the_fixture_model_to_the_investigator(demo_workbook_path: Path) -> None:
    source: SpreadsheetSource = XlsxSource({"demo": demo_workbook_path})
    book = source.load("demo")

    assert source.list_sheets("demo") == ["P&L", "Assumptions"]
    assert source.read_range("demo", "P&L!A7:H7")["P&L!H7"] == -45.2
    assert source.read_range("demo", "P&L!G6:H6")["P&L!H6"] == "=H4+H5"
    assert source.row_label("demo", "P&L!H7") == "Opex"
    assert source.column_header("demo", "P&L!H7") == "2027E"

    assert find_cells(book, "Opex", "2027") == ["P&L!H7"]
    assert find_cells(book, "EBITDA", "2027") == ["P&L!H8"]

    assert get_cell(book, "P&L!H7") == "P&L!H7 Opex 2027E = -45.2, typed value, no formula, no note"
    assert get_cell(book, "P&L!H8").startswith("P&L!H8 EBITDA 2027E = ")
    assert "formula =H6+H7" in get_cell(book, "P&L!H8")

    assert trace_precedents(book, "P&L!H8", 1) == "P&L!H8 depends on P&L!H6, P&L!H7"
    assert trace_precedents(book, "P&L!H7", 1) == "P&L!H7 has no precedents: it is a typed value (-45.2)"
    deeper = trace_precedents(book, "P&L!H8", 2)
    assert "P&L!H6 depends on P&L!H4, P&L!H5" in deeper
    assert trace_dependents(book, "P&L!H7", 1) == "P&L!H7 is read by P&L!H8"
    assert "P&L!H4 is read by P&L!H5, P&L!H6" in trace_dependents(book, "P&L!H4", 2)


def test_find_formula_outliers_flags_the_planted_typed_value_in_forecast_columns(demo_workbook_path: Path) -> None:
    book = load_xlsx(demo_workbook_path)

    outliers = find_formula_outliers(book, "P&L!G4:H9")

    assert [o["cell"] for o in outliers] == ["P&L!H7"]
    assert "typed value" in outliers[0]["reason"]
    assert find_formula_outliers(book, "P&L!G4:H6") == []


def test_compare_formulas_explains_that_the_planted_cell_breaks_its_row(demo_workbook_path: Path) -> None:
    book = load_xlsx(demo_workbook_path)

    broken = compare_formulas(book, "P&L!H7", ["P&L!G7"])
    assert "P&L!H7 is a typed value (-45.2) with no formula" in broken
    assert book.formula_pattern("P&L!G7") in broken
    assert "breaks the pattern" in broken

    matching = compare_formulas(book, "P&L!H6", ["P&L!G6"])
    assert book.formula_pattern("P&L!H6") in matching
    assert "matches the row pattern" in matching


def test_get_cell_metadata_reports_notes_formats_and_colours(demo_workbook_path: Path, demo_workbook_with_override_note: Path) -> None:
    book = load_xlsx(demo_workbook_path)
    overridden = load_xlsx(demo_workbook_with_override_note)

    plain = get_cell_metadata(book, "P&L!F7")
    assert plain["font_color"] is not None and plain["font_color"].endswith("0000FF")
    assert plain["number_format"] == "0.0"
    assert plain["note"] is None

    note = get_cell_metadata(overridden, "P&L!H7")
    assert note["note"] == "Per budget meeting, opex frozen at 45.2"
    assert note["number_format"] == "0.0"

    patched = book.with_patch("P&L!H7", "=G7*(1+Assumptions!$C$7)")
    assert get_cell_metadata(patched, "P&L!F7")["font_color"] == plain["font_color"]

    metadata_tool = next(t for t in make_read_only_tools(book) if t.name == "get_cell_metadata")
    assert "no note" in metadata_tool.invoke({"ref": "P&L!H7"})


def test_make_read_only_tools_wraps_the_api_for_the_investigator(demo_workbook_path: Path) -> None:
    book = load_xlsx(demo_workbook_path)

    tools = make_read_only_tools(book)

    assert [t.name for t in tools] == [
        "find_cells",
        "get_cell",
        "trace_precedents",
        "trace_dependents",
        "compare_formulas",
        "find_formula_outliers",
        "get_cell_metadata",
    ]
    assert "Opex" in tools[1].invoke({"ref": "P&L!H7"})
    assert "P&L!H7" in tools[0].invoke({"label": "Opex", "period": "2027"})
    assert "P&L!H8 depends on" in tools[2].invoke({"ref": "P&L!H8"})

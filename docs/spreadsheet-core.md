# Spreadsheet core

The code that reads a financial model and understands it: cell contents, formulas, the dependency graph between cells, recalculation, and sandbox copies for testing a fix. The Investigator's tools and the `test` node are built on it. It is not the financial model itself; the model is the data it works on.

Issues: #5 (reading, dependency graph, tools), #6 (sandbox). Design context: `docs/agent-architecture.md` §Platform.

## Modules

| Module | Responsibility |
|---|---|
| `spreadsheet/engine.py` | `Workbook`: contents, notes, metadata, formulas, values, dependency graph, relative formula patterns, labels, patched copies |
| `spreadsheet/xlsx.py` | `load_xlsx(path)`: reads an `.xlsx` file (for example a model downloaded from Google Sheets with File, Download, Microsoft Excel) into a `Workbook` |
| `spreadsheet/source.py` | `SpreadsheetSource` protocol (`load`, `list_sheets`, `read_range`, `row_label`, `column_header`) and `XlsxSource`, which serves files by id |
| `spreadsheet/sandbox.py` | `Sandbox` protocol (`create_copy`, `apply_patch`, `read_values`, `discard`), `SandboxWithWrite` (adds `write_corrected_copy`), `GoogleSandbox`, `run_sandbox_test`, `a1_range`, `build_google_services` |
| `rules.py` | `find_formula_outliers(range)` — the pattern rules, independent of LangChain so the rules-only baseline (#16) can reuse them |
| `causal.py` | `explain_change` (one-input-at-a-time contributions) and `build_causal_tree` (the `CausalNode` dict, suspicious branches marked) |
| `tools.py` | The read-only investigation API the Investigator and the nodes call: `find_cells`, `get_cell`, `trace_precedents`, `trace_dependents`, `explain_change`, `compare_formulas`, `find_formula_outliers`, `get_cell_metadata`, plus `make_read_only_tools(book)` which wraps them as LangChain tools |

The Google Sheets API reader (#5) and sandbox (#6) will produce the same `Workbook`, so the tools and nodes do not depend on where the model came from.

## Workbook

Cells are addressed as `Sheet!A1` (for example `P&L!H8`, `Assumptions!C7`). Contents are numbers, text, booleans, or formulas (text starting with `=`). Notes come from cell comments.

| Method | Returns |
|---|---|
| `raw(ref)` | The stored content: number, text, or formula text |
| `formula(ref)` | The formula text, or `None` for a typed value |
| `value(ref)` | The calculated value |
| `note(ref)` | The cell note, or `None` |
| `precedents(ref)` / `all_precedents(ref)` | Cells the formula reads, directly / through the whole chain |
| `dependents(ref)` / `all_dependents(ref)` | Cells that read this cell, directly / through the whole chain |
| `formula_pattern(ref)` | The formula with references written relative to the cell (R1C1 style), or `None` for a typed value |
| `row_label(ref)` / `column_header(ref)` | The first text to the left in the row / the nearest text above in the column |
| `with_patch(ref, content)` | A new `Workbook` with one cell changed; the original is never modified |
| `metadata_of(ref)` | `CellMetadata`: cell note, font colour (blue = typed input convention), number format — signals for telling deliberate overrides from errors, never proof alone |

### Relative formula patterns

`formula_pattern` rewrites references relative to the cell, so formulas dragged across a row have identical patterns. `=F7*(1+Assumptions!$C$7)` in `G7` becomes `=RC[-1]*(1+Assumptions!R7C3)`: `R` means same row, `C[-1]` one column to the left, and `$`-anchored parts stay absolute (`R7C3`). A cell whose pattern differs from its neighbours, or that has no pattern because it is a typed value, breaks the row. This is what `compare_formulas` and `find_formula_outliers` build on.

## Formula support

Deliberately small, matching standard financial models:

- Numbers, percentages (`50%`), text in quotes, `TRUE` / `FALSE`
- References: `A1`, `$C$7`, ranges `A1:A3`, other sheets `Assumptions!C7` and quoted names `'P&L'!H8`
- Operators: `+ - * / ^`, unary minus, `&` (join text), comparisons `= <> < > <= >=`, parentheses
- Maths: `SUM`, `AVERAGE`, `MIN`, `MAX`, `ROUND` (half away from zero, as in Excel and Google Sheets), `ABS`, `SUMPRODUCT` (equal-size ranges, text counts as 0)
- Logic: `IF`, `IFERROR`, `AND`, `OR`, `NOT`
- Conditional sum: `SUMIF(range, criteria, [sum_range])` with criteria as a value (`"Data Center"`, `5`) or a comparison in text (`">10"`, `"<>US"`, `"="` for blanks)
- Lookups: `INDEX(range, row, [column])`, `MATCH(value, range, [type])` with type `0` (exact) or `1` (default: largest value not above the target, range sorted ascending), `VLOOKUP(value, table, column, [approximate])` (approximate by default, as in Excel), `XLOOKUP(value, lookup, results, [if_not_found])` (exact match)
- Dates: `EOMONTH(start, months)`. Dates are Excel serial numbers (days since 30 Dec 1899); a date typed in a cell is loaded as ISO text (so it can still be a column header) and turns into its serial number when a formula uses it as a number.
- Excel's `_xlfn.` prefix (how Excel stores newer functions such as `XLOOKUP` in the file) is ignored.

Errors behave like Excel's where it matters for models. `IF` evaluates only the branch it returns, so `=IF(G8=0,0,H8/G8)` works when `G8` is 0. `IFERROR` returns its fallback when the first argument fails with a formula error (division by zero, a lookup that finds nothing, text used as a number). It never hides an unsupported function or a circular reference, because those mean the engine cannot calculate the model, not that the model has an error. A lookup with no match raises `FormulaError("#N/A: ...")`; an `INDEX` outside its range raises `FormulaError("#REF: ...")`.

Every reference inside a function counts as a precedent, including whole ranges inside `SUMIF`, `INDEX`, `VLOOKUP` and `XLOOKUP`. This is deliberately cautious: a cell behind a lookup can always be traced.

Not supported, and raising `UnsupportedFormulaError` naming the function: `INDIRECT`, `OFFSET`, named ranges, wildcard criteria, `MATCH` type `-1`, approximate `XLOOKUP` modes, array maths inside `SUMPRODUCT` (such as `(A1:A3="x")*B1:B3`), and any other function. An unsupported model fails clearly instead of producing wrong numbers. Circular references raise `CircularReferenceError`. Empty cells count as 0 in arithmetic.

Consequence for building demo models (including the NVIDIA model): use only the functions above. Add a function here, with a test, when a model needs it (#86).

## Read-only tools

The LLM never interprets raw formulas on its own; it reads these (design: `docs/agent-architecture.md` §Tools):

| Tool | Returns |
|---|---|
| `find_cells(label, period)` | Cells whose row label and period header match; exact label first, then contains |
| `get_cell(ref)` | `ref label header = value, formula ...` or `typed value, no formula`, with the note when present |
| `trace_precedents(ref, depth)` | BFS lines `X depends on A, B` up to `depth`; typed cells report `no precedents: it is a typed value` |
| `trace_dependents(ref, depth)` | The mirror: `X is read by ...`, `nothing reads X` |
| `explain_change(ref, from_period, to_period)` | Target's before/after/delta plus each input's contribution, recomputed by patching inputs to the prior-period values one at a time |
| `compare_formulas(ref, reference_cells)` | Each neighbour's relative pattern and a verdict: `matches the row pattern` or `breaks the pattern` |
| `find_formula_outliers(range)` | Every cell in the range that is a typed value where its row uses formulas, or whose pattern differs from the row's (needs two agreeing formulas); the rules-only baseline of #16 |
| `get_cell_metadata(ref)` | `no note` / `note: ...`, font colour, number format |

Plain functions take the `Workbook` first (nodes and rules call those); `make_read_only_tools(book)` returns the LangChain-wrapped versions with the tool-only signatures for the Investigator.

## Sandbox

`with_patch` is the local recalculation engine; the `Sandbox` interface (`spreadsheet/sandbox.py`) is what the `test` step uses to prove a fix without ever writing the original:

| Piece | Behaviour |
|---|---|
| `Sandbox` protocol | `create_copy(spreadsheet_id)`, `apply_patch(copy_id, patch)`, `read_values(copy_id, cells)`, `discard(copy_id)` |
| `SandboxWithWrite` | adds `write_corrected_copy(...)` — the `apply_fix` node's capability, kept out of the test path by the narrower type |
| `run_sandbox_test(source, sandbox, id, patch)` | before-values from the source workbook, then copy → patch → read → discard (discard in a `finally`), returning `{"before": {...}, "after": {...}}` for the patched cell and every transitive dependent (`affected_cells` = the cell + `all_dependents`) |
| `GoogleSandbox(sheets, drive, folder_id=None)` | `files.copy` into a dedicated folder (created lazily, named `Model X-Ray sandbox`), `values.update` with `valueInputOption=USER_ENTERED` so Google enters the formula and recalculates, `values.batchGet` with `valueRenderOption=UNFORMATTED_VALUE`, `files.delete` on discard |
| `write_corrected_copy(...)` | copies the original into the same folder, applies the patch, adds a `Change log` tab (`addSheet`, then `values.update` on `'Change log'!A1` with the timestamp/cell/old/new/reason rows), and returns the id — it is never discarded |
| `a1_range(ref)` | `P&L!H7` → `'P&L'!H7`: quotes sheet names that are not plain identifiers |
| `build_google_services(path=None)` | service-account credentials from `GOOGLE_APPLICATION_CREDENTIALS`, scopes `spreadsheets` + `drive`; the google libraries are imported lazily so offline tests never touch them |

Tests use `EngineSandbox` (`tests/conftest.py`), which recalculates through the real engine on a `with_patch` copy, and `FakeGoogle` (`tests/test_sandbox.py`), a fluent stand-in for the discovery services that records every request. The live roundtrip test is marked `live` and needs the service account from #14.

## Testing

`tests/conftest.py` writes a small demo model to a real `.xlsx` file: an Assumptions sheet and a P&L where Opex 2027 (`P&L!H7`) is typed over instead of following the growth formula. The tests load it through `load_xlsx` and check values, the broken link to `Assumptions!C7`, the patched recalculation (EBITDA 2027 52.0 becomes 44.7, growth 29.9% becomes 11.7%), relative patterns, labels, notes, functions, quoted sheet names, and the clear errors.

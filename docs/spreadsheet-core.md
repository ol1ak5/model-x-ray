# Spreadsheet core

The code that reads a financial model and understands it: cell contents, formulas, the dependency graph between cells, recalculation, and sandbox copies for testing a fix. The Investigator's tools and the `test` node are built on it. It is not the financial model itself; the model is the data it works on.

Issues: #5 (reading, dependency graph, tools), #6 (sandbox). Design context: `docs/agent-architecture.md` §Platform.

## Modules

| Module | Responsibility |
|---|---|
| `spreadsheet/engine.py` | `Workbook`: contents, notes, formulas, values, dependency graph, relative formula patterns, labels, patched copies |
| `spreadsheet/xlsx.py` | `load_xlsx(path)`: reads an `.xlsx` file (for example a model downloaded from Google Sheets with File, Download, Microsoft Excel) into a `Workbook` |

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

### Relative formula patterns

`formula_pattern` rewrites references relative to the cell, so formulas dragged across a row have identical patterns. `=F7*(1+Assumptions!$C$7)` in `G7` becomes `=RC[-1]*(1+Assumptions!R7C3)`: `R` means same row, `C[-1]` one column to the left, and `$`-anchored parts stay absolute (`R7C3`). A cell whose pattern differs from its neighbours, or that has no pattern because it is a typed value, breaks the row. This is what `compare_formulas` and `find_formula_outliers` build on.

## Formula support

Deliberately small, matching standard financial models:

- Numbers, percentages (`50%`), text in quotes, `TRUE` / `FALSE`
- References: `A1`, `$C$7`, ranges `A1:A3`, other sheets `Assumptions!C7` and quoted names `'P&L'!H8`
- Operators: `+ - * / ^`, unary minus, `&` (join text), comparisons `= <> < > <= >=`, parentheses
- Functions: `SUM`, `AVERAGE`, `MIN`, `MAX`, `IF`, `ROUND` (half away from zero, as in Excel and Google Sheets), `ABS`

Anything else raises `UnsupportedFormulaError` naming the function, so an unsupported model fails clearly instead of producing wrong numbers. Circular references raise `CircularReferenceError`. Empty cells count as 0 in arithmetic.

Consequence for building demo models (including the NVIDIA model): use only the functions above. Add a function here, with a test, when a model needs it.

## Sandbox

`with_patch` is the local sandbox: it copies the cell contents, applies the patch, and recalculates lazily, so the before and after values of any cell can be compared while the original stays untouched. With Google Sheets, the same role is played by copying the spreadsheet and letting Google recalculate (#6).

## Testing

`tests/conftest.py` writes a small demo model to a real `.xlsx` file: an Assumptions sheet and a P&L where Opex 2027 (`P&L!H7`) is typed over instead of following the growth formula. The tests load it through `load_xlsx` and check values, the broken link to `Assumptions!C7`, the patched recalculation (EBITDA 2027 52.0 becomes 44.7, growth 29.9% becomes 11.7%), relative patterns, labels, notes, functions, quoted sheet names, and the clear errors.

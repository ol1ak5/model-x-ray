import re
from collections import Counter
from dataclasses import dataclass, field

from model_x_ray.spreadsheet.engine import ISO_DATE, FormulaError, Workbook, column_letters, is_label_text, is_number, split_ref

TOTAL_FORMULA = re.compile(r"^=\s*SUM\(", re.IGNORECASE)
PERIOD_TEXT = re.compile(r"(?i)^\s*((19|20)\d{2}\s*[abefp]?|fy\s*'?\d{2,4}[abef]?|[qh][1-4]\s*'?\s*(\d{2,4})?|year\s*-?\d+|(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*[\s'-]*\d{0,4})\s*$")
MIN_COPIES = 3
MIN_TABLE_ROWS = 4
COPY_SHARE = 0.6
MIN_CALCULATIONS = 1
DATA_SHARE = 0.9
TOTAL_GAP = 3
INPUT_SHARE = 0.6
SUMMARY_SHARE = 0.6


@dataclass(frozen=True)
class Block:
    sheet: str
    kind: str
    top: int
    bottom: int
    left: int
    right: int
    axis: str | None
    header_row: int | None
    evidence: str
    totals: list[str] = field(default_factory=list)
    periods: tuple[str, str] | None = None

    def contains(self, ref: str) -> bool:
        sheet, address = split_ref(ref)
        return sheet == self.sheet and self.top <= address.row <= self.bottom and self.left <= address.column <= self.right


def pattern_of(book: Workbook, ref: str) -> str | None:
    try:
        return book.formula_pattern(ref)
    except FormulaError:
        return None


def sheet_cells(book: Workbook, sheet: str) -> dict[tuple[int, int], str]:
    found = {}
    for ref in book.cells():
        cell_sheet, address = split_ref(ref)
        if cell_sheet == sheet:
            found[(address.row, address.column)] = ref
    return found


def text_timelines(book: Workbook, cells: dict[tuple[int, int], str]) -> list[tuple[int, dict[int, str]]]:
    rows: dict[int, dict[int, str]] = {}
    for (row, column), ref in cells.items():
        content = book.raw(ref)
        if isinstance(content, str) and PERIOD_TEXT.match(content):
            rows.setdefault(row, {})[column] = content.strip()
    return [(row, periods) for row, periods in sorted(rows.items()) if len(periods) >= MIN_COPIES]


def temporal_blocks(book: Workbook, sheet: str, cells: dict[tuple[int, int], str]) -> list[Block]:
    blocks = []
    numeric = book.timelines(sheet)
    numeric_rows = {row for row, _ in numeric}
    timelines = sorted(numeric + [timeline for timeline in text_timelines(book, cells) if timeline[0] not in numeric_rows])
    last_row = max((row for row, _ in cells), default=0)
    for index, (header, periods) in enumerate(timelines):
        end = timelines[index + 1][0] - 1 if index + 1 < len(timelines) else last_row
        columns = sorted(periods)
        lines = []
        for row in range(header + 1, end + 1):
            formulas = [cells[(row, column)] for column in columns if (row, column) in cells and book.formula(cells[(row, column)]) is not None]
            filled = [column for column in columns if (row, column) in cells]
            if filled:
                lines.append((row, len(formulas)))
        if not any(count >= 2 for _, count in lines):
            continue
        rows = [row for row, _ in lines]
        first, last = periods[columns[0]], periods[columns[-1]]
        evidence = f"{len(rows)} lines across {len(columns)} periods, {first} to {last}"
        blocks.append(Block(sheet, "temporal", min(rows), max(rows), min(columns), max(columns), "across", header, evidence, periods=(first, last)))
    return blocks


def safe_value(book: Workbook, ref: str) -> object:
    try:
        return book.value(ref)
    except FormulaError:
        return None


PERIOD_HEADER = re.compile(r"(?i)\b(year|period|month|quarter|yr|date)s?\b")


def period_series(values: list[object], header: object = None) -> tuple[str, str] | None:
    filled = [value for value in values if value not in (None, "")]
    if len(filled) < MIN_COPIES:
        return None
    if all(is_number(value) and float(value).is_integer() for value in filled):
        numbers = [int(value) for value in filled]
        consecutive = all(later == earlier + 1 for earlier, later in zip(numbers, numbers[1:]))
        years = all(1900 <= number <= 2100 for number in numbers)
        if consecutive and (years or PERIOD_HEADER.search(str(header or ""))):
            return str(numbers[0]), str(numbers[-1])
        return None
    texts = [str(value).strip() for value in filled]
    marked = [text for text in texts if PERIOD_TEXT.match(text) or ISO_DATE.match(text)]
    if len(marked) >= COPY_SHARE * len(texts):
        return marked[0][:10], marked[-1][:10]
    return None


def column_runs(cells: dict[tuple[int, int], str]) -> list[list[tuple[int, int]]]:
    by_column: dict[int, list[int]] = {}
    for row, column in cells:
        by_column.setdefault(column, []).append(row)
    runs = []
    for column, rows in by_column.items():
        run: list[tuple[int, int]] = []
        for row in sorted(rows):
            if run and run[-1][0] != row - 1:
                runs.append(run)
                run = []
            run.append((row, column))
        runs.append(run)
    return runs


def table_blocks(book: Workbook, sheet: str, cells: dict[tuple[int, int], str], taken: list[Block]) -> list[Block]:
    copied = []
    for run in column_runs(cells):
        refs = [cells[position] for position in run if not any(block.contains(cells[position]) for block in taken)]
        patterns = {ref: pattern_of(book, ref) for ref in refs}
        counted = Counter(pattern for pattern in patterns.values() if pattern is not None and not TOTAL_FORMULA.match(book.formula(next(r for r, p in patterns.items() if p == pattern)) or ""))
        if not counted:
            continue
        common, count = counted.most_common(1)[0]
        formulas = sum(1 for pattern in patterns.values() if pattern is not None)
        if count < MIN_TABLE_ROWS or count < COPY_SHARE * formulas:
            continue
        rows = [split_ref(ref)[1].row for ref, pattern in patterns.items() if pattern == common]
        copied.append((min(rows), max(rows), run[0][1]))
    groups: list[list[tuple[int, int, int]]] = []
    for top, bottom, column in sorted(copied, key=lambda item: (item[0], item[2])):
        group = next((g for g in groups if any(t <= bottom and top <= b and abs(c - column) <= 3 for t, b, c in g)), None)
        if group is None:
            groups.append([(top, bottom, column)])
        else:
            group.append((top, bottom, column))
    blocks = []
    for group in groups:
        top, bottom = min(t for t, _, _ in group), max(b for _, b, _ in group)
        columns = {column for (row, column) in cells if top <= row <= bottom}
        left, right = min(columns), max(columns)
        header = top - 1 if any(is_label_text(book.raw(cells[(top - 1, column)])) for column in range(left, right + 1) if (top - 1, column) in cells) else None
        totals = sorted(
            {cells[(row, column)] for (row, column) in cells if bottom < row <= bottom + TOTAL_GAP and left <= column <= right and TOTAL_FORMULA.match(book.formula(cells[(row, column)]) or "")},
            key=lambda ref: split_ref(ref)[1].column,
        )
        copied_columns = ", ".join(column_letters(c) for _, _, c in sorted(group, key=lambda item: item[2]))
        periods = next(
            (found for column in range(max(1, left - 3), right + 1)
             if (found := period_series(
                 [safe_value(book, cells[(row, column)]) if (row, column) in cells else None for row in range(top, bottom + 1)],
                 book.raw(cells[(top - 1, column)]) if (top - 1, column) in cells else None,
             ))),
            None,
        )
        if periods is not None:
            evidence = f"{bottom - top + 1} periods down the page, {periods[0]} to {periods[1]}, formulas copied down column{'s' if len(group) > 1 else ''} {copied_columns}"
            blocks.append(Block(sheet, "temporal", top, bottom, left, right, "down", header, evidence, totals=totals, periods=periods))
            continue
        evidence = f"{bottom - top + 1} rows, formulas copied down column{'s' if len(group) > 1 else ''} {copied_columns}"
        blocks.append(Block(sheet, "table", top, bottom, left, right, "down", header, evidence, totals=totals))
    return blocks


def inputs_block(book: Workbook, sheet: str, cells: dict[tuple[int, int], str], taken: list[Block]) -> Block | None:
    free = [ref for ref in cells.values() if not any(block.contains(ref) for block in taken)]
    typed = [ref for ref in free if is_number(book.raw(ref))]
    formulas = [ref for ref in free if book.formula(ref) is not None]
    if len(typed) < MIN_COPIES or len(typed) < INPUT_SHARE * (len(typed) + len(formulas)):
        return None
    read_elsewhere = [ref for ref in typed if any(split_ref(dependent)[0] != sheet for dependent in book.dependents(ref))]
    if not read_elsewhere:
        return None
    rows = [split_ref(ref)[1].row for ref in typed]
    columns = [split_ref(ref)[1].column for ref in typed]
    evidence = f"{len(typed)} typed values, {len(read_elsewhere)} read by other sheets"
    return Block(sheet, "inputs", min(rows), max(rows), min(columns), max(columns), None, None, evidence)


def summary_block(book: Workbook, sheet: str, cells: dict[tuple[int, int], str], taken: list[Block]) -> Block | None:
    if any(block.sheet == sheet for block in taken):
        return None
    formulas = [ref for ref in cells.values() if book.formula(ref) is not None]
    linked = [ref for ref in formulas if "!" in (book.formula(ref) or "")]
    if not formulas or len(linked) < SUMMARY_SHARE * len(formulas):
        return None
    rows = [split_ref(ref)[1].row for ref in formulas]
    columns = [split_ref(ref)[1].column for ref in formulas]
    return Block(sheet, "summary", min(rows), max(rows), min(columns), max(columns), None, None, f"{len(linked)} of {len(formulas)} formulas read other sheets")


def calculation_block(book: Workbook, sheet: str, cells: dict[tuple[int, int], str], taken: list[Block]) -> Block | None:
    if any(block.sheet == sheet for block in taken):
        return None
    formulas = [ref for ref in cells.values() if book.formula(ref) is not None]
    if len(formulas) < MIN_CALCULATIONS:
        return None
    rows = [split_ref(ref)[1].row for ref in formulas]
    columns = [split_ref(ref)[1].column for ref in formulas]
    return Block(sheet, "calculation", min(rows), max(rows), min(columns), max(columns), None, None, f"{len(formulas)} formulas, each line calculated once")


def data_block(book: Workbook, sheet: str, cells: dict[tuple[int, int], str], taken: list[Block]) -> Block | None:
    if any(block.sheet == sheet for block in taken):
        return None
    typed = [ref for ref in cells.values() if is_number(book.raw(ref))]
    formulas = [ref for ref in cells.values() if book.formula(ref) is not None]
    texts = sum(1 for ref in cells.values() if is_label_text(book.raw(ref)))
    if len(typed) < MIN_COPIES or len(typed) < DATA_SHARE * (len(typed) + len(formulas)) or len(typed) < texts:
        return None
    rows = [split_ref(ref)[1].row for ref in typed]
    columns = [split_ref(ref)[1].column for ref in typed]
    return Block(sheet, "data", min(rows), max(rows), min(columns), max(columns), None, None, f"{len(typed)} typed values, {len(formulas)} formulas")


def notes_block(book: Workbook, sheet: str, cells: dict[tuple[int, int], str], taken: list[Block]) -> Block | None:
    if any(block.sheet == sheet for block in taken) or not cells:
        return None
    rows = [row for row, _ in cells]
    columns = [column for _, column in cells]
    texts = sum(1 for ref in cells.values() if is_label_text(book.raw(ref)))
    return Block(sheet, "notes", min(rows), max(rows), min(columns), max(columns), None, None, f"{texts} text cells, no calculation")


def profile(book: Workbook) -> list[Block]:
    blocks: list[Block] = []
    for sheet in book.sheets:
        cells = sheet_cells(book, sheet)
        found = temporal_blocks(book, sheet, cells)
        found += table_blocks(book, sheet, cells, found)
        blocks += found
    for sheet in book.sheets:
        cells = sheet_cells(book, sheet)
        extra = (
            inputs_block(book, sheet, cells, blocks)
            or summary_block(book, sheet, cells, blocks)
            or data_block(book, sheet, cells, blocks)
            or calculation_block(book, sheet, cells, blocks)
            or notes_block(book, sheet, cells, blocks)
        )
        if extra is not None:
            blocks.append(extra)
    return blocks


def describe(blocks: list[Block]) -> str:
    kinds = {block.kind for block in blocks}
    if {"temporal", "table"} <= kinds:
        title = "Mixed model"
    elif "temporal" in kinds:
        title = "Time-series model"
    elif "table" in kinds:
        title = "Table model"
    elif "calculation" in kinds:
        title = "Calculation model"
    elif "summary" in kinds:
        title = "Summary workbook"
    elif "data" in kinds or "inputs" in kinds:
        title = "Data workbook"
    elif "notes" in kinds:
        title = "Text document"
    else:
        return "Empty workbook: no cells to check."
    parts = []
    temporal: dict[tuple[str, str], list[str]] = {}
    for block in blocks:
        if block.kind == "temporal" and block.periods:
            sheets = temporal.setdefault(block.periods, [])
            if block.sheet not in sheets and not any(block.sheet in names for names in temporal.values()):
                sheets.append(block.sheet)
    for (first, last), sheets in temporal.items():
        if sheets:
            parts.append(f"time series on {', '.join(sheets)} ({first} to {last})")
    tables: dict[str, list[Block]] = {}
    for block in blocks:
        if block.kind == "table":
            tables.setdefault(block.sheet, []).append(block)
    for sheet, found in tables.items():
        if len(found) == 1:
            totals = ", ".join(ref.split("!", 1)[1] for ref in found[0].totals)
            parts.append(f"table on {sheet} ({found[0].bottom - found[0].top + 1} rows, {'total in ' + totals if totals else 'no total'})")
        else:
            parts.append(f"{len(found)} tables on {sheet}")
    for kind, name in (("calculation", "calculation"), ("inputs", "assumptions"), ("summary", "summary"), ("data", "data"), ("notes", "notes")):
        sheets = [block.sheet for block in blocks if block.kind == kind]
        if sheets:
            parts.append(f"{name} on {', '.join(sheets)}")
    return f"{title}: " + "; ".join(parts) + "."

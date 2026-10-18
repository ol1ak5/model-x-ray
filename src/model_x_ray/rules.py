import re
from collections import Counter

from model_x_ray.spreadsheet.engine import CellAddress, FormulaError, Workbook, column_letters, expand_range, is_number, make_ref, normalize_ref, split_ref

PERIOD_LIKE = re.compile(r"\d")


def find_formula_outliers(book: Workbook, range_ref: str) -> list[dict[str, str]]:
    refs = [normalize_ref(ref) for ref in expand_range(range_ref) if book.raw(ref) is not None]
    return row_outliers(book, refs)


def is_period_cell(book: Workbook, ref: str) -> bool:
    header = book.column_header(ref)
    raw = book.raw(ref)
    return bool(header and (PERIOD_LIKE.search(header) or book.in_timeline(ref)) and book.row_label(ref)) and (is_number(raw) or book.formula(ref) is not None)


def scan_model(book: Workbook) -> list[dict[str, str]]:
    cells = [ref for ref in book.cells() if is_period_cell(book, ref) and PERIOD_LIKE.search(book.column_header(ref) or "")]
    found = []
    for outlier in row_outliers(book, cells):
        sheet, address = split_ref(outlier["cell"])
        if outlier["reason"].startswith("typed value"):
            left = [ref for ref in cells if split_ref(ref)[0] == sheet and split_ref(ref)[1].row == address.row and split_ref(ref)[1].column < address.column]
            if not any(book.formula(ref) is not None for ref in left):
                continue
        found.append(outlier)
    return found


def row_outliers(book: Workbook, refs: list[str]) -> list[dict[str, str]]:
    outliers: list[dict[str, str]] = []
    rows: dict[tuple[str, int], list[str]] = {}
    for ref in refs:
        sheet, address = split_ref(ref)
        rows.setdefault((sheet, address.row), []).append(ref)
    for row_refs in rows.values():
        patterned = {ref: book.formula_pattern(ref) for ref in row_refs}
        formulas = {ref: pattern for ref, pattern in patterned.items() if pattern is not None}
        typed = [ref for ref, pattern in patterned.items() if pattern is None]
        if not formulas:
            continue
        common, count = Counter(formulas.values()).most_common(1)[0]
        for ref in typed:
            outliers.append({"cell": ref, "reason": f"typed value where the row uses {common}"})
        if count >= 2:
            for ref, pattern in formulas.items():
                if pattern != common:
                    outliers.append({"cell": ref, "reason": f"reference pattern differs from the row: the row uses {common}"})
    outliers.sort(key=lambda o: (split_ref(o["cell"])[1].row, split_ref(o["cell"])[1].column))
    return outliers


TOTAL_FORMULA = re.compile(r"^=\s*SUM\(\s*(\$?[A-Za-z]{1,3}\$?\d+)(?::(\$?[A-Za-z]{1,3}\$?\d+))?\s*\)\s*$", re.IGNORECASE)
BLANK_ROWS_ABOVE_TOTAL = 2
MIN_COLUMN_RUN = 3


def safe_pattern(book: Workbook, ref: str) -> str | None:
    try:
        return book.formula_pattern(ref)
    except FormulaError:
        return f"unreadable {ref}"


def column_runs(book: Workbook) -> list[list[str]]:
    columns: dict[tuple[str, int], list[int]] = {}
    for ref in book.cells():
        sheet, address = split_ref(ref)
        columns.setdefault((sheet, address.column), []).append(address.row)
    runs = []
    for (sheet, column), rows in columns.items():
        run: list[str] = []
        for row in sorted(rows):
            ref = make_ref(sheet, CellAddress(column, row))
            if run and split_ref(run[-1])[1].row != row - 1:
                runs.append(run)
                run = []
            run.append(ref)
        runs.append(run)
    return runs


def column_findings(book: Workbook) -> list[dict[str, str]]:
    findings = []
    for run in column_runs(book):
        patterns = {ref: safe_pattern(book, ref) for ref in run}
        counted = Counter(pattern for pattern in patterns.values() if pattern is not None)
        if not counted:
            continue
        common, count = counted.most_common(1)[0]
        if count < MIN_COLUMN_RUN:
            continue
        for index, ref in enumerate(run):
            above = next((run[i] for i in range(index - 1, -1, -1) if patterns[run[i]] is not None), None)
            below = next((run[i] for i in range(index + 1, len(run)) if patterns[run[i]] is not None), None)
            if above is None or below is None or common not in (patterns[above], patterns[below]):
                continue
            pattern = patterns[ref]
            if pattern is not None and counted[pattern] > max(2, count // 4):
                continue
            source = above if patterns[above] == common else below
            if pattern is None and is_number(book.raw(ref)):
                findings.append({"cell": ref, "kind": "typed_in_column", "reason": f"typed value where the column uses {book.formula(source)}", "fix": book.shifted_formula(source, ref)})
            elif pattern is not None and pattern != common and not pattern.startswith("unreadable") and not TOTAL_FORMULA.match(book.formula(ref) or ""):
                findings.append({"cell": ref, "kind": "column_pattern", "reason": f"reference pattern differs from the column, which uses {book.formula(source)}", "fix": book.shifted_formula(source, ref)})
    return findings


def block_above(book: Workbook, ref: str) -> list[str]:
    sheet, address = split_ref(ref)
    row = address.row - 1
    while row > 0 and address.row - row <= BLANK_ROWS_ABOVE_TOTAL and book.raw(make_ref(sheet, CellAddress(address.column, row))) is None:
        row -= 1
    block = []
    while row > 0:
        cell = make_ref(sheet, CellAddress(address.column, row))
        content = book.raw(cell)
        if content is None or TOTAL_FORMULA.match(str(content)) or not (is_number(content) or book.formula(cell) is not None):
            break
        block.append(cell)
        row -= 1
    return list(reversed(block))


def total_findings(book: Workbook) -> list[dict[str, str]]:
    findings = []
    for ref in book.cells():
        match = TOTAL_FORMULA.match(book.formula(ref) or "")
        if match is None:
            continue
        sheet, address = split_ref(ref)
        first, last = (normalize_ref(f"{sheet}!{part.replace('$', '')}") for part in (match.group(1), match.group(2) or match.group(1)))
        covered = expand_range(f"{sheet}!{first.split('!')[1]}:{last.split('!')[1]}")
        if any(split_ref(cell)[1].column != address.column for cell in covered):
            continue
        block = block_above(book, ref)
        filled = [cell for cell in covered if book.raw(cell) is not None]
        if not filled or not set(filled) < set(block):
            continue
        missing = [cell for cell in block if cell not in covered]
        start = min(split_ref(block[0])[1].row, split_ref(covered[0])[1].row)
        end = max(split_ref(block[-1])[1].row, split_ref(covered[-1])[1].row)
        start, end = CellAddress(address.column, start), CellAddress(address.column, end)
        fix = f"=SUM({column_letters(start.column)}{start.row}:{column_letters(end.column)}{end.row})"
        findings.append({"cell": ref, "kind": "incomplete_total", "reason": f"the total sums {first.split('!')[1]}" + (f":{last.split('!')[1]}" if last != first else "") + f" and leaves out {', '.join(cell.split('!')[1] for cell in missing)} in the same block", "fix": fix})
    return findings


def scan_tables(book: Workbook) -> list[dict[str, str]]:
    found = {finding["cell"]: finding for finding in [*total_findings(book), *column_findings(book)]}
    return sorted(found.values(), key=lambda f: (split_ref(f["cell"])[0], split_ref(f["cell"])[1].row, split_ref(f["cell"])[1].column))

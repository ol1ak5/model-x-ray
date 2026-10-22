import re
from collections import Counter
from collections.abc import Callable
from weakref import WeakKeyDictionary

from model_x_ray.spreadsheet.engine import CellAddress, FormulaError, Workbook, column_letters, expand_range, is_number, make_ref, normalize_ref, split_ref
from model_x_ray.structure import profile

PERIOD_LIKE = re.compile(r"\d")


def find_formula_outliers(book: Workbook, range_ref: str) -> list[dict[str, str]]:
    refs = [normalize_ref(ref) for ref in expand_range(range_ref) if book.raw(ref) is not None]
    return row_outliers(book, refs)


def is_period_cell(book: Workbook, ref: str) -> bool:
    header = book.column_header(ref)
    raw = book.raw(ref)
    return bool(header and (PERIOD_LIKE.search(header) or book.in_timeline(ref)) and book.row_label(ref)) and (is_number(raw) or book.formula(ref) is not None)


def row_fix(book: Workbook, ref: str) -> str | None:
    sheet, address = split_ref(ref)
    neighbours = [cell for cell in book.cells() if split_ref(cell)[0] == sheet and split_ref(cell)[1].row == address.row and cell != ref and book.formula(cell) is not None]
    patterns = Counter(book.formula_pattern(cell) for cell in neighbours)
    if not patterns:
        return None
    common, _ = patterns.most_common(1)[0]
    source = min((cell for cell in neighbours if book.formula_pattern(cell) == common), key=lambda cell: abs(split_ref(cell)[1].column - address.column))
    return book.shifted_formula(source, ref)


def row_cells(book: Workbook, ref: str) -> list[str]:
    sheet, address = split_ref(ref)
    return [
        candidate
        for candidate in book.cells()
        if split_ref(candidate)[0] == sheet
        and split_ref(candidate)[1].row == address.row
        and is_period_cell(book, candidate)
    ]


def model_outliers(book: Workbook, cells: list[str]) -> list[dict[str, str]]:
    edges: dict[tuple[str, int], tuple[int, int]] = {}
    for ref in cells:
        sheet, address = split_ref(ref)
        low, high = edges.get((sheet, address.row), (address.column, address.column))
        edges[(sheet, address.row)] = (min(low, address.column), max(high, address.column))
    found = []
    for outlier in row_outliers(book, cells):
        sheet, address = split_ref(outlier["cell"])
        if outlier["reason"].startswith("reference pattern differs") and address.column in edges[(sheet, address.row)]:
            continue
        if outlier["reason"].startswith("typed value"):
            left = [ref for ref in cells if split_ref(ref)[0] == sheet and split_ref(ref)[1].row == address.row and split_ref(ref)[1].column < address.column]
            if not any(book.formula(ref) is not None for ref in left):
                continue
        found.append(outlier)
    return found


def breaks_row_pattern(book: Workbook, ref: str) -> bool:
    return normalize_ref(ref) in {outlier["cell"] for outlier in model_outliers(book, row_cells(book, ref))}


def isolated_break(book: Workbook, ref: str) -> bool:
    row = sorted(row_cells(book, ref), key=lambda cell: split_ref(cell)[1].column)
    if ref not in row:
        return False
    index = row.index(ref)
    if index == 0 or index + 1 == len(row):
        return False
    left, right = book.formula_pattern(row[index - 1]), book.formula_pattern(row[index + 1])
    return left is not None and left == right and book.formula_pattern(ref) != left


def rank_outliers(book: Workbook, outliers: list[dict[str, str]]) -> list[dict[str, str]]:
    return sorted(outliers, key=lambda o: (not isolated_break(book, o["cell"]), -len(book.all_dependents(o["cell"]))))


def scan_model(book: Workbook) -> list[dict[str, str]]:
    return model_outliers(book, [ref for ref in book.cells() if is_period_cell(book, ref) and PERIOD_LIKE.search(book.column_header(ref) or "")])


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
            if pattern is None and is_number(book.raw(ref)) and (index == 0 or patterns[run[index - 1]] is None or index == len(run) - 1 or patterns[run[index + 1]] is None):
                continue
            if pattern is None and is_number(book.raw(ref)):
                findings.append({"cell": ref, "kind": "typed_in_column", "reason": f"typed value where the column uses {book.formula(source)}", "fix": book.shifted_formula(source, ref)})
            elif pattern is not None and pattern != common and not pattern.startswith("unreadable") and not TOTAL_FORMULA.match(book.formula(ref) or ""):
                findings.append({"cell": ref, "kind": "column_pattern", "reason": f"reference pattern differs from the column, which uses {book.formula(source)}", "fix": book.shifted_formula(source, ref)})
    return findings


SUM_OF_CELLS = re.compile(r"^[A-Za-z]{1,3}\$?\d+(?:\s*[-+]\s*\$?[A-Za-z]{1,3}\$?\d+)+$")


def sums_cells_above(book: Workbook, ref: str) -> bool:
    formula = (book.formula(ref) or "").replace("=", "").replace(" ", "")
    if not SUM_OF_CELLS.match(formula):
        return False
    sheet, address = split_ref(ref)
    for part in re.findall(r"\$?[A-Za-z]{1,3}\$?\d+", formula):
        other_sheet, other = split_ref(normalize_ref(f"{sheet}!{part.replace('$', '')}"))
        if other_sheet != sheet or other.column != address.column or other.row >= address.row:
            return False
    return True


def block_above(book: Workbook, ref: str) -> list[str]:
    sheet, address = split_ref(ref)
    row = address.row - 1
    while row > 0 and address.row - row <= BLANK_ROWS_ABOVE_TOTAL and book.raw(make_ref(sheet, CellAddress(address.column, row))) is None:
        row -= 1
    block = []
    while row > 0:
        cell = make_ref(sheet, CellAddress(address.column, row))
        content = book.raw(cell)
        if content is None or TOTAL_FORMULA.match(str(content)) or sums_cells_above(book, cell) or not (is_number(content) or book.formula(cell) is not None):
            break
        block.append(cell)
        row -= 1
    return list(reversed(block))


def same_kind_tail(book: Workbook, block: list[str], typed: bool) -> list[str]:
    tail: list[str] = []
    for cell in reversed(block):
        if (book.formula(cell) is None) != typed:
            break
        tail.append(cell)
    return list(reversed(tail))


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
        filled = [cell for cell in covered if book.raw(cell) is not None]
        typed = {book.formula(cell) is None for cell in filled}
        block = same_kind_tail(book, block_above(book, ref), typed.pop()) if len(typed) == 1 else block_above(book, ref)
        if not filled or not set(filled) < set(block):
            continue
        missing = [cell for cell in block if cell not in covered]
        start = min(split_ref(block[0])[1].row, split_ref(covered[0])[1].row)
        end = max(split_ref(block[-1])[1].row, split_ref(covered[-1])[1].row)
        start, end = CellAddress(address.column, start), CellAddress(address.column, end)
        fix = f"=SUM({column_letters(start.column)}{start.row}:{column_letters(end.column)}{end.row})"
        findings.append({"cell": ref, "kind": "incomplete_total", "reason": f"the total sums {first.split('!')[1]}" + (f":{last.split('!')[1]}" if last != first else "") + f" and leaves out {', '.join(cell.split('!')[1] for cell in missing)} in the same block", "fix": fix})
    return findings


def section_above(book: Workbook, ref: str) -> list[str] | None:
    sheet, address = split_ref(ref)
    numbers = []
    for row in range(address.row - 1, 0, -1):
        cell = make_ref(sheet, CellAddress(address.column, row))
        content = book.raw(cell)
        if content is None:
            continue
        if not is_number(content):
            return list(reversed(numbers)) if book.formula(cell) is None or TOTAL_FORMULA.match(str(content)) else None
        numbers.append(cell)
    return None


def changes_value(book: Workbook, ref: str, fix: str) -> bool:
    try:
        before, after = book.value(ref), book.with_patch(ref, fix).value(ref)
    except FormulaError:
        return False
    return not (is_number(before) and is_number(after) and abs(after - before) <= 1e-9 * max(1.0, abs(before)))


def section_total_findings(book: Workbook) -> list[dict[str, str]]:
    findings = []
    for ref in book.cells():
        covered = total_range(book, ref)
        if not covered or "total" not in (book.row_label(ref) or "").lower():
            continue
        sheet, address = split_ref(ref)
        rows = [split_ref(cell)[1].row for cell in covered]
        if any(split_ref(cell)[1].column != address.column for cell in covered) or max(rows) >= address.row:
            continue
        section = section_above(book, ref)
        if not section or split_ref(section[0])[1].row > min(rows):
            continue
        missing = [cell for cell in section if cell not in covered]
        if not missing:
            continue
        start = min(split_ref(section[0])[1].row, min(rows))
        end = max(split_ref(section[-1])[1].row, max(rows))
        letters = column_letters(address.column)
        fix = f"=SUM({letters}{start}:{letters}{end})"
        if not changes_value(book, ref, fix):
            continue
        findings.append({"cell": ref, "kind": "incomplete_total", "reason": f"the subtotal sums {covered[0].split('!')[1]}" + (f":{covered[-1].split('!')[1]}" if len(covered) > 1 else "") + f" and leaves out {', '.join(cell.split('!')[1] for cell in missing)} in its section", "fix": fix})
    return findings


AGGREGATE_FORMULA = re.compile(r"^=\s*(SUM|AVERAGE|MIN|MAX|COUNT|COUNTA)\(\s*(\$?[A-Za-z]{1,3}\$?\d+)(?::(\$?[A-Za-z]{1,3}\$?\d+))?\s*\)\s*$", re.IGNORECASE)
MAX_GAP_BETWEEN_AGGREGATES = 2


def aggregate_shape(book: Workbook, ref: str) -> tuple[str, tuple[int, int], tuple[int, int]] | None:
    match = AGGREGATE_FORMULA.match(book.formula(ref) or "")
    if match is None:
        return None
    sheet, address = split_ref(ref)
    start = split_ref(f"{sheet}!{match.group(2).replace('$', '')}")[1]
    end = split_ref(f"{sheet}!{(match.group(3) or match.group(2)).replace('$', '')}")[1]
    return match.group(1).upper(), (start.row - address.row, end.row - address.row), (start.column - address.column, end.column - address.column)


def aggregate_peers(book: Workbook, ref: str, step: tuple[int, int]) -> list[str]:
    sheet, address = split_ref(ref)
    function = aggregate_shape(book, ref)[0]
    peers = []
    for direction in (1, -1):
        row, column, gap = address.row, address.column, 0
        while True:
            row, column = row + direction * step[0], column + direction * step[1]
            if row < 1 or column < 1 or gap > MAX_GAP_BETWEEN_AGGREGATES:
                break
            cell = make_ref(sheet, CellAddress(column, row))
            if book.raw(cell) is None:
                gap += 1
                continue
            shape = aggregate_shape(book, cell)
            if shape is None or shape[0] != function:
                break
            peers.append(cell)
            gap = 0
    return peers


def consensus(values: list) -> object | None:
    if len(values) < 2:
        return None
    value, count = Counter(values).most_common(1)[0]
    return value if count >= 2 and count * 2 > len(values) else None


def aggregate_finding(book: Workbook, ref: str, peers: list[str]) -> dict[str, str] | None:
    function, *own = aggregate_shape(book, ref)
    shapes = {peer: aggregate_shape(book, peer) for peer in peers}
    axes = []
    for axis in (0, 1):
        offsets = [shape[1 + axis] for shape in shapes.values()]
        agreed = consensus(offsets)
        span = consensus([last - first for first, last in offsets])
        axes.append((agreed, agreed is not None and agreed != own[axis] and own[axis] not in offsets, agreed == own[axis] or (agreed is None and span == own[axis][1] - own[axis][0])))
    differing = [axis for axis, (_, differs, _) in enumerate(axes) if differs]
    if len(differing) != 1 or not axes[1 - differing[0]][2]:
        return None
    axis = differing[0]
    rows, columns = (axes[0][0], own[1]) if axis == 0 else (own[0], axes[1][0])
    sheet, address = split_ref(ref)
    first, last = CellAddress(address.column + columns[0], address.row + rows[0]), CellAddress(address.column + columns[1], address.row + rows[1])
    if min(first.row, first.column, last.row, last.column) < 1:
        return None
    span = f"{column_letters(first.column)}{first.row}" + (f":{column_letters(last.column)}{last.row}" if last != first else "")
    witnesses = sorted((peer for peer, shape in shapes.items() if shape[1 + axis] == axes[axis][0]), key=lambda peer: abs(split_ref(peer)[1].row - address.row) + abs(split_ref(peer)[1].column - address.column))[:2]
    fix = f"={function}({span})"
    if not changes_value(book, ref, fix):
        return None
    beside = ", ".join(f"{peer.split('!')[1]} {book.formula(peer)}" for peer in witnesses)
    return {"cell": ref, "kind": "aggregate_range", "reason": f"{book.formula(ref)} covers a different range than the {function} formulas beside it ({beside})", "fix": fix}


def aggregate_findings(book: Workbook) -> list[dict[str, str]]:
    findings = []
    for ref in book.cells():
        if aggregate_shape(book, ref) is None:
            continue
        for step in ((0, 1), (1, 0)):
            finding = aggregate_finding(book, ref, aggregate_peers(book, ref, step))
            if finding is not None:
                findings.append(finding)
                break
    return findings


def total_range(book: Workbook, ref: str) -> list[str] | None:
    match = TOTAL_FORMULA.match(book.formula(ref) or "")
    if match is None:
        return None
    sheet = split_ref(ref)[0]
    first, last = match.group(1).replace("$", ""), (match.group(2) or match.group(1)).replace("$", "")
    return [normalize_ref(cell) for cell in expand_range(f"{sheet}!{first}:{last}")]


def double_count_findings(book: Workbook) -> list[dict[str, str]]:
    findings = []
    for ref in book.cells():
        covered = total_range(book, ref)
        if not covered:
            continue
        inside = set(covered)
        for subtotal in covered:
            parts = total_range(book, subtotal)
            if parts and set(parts) <= inside:
                kept = [cell for cell in covered if cell != subtotal and not (total_range(book, cell) or [])]
                findings.append({"cell": ref, "kind": "double_count", "reason": f"the total adds the subtotal {subtotal.split('!')[1]} and also its parts {parts[0].split('!')[1]}:{parts[-1].split('!')[1]}", "fix": "=" + "+".join(cell.split("!")[1] for cell in kept) if 0 < len(kept) <= 12 else None})
                break
    return findings


RECORD_BLOCKS: WeakKeyDictionary[Workbook, list] = WeakKeyDictionary()


def runs_down_like_records(book: Workbook) -> Callable[[str], bool]:
    if book not in RECORD_BLOCKS:
        RECORD_BLOCKS[book] = [block for block in profile(book) if block.kind == "table" or (block.kind == "temporal" and block.axis == "down")]
    blocks = RECORD_BLOCKS[book]
    return lambda ref: any(block.contains(ref) for block in blocks)


def scan_tables(book: Workbook, layout: Workbook | None = None) -> list[dict[str, str]]:
    like_records = runs_down_like_records(layout or book)
    columns = [finding for finding in column_findings(book) if like_records(finding["cell"])]
    findings = [*section_total_findings(book), *total_findings(book), *double_count_findings(book), *columns, *aggregate_findings(book)]
    found = {finding["cell"]: finding for finding in findings if not finding.get("fix") or changes_value(book, finding["cell"], finding["fix"])}
    return sorted(found.values(), key=lambda f: (split_ref(f["cell"])[0], split_ref(f["cell"])[1].row, split_ref(f["cell"])[1].column))


INPUT_OUTLIER_FACTOR = 5
MIN_INPUTS_IN_LINE = 4


def input_outliers(book: Workbook) -> list[dict]:
    lines: dict[tuple[str, int], list[str]] = {}
    for ref in book.cells():
        if book.formula(ref) is None and is_number(book.raw(ref)) and is_period_cell(book, ref):
            sheet, address = split_ref(ref)
            lines.setdefault((sheet, address.row), []).append(ref)
    found = []
    for cells in lines.values():
        if len(cells) < MIN_INPUTS_IN_LINE:
            continue
        for ref in cells:
            value = float(book.raw(ref))
            others = sorted(abs(float(book.raw(cell))) for cell in cells if cell != ref)
            typical = others[len(others) // 2]
            if typical > 0 and value != 0 and (abs(value) >= INPUT_OUTLIER_FACTOR * typical or abs(value) * INPUT_OUTLIER_FACTOR <= typical):
                found.append({"cell": ref, "value": value, "typical": typical})
    return found

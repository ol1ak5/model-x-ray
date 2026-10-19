import re
from collections import Counter

from model_x_ray.spreadsheet.engine import Workbook, expand_range, is_number, normalize_ref, split_ref

PERIOD_LIKE = re.compile(r"\d")


def find_formula_outliers(book: Workbook, range_ref: str) -> list[dict[str, str]]:
    refs = [normalize_ref(ref) for ref in expand_range(range_ref) if book.raw(ref) is not None]
    return row_outliers(book, refs)


def is_period_cell(book: Workbook, ref: str) -> bool:
    header = book.column_header(ref)
    raw = book.raw(ref)
    return bool(header and (PERIOD_LIKE.search(header) or book.in_timeline(ref)) and book.row_label(ref)) and (is_number(raw) or book.formula(ref) is not None)


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
    found = []
    for outlier in row_outliers(book, cells):
        sheet, address = split_ref(outlier["cell"])
        if outlier["reason"].startswith("typed value"):
            left = [ref for ref in cells if split_ref(ref)[0] == sheet and split_ref(ref)[1].row == address.row and split_ref(ref)[1].column < address.column]
            if not any(book.formula(ref) is not None for ref in left):
                continue
        found.append(outlier)
    return found


def breaks_row_pattern(book: Workbook, ref: str) -> bool:
    return normalize_ref(ref) in {outlier["cell"] for outlier in model_outliers(book, row_cells(book, ref))}


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

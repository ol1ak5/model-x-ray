from collections import Counter

from model_x_ray.spreadsheet.engine import Workbook, expand_range, normalize_ref, split_ref


def find_formula_outliers(book: Workbook, range_ref: str) -> list[dict[str, str]]:
    outliers: list[dict[str, str]] = []
    refs = [normalize_ref(ref) for ref in expand_range(range_ref) if book.raw(ref) is not None]
    rows: dict[int, list[str]] = {}
    for ref in refs:
        _, address = split_ref(ref)
        rows.setdefault(address.row, []).append(ref)
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

from model_x_ray.rules import find_formula_outliers
from model_x_ray.spreadsheet.engine import CellAddress, Workbook, column_letters, make_ref, normalize_ref, split_ref
from model_x_ray.state import CausalNode, Contribution


def _grid(book: Workbook, sheet: str, from_period: str, to_period: str) -> tuple[int, int] | None:
    from_columns = set()
    to_columns = set()
    for ref in book.cells():
        if not ref.startswith(f"{sheet}!"):
            continue
        header = book.column_header(ref)
        if header is None:
            continue
        if from_period in header:
            from_columns.add(split_ref(ref)[1].column)
        if to_period in header:
            to_columns.add(split_ref(ref)[1].column)
    if not from_columns or not to_columns:
        return None
    return min(from_columns), min(to_columns)


def _from_ref(book: Workbook, ref: str, from_period: str, to_period: str) -> str | None:
    sheet, address = split_ref(ref)
    grid = _grid(book, sheet, from_period, to_period)
    if grid is None:
        return None
    header = book.column_header(ref)
    if header is None or (from_period not in header and to_period not in header):
        return None
    shifted = make_ref(sheet, CellAddress(address.column - (grid[1] - grid[0]), address.row))
    if book.raw(shifted) is None:
        return None
    return shifted


def _suspicious(book: Workbook, ref: str, from_period: str, to_period: str) -> bool:
    sheet, address = split_ref(ref)
    grid = _grid(book, sheet, from_period, to_period)
    if grid is None:
        return False
    low, high = sorted(grid)
    row_range = f"{sheet}!{column_letters(low)}{address.row}:{column_letters(high)}{address.row}"
    return ref in {o["cell"] for o in find_formula_outliers(book, row_range)}


def _node(book: Workbook, ref: str, from_period: str, to_period: str, root_delta: float) -> CausalNode | None:
    from_ref = _from_ref(book, ref, from_period, to_period)
    if from_ref is None:
        return None
    value_before = book.value(from_ref)
    value_after = book.value(ref)
    if value_before is None or value_after is None:
        return None
    delta = value_after - value_before
    children = []
    for precedent in book.precedents(ref):
        child = _node(book, precedent, from_period, to_period, root_delta)
        if child is not None:
            children.append(child)
    return {
        "cell": ref,
        "label": book.row_label(ref) or "",
        "value_before": value_before,
        "value_after": value_after,
        "delta": delta,
        "share_of_change": delta / root_delta if root_delta else 0.0,
        "suspicious": _suspicious(book, ref, from_period, to_period),
        "children": children,
    }


def explain_change(book: Workbook, ref: str, from_period: str, to_period: str) -> dict:
    ref = normalize_ref(ref)
    from_ref = _from_ref(book, ref, from_period, to_period)
    if from_ref is None:
        raise ValueError(f"No period columns {from_period} -> {to_period} for {ref}")
    value_before = book.value(from_ref)
    value_after = book.value(ref)
    if value_before is None or value_after is None:
        raise ValueError(f"Missing values for {ref}")
    inputs = book.precedents(ref)
    shifts = {input_ref: _from_ref(book, input_ref, from_period, to_period) for input_ref in inputs}
    patched = book
    for input_ref, shift in shifts.items():
        if shift is not None:
            shifted_value = book.value(shift)
            if shifted_value is not None:
                patched = patched.with_patch(input_ref, shifted_value)
    baseline = patched.value(ref)
    if baseline is None:
        raise ValueError(f"Could not recompute {ref} with prior-period inputs")
    contributions: list[Contribution] = []
    for input_ref, shift in shifts.items():
        input_value = book.value(input_ref)
        if shift is None or input_value is None:
            continue
        restored = patched.with_patch(input_ref, input_value)
        contribution = restored.value(ref) - baseline
        if abs(contribution) < 1e-9:
            continue
        contributions.append({"cell": input_ref, "label": book.row_label(input_ref) or "", "delta": contribution})
    return {
        "cell": ref,
        "value_before": value_before,
        "value_after": value_after,
        "delta": value_after - value_before,
        "contributions": contributions,
    }


def build_causal_tree(book: Workbook, ref: str, from_period: str, to_period: str) -> CausalNode:
    ref = normalize_ref(ref)
    from_ref = _from_ref(book, ref, from_period, to_period)
    if from_ref is None:
        raise ValueError(f"No period columns {from_period} -> {to_period} for {ref}")
    value_before = book.value(from_ref)
    value_after = book.value(ref)
    if value_before is None or value_after is None:
        raise ValueError(f"Missing values for {ref}")
    root_delta = value_after - value_before
    tree = _node(book, ref, from_period, to_period, root_delta)
    if tree is None:
        raise ValueError(f"Could not build causal tree for {ref}")
    return tree

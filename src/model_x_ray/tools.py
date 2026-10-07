from collections import Counter

from langchain_core.tools import BaseTool, tool

from model_x_ray.spreadsheet.engine import CellMetadata, Workbook, expand_range, normalize_ref, split_ref


def find_cells(book: Workbook, label: str, period: str) -> list[str]:
    matches = []
    for ref in book.cells():
        row = book.row_label(ref)
        column = book.column_header(ref)
        if row is None or column is None:
            continue
        if row == label and period in column:
            matches.append(ref)
    if matches:
        return matches
    for ref in book.cells():
        row = book.row_label(ref)
        column = book.column_header(ref)
        if row is None or column is None:
            continue
        if label in row and period in column:
            matches.append(ref)
    return matches


def get_cell(book: Workbook, ref: str) -> str:
    ref = normalize_ref(ref)
    label = book.row_label(ref) or ""
    header = book.column_header(ref) or ""
    value = book.value(ref)
    formula = book.formula(ref)
    head = f"{ref} {label} {header}".strip()
    if formula is not None:
        return f"{head} = {value}, formula {formula}"
    note = book.note(ref)
    note_text = f", note: {note}" if note is not None else ", no note"
    kind = "typed value" if isinstance(value, (int, float)) else "typed text"
    return f"{head} = {value}, {kind}, no formula{note_text}"


def trace_precedents(book: Workbook, ref: str, depth: int = 1) -> str:
    lines = []
    seen = {normalize_ref(ref)}
    frontier = [normalize_ref(ref)]
    for _ in range(depth):
        following = []
        for cell in frontier:
            precedents = book.precedents(cell)
            if precedents:
                lines.append(f"{cell} depends on {', '.join(precedents)}")
                following += [p for p in precedents if p not in seen]
            elif book.formula(cell) is not None:
                lines.append(f"{cell} has no precedents: its formula reads no other cells")
            else:
                lines.append(f"{cell} has no precedents: it is a typed value ({book.value(cell)})")
        seen.update(following)
        frontier = following
        if not frontier:
            break
    return "\n".join(lines)


def trace_dependents(book: Workbook, ref: str, depth: int = 1) -> str:
    lines = []
    seen = {normalize_ref(ref)}
    frontier = [normalize_ref(ref)]
    for _ in range(depth):
        following = []
        for cell in frontier:
            dependents = book.dependents(cell)
            if dependents:
                lines.append(f"{cell} is read by {', '.join(dependents)}")
                following += [d for d in dependents if d not in seen]
            else:
                lines.append(f"nothing reads {cell}")
        seen.update(following)
        frontier = following
        if not frontier:
            break
    return "\n".join(lines)


def compare_formulas(book: Workbook, ref: str, reference_cells: list[str]) -> str:
    ref = normalize_ref(ref)
    own_pattern = book.formula_pattern(ref)
    if own_pattern is None:
        head = f"{ref} is a typed value ({book.value(ref)}) with no formula"
    else:
        head = f"{ref} uses {book.formula(ref)}, pattern {own_pattern}"
    parts = [head]
    neighbour_patterns = []
    for neighbour in reference_cells:
        neighbour = normalize_ref(neighbour)
        pattern = book.formula_pattern(neighbour)
        if pattern is None:
            parts.append(f"neighbour {neighbour} is a typed value ({book.value(neighbour)})")
        else:
            neighbour_patterns.append(pattern)
            parts.append(f"neighbour {neighbour} uses pattern {pattern}")
    common = Counter(neighbour_patterns).most_common(1)[0][0] if neighbour_patterns else None
    if own_pattern is None:
        parts.append(f"{ref} breaks the pattern; the row uses {common}" if common else f"{ref} breaks the pattern")
    elif common is None:
        parts.append(f"{ref} has no formula neighbours to compare against")
    elif own_pattern == common:
        parts.append(f"{ref} matches the row pattern")
    else:
        parts.append(f"{ref} breaks the pattern; the row uses {common}")
    return "; ".join(parts)


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


def get_cell_metadata(book: Workbook, ref: str) -> CellMetadata:
    return book.metadata_of(ref)


def make_read_only_tools(book: Workbook) -> list[BaseTool]:
    @tool("find_cells")
    def find_cells_for(label: str, period: str) -> str:
        """Find the cells of a row label in a period, for example label='Opex', period='2027'. Returns comma-separated cell references."""
        return ", ".join(find_cells(book, label, period))

    @tool("get_cell")
    def get_cell_for(ref: str) -> str:
        """Read one cell: its value, formula, row label, period header and note, for example ref='P&L!H8'."""
        return get_cell(book, ref)

    @tool("trace_precedents")
    def trace_precedents_for(ref: str, depth: int = 1) -> str:
        """List the cells a formula reads, for example ref='P&L!H8', depth=1 for direct inputs only."""
        return trace_precedents(book, ref, depth)

    @tool("trace_dependents")
    def trace_dependents_for(ref: str, depth: int = 1) -> str:
        """List the cells that read this cell, for example ref='P&L!H7', depth=1 for direct readers only."""
        return trace_dependents(book, ref, depth)

    @tool("compare_formulas")
    def compare_formulas_for(ref: str, reference_cells: list[str]) -> str:
        """Compare a cell's formula structure with neighbouring cells, normalized relative to each cell, and say whether it deviates, for example ref='P&L!H7', reference_cells=['P&L!G7']."""
        return compare_formulas(book, ref, reference_cells)

    @tool("find_formula_outliers")
    def find_formula_outliers_for(range: str) -> str:
        """Scan a range such as 'P&L!G4:H9' and report every cell that breaks its row pattern or is a typed value where the row uses formulas. Returns lines of 'cell: reason'."""
        outliers = find_formula_outliers(book, range)
        return "\n".join(f"{o['cell']}: {o['reason']}" for o in outliers) if outliers else "no outliers found"

    @tool("get_cell_metadata")
    def get_cell_metadata_for(ref: str) -> str:
        """Read the cell's note, font colour and number format, for example ref='P&L!H7'. Blue font marks typed inputs; notes give the business context."""
        meta = get_cell_metadata(book, ref)
        parts = [f"note: {meta['note']}" if meta["note"] else "no note"]
        if meta["font_color"]:
            parts.append(f"font colour: {meta['font_color']}")
        if meta["number_format"] and meta["number_format"] != "General":
            parts.append(f"number format: {meta['number_format']}")
        return f"{ref}: " + "; ".join(parts)

    return [
        find_cells_for,
        get_cell_for,
        trace_precedents_for,
        trace_dependents_for,
        compare_formulas_for,
        find_formula_outliers_for,
        get_cell_metadata_for,
    ]

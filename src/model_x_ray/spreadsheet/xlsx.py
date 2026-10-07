from datetime import date, datetime
from pathlib import Path

from openpyxl import load_workbook

from model_x_ray.spreadsheet.engine import CellContent, CellMetadata, Workbook


def to_content(value: object) -> CellContent | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


def font_color(cell: object) -> str | None:
    color = getattr(cell, "font", None)
    color = getattr(color, "color", None)
    if color is None or getattr(color, "type", None) != "rgb":
        return None
    return str(color.rgb)


def load_xlsx(path: Path) -> Workbook:
    source = load_workbook(path, data_only=False)
    cells: dict[str, CellContent] = {}
    notes: dict[str, str] = {}
    metadata: dict[str, CellMetadata] = {}
    for sheet in source.worksheets:
        for row in sheet.iter_rows():
            for cell in row:
                ref = f"{sheet.title}!{cell.coordinate}"
                content = to_content(cell.value)
                if content is not None and content != "":
                    cells[ref] = content
                note = cell.comment.text.strip() if cell.comment is not None else None
                if note is not None:
                    notes[ref] = note
                color = font_color(cell)
                number_format = cell.number_format
                if color is not None or number_format != "General":
                    metadata[ref] = {"note": note, "font_color": color, "number_format": number_format}
    return Workbook(cells, notes, source.sheetnames, metadata)

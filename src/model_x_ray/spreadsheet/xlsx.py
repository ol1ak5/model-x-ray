from datetime import date, datetime
from pathlib import Path

from openpyxl import load_workbook

from model_x_ray.spreadsheet.engine import CellContent, Workbook


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


def load_xlsx(path: Path) -> Workbook:
    source = load_workbook(path, data_only=False)
    cells: dict[str, CellContent] = {}
    notes: dict[str, str] = {}
    for sheet in source.worksheets:
        for row in sheet.iter_rows():
            for cell in row:
                ref = f"{sheet.title}!{cell.coordinate}"
                content = to_content(cell.value)
                if content is not None and content != "":
                    cells[ref] = content
                if cell.comment is not None:
                    notes[ref] = cell.comment.text.strip()
    return Workbook(cells, notes, source.sheetnames)

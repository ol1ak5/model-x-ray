from pathlib import Path
from typing import Protocol

from model_x_ray.spreadsheet.engine import CellContent, Workbook, expand_range
from model_x_ray.spreadsheet.xlsx import load_xlsx


class SpreadsheetSource(Protocol):
    def load(self, spreadsheet_id: str) -> Workbook: ...

    def list_sheets(self, spreadsheet_id: str) -> list[str]: ...

    def read_range(self, spreadsheet_id: str, range_ref: str) -> dict[str, CellContent]: ...

    def row_label(self, spreadsheet_id: str, ref: str) -> str | None: ...

    def column_header(self, spreadsheet_id: str, ref: str) -> str | None: ...


class XlsxSource:
    def __init__(self, files: dict[str, Path]) -> None:
        self._files = files
        self._cache: dict[str, Workbook] = {}

    def load(self, spreadsheet_id: str) -> Workbook:
        if spreadsheet_id not in self._cache:
            self._cache[spreadsheet_id] = load_xlsx(self._files[spreadsheet_id])
        return self._cache[spreadsheet_id]

    def list_sheets(self, spreadsheet_id: str) -> list[str]:
        return self.load(spreadsheet_id).sheets

    def read_range(self, spreadsheet_id: str, range_ref: str) -> dict[str, CellContent]:
        book = self.load(spreadsheet_id)
        contents: dict[str, CellContent] = {}
        for ref in expand_range(range_ref):
            content = book.raw(ref)
            if content is not None:
                contents[ref] = content
        return contents

    def row_label(self, spreadsheet_id: str, ref: str) -> str | None:
        return self.load(spreadsheet_id).row_label(ref)

    def column_header(self, spreadsheet_id: str, ref: str) -> str | None:
        return self.load(spreadsheet_id).column_header(ref)

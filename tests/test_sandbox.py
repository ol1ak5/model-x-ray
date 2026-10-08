from collections.abc import Callable
from pathlib import Path

import pytest

from model_x_ray.spreadsheet.sandbox import (
    CHANGE_LOG_SHEET,
    FOLDER_MIME,
    GoogleSandbox,
    build_google_services,
    run_sandbox_test,
)
from model_x_ray.spreadsheet.source import XlsxSource
from model_x_ray.state import Patch

PATCH: Patch = {
    "cell": "P&L!H7",
    "old_formula": "-45.2",
    "new_formula": "=G7*(1+Assumptions!$C$7)",
    "source": "agent",
}


class Executable:
    def __init__(self, run: Callable[[], dict]) -> None:
        self._run = run

    def execute(self) -> dict:
        return self._run()


class FakeGoogle:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.data: dict[str, dict[str, object]] = {}
        self.made: list[str] = []
        self._ids = 0

    def files(self) -> "FakeFiles":
        return FakeFiles(self)

    def spreadsheets(self) -> "FakeSpreadsheets":
        return FakeSpreadsheets(self)

    def next_id(self, prefix: str) -> str:
        self._ids += 1
        made = f"{prefix}-{self._ids}"
        self.made.append(made)
        return made


class FakeFiles:
    def __init__(self, service: FakeGoogle) -> None:
        self._service = service

    def create(self, body: dict) -> Executable:
        def run() -> dict:
            self._service.calls.append(("files.create", {"body": body}))
            prefix = "folder" if body.get("mimeType") == FOLDER_MIME else "file"
            file_id = self._service.next_id(prefix)
            self._service.data.setdefault(file_id, {})
            return {"id": file_id}

        return Executable(run)

    def copy(self, fileId: str, body: dict) -> Executable:
        def run() -> dict:
            self._service.calls.append(("files.copy", {"fileId": fileId, "body": body}))
            copy_id = self._service.next_id("copy")
            self._service.data[copy_id] = dict(self._service.data.get(fileId, {}))
            return {"id": copy_id}

        return Executable(run)

    def delete(self, fileId: str) -> Executable:
        def run() -> dict:
            self._service.calls.append(("files.delete", {"fileId": fileId}))
            self._service.data.pop(fileId, None)
            return {}

        return Executable(run)


class FakeValues:
    def __init__(self, service: FakeGoogle) -> None:
        self._service = service

    def update(self, spreadsheetId: str, range: str, valueInputOption: str, body: dict) -> Executable:
        def run() -> dict:
            self._service.calls.append(("values.update", {
                "spreadsheetId": spreadsheetId, "range": range, "valueInputOption": valueInputOption, "body": body,
            }))
            self._service.data.setdefault(spreadsheetId, {})[range] = body["values"][0][0]
            return {"updatedCells": 1}

        return Executable(run)

    def batchGet(self, spreadsheetId: str, ranges: list[str], valueRenderOption: str) -> Executable:
        def run() -> dict:
            self._service.calls.append(("values.batchGet", {
                "spreadsheetId": spreadsheetId, "ranges": ranges, "valueRenderOption": valueRenderOption,
            }))
            stored = self._service.data.get(spreadsheetId, {})
            value_ranges = [
                {"range": ref, "values": [[stored[ref]]]} if ref in stored else {"range": ref}
                for ref in ranges
            ]
            return {"valueRanges": value_ranges}

        return Executable(run)


class FakeSpreadsheets:
    def __init__(self, service: FakeGoogle) -> None:
        self._service = service

    def values(self) -> FakeValues:
        return FakeValues(self._service)

    def batchUpdate(self, spreadsheetId: str, body: dict) -> Executable:
        def run() -> dict:
            self._service.calls.append(("spreadsheets.batchUpdate", {"spreadsheetId": spreadsheetId, "body": body}))
            replies = [
                {"addSheet": {"properties": {"sheetId": 99, "title": request["addSheet"]["properties"]["title"]}}}
                for request in body.get("requests", [])
                if "addSheet" in request
            ]
            return {"replies": replies}

        return Executable(run)


def test_sandbox_test_returns_before_and_after_for_the_target_and_every_dependent(demo_workbook_path: Path, engine_sandbox) -> None:
    source = XlsxSource({"demo": demo_workbook_path})

    result = run_sandbox_test(source, engine_sandbox, "demo", PATCH)

    assert list(result["before"]) == ["P&L!H7", "P&L!H8", "P&L!H9"]
    assert result["before"]["P&L!H7"] == -45.2
    assert result["before"]["P&L!H8"] == pytest.approx(52.01, abs=0.01)
    assert result["after"]["P&L!H7"] == pytest.approx(-52.48, abs=0.01)
    assert result["after"]["P&L!H8"] == pytest.approx(44.73, abs=0.01)
    assert result["before"]["P&L!H9"] == pytest.approx(0.299, abs=0.01)
    assert result["after"]["P&L!H9"] == pytest.approx(0.117, abs=0.01)
    assert engine_sandbox.discarded == engine_sandbox.created
    assert source.load("demo").value("P&L!H8") == pytest.approx(52.01, abs=0.01)


def test_google_sandbox_drives_the_drive_and_sheets_apis() -> None:
    service = FakeGoogle()
    service.data["sheet-1"] = {"'P&L'!H8": 52.0, "'P&L'!H9": 0.3}
    sandbox = GoogleSandbox(service, service)

    copy_id = sandbox.create_copy("sheet-1")
    sandbox.apply_patch(copy_id, PATCH)
    values = sandbox.read_values(copy_id, ["P&L!H8", "P&L!H9"])
    sandbox.discard(copy_id)

    names = [name for name, _ in service.calls]
    assert names[0] == "files.create"
    assert service.calls[0][1]["body"]["mimeType"] == FOLDER_MIME
    copy_call = service.calls[1]
    assert names[1] == "files.copy"
    assert copy_id == service.made[1]
    assert copy_call[1]["fileId"] == "sheet-1"
    assert copy_call[1]["body"]["parents"] == [service.made[0]]

    update = service.calls[2]
    assert names[2] == "values.update"
    assert update[1]["spreadsheetId"] == copy_id
    assert update[1]["range"] == "'P&L'!H7"
    assert update[1]["valueInputOption"] == "USER_ENTERED"
    assert update[1]["body"] == {"values": [["=G7*(1+Assumptions!$C$7)"]]}

    batch = service.calls[3]
    assert names[3] == "values.batchGet"
    assert batch[1]["spreadsheetId"] == copy_id
    assert batch[1]["ranges"] == ["'P&L'!H8", "'P&L'!H9"]
    assert batch[1]["valueRenderOption"] == "UNFORMATTED_VALUE"
    assert values == {"P&L!H8": 52.0, "P&L!H9": 0.3}

    assert names[4] == "files.delete"
    assert service.calls[4][1]["fileId"] == copy_id
    assert copy_id not in service.data


def test_write_corrected_copy_adds_a_change_log_tab() -> None:
    service = FakeGoogle()
    service.data["sheet-1"] = {"'P&L'!H8": 52.0}
    sandbox = GoogleSandbox(service, service, folder_id="folder-1")
    log_rows = [
        ["Timestamp", "Cell", "Old formula", "New formula", "Reason"],
        ["2026-10-08T12:00:00+00:00", "P&L!H7", "-45.2", "=G7*(1+Assumptions!$C$7)", "typed value"],
    ]

    copy_id = sandbox.write_corrected_copy("sheet-1", PATCH, log_rows)

    names = [name for name, _ in service.calls]
    assert names == ["files.copy", "values.update", "spreadsheets.batchUpdate", "values.update"]
    assert service.calls[0][1]["body"]["parents"] == ["folder-1"]
    patch_update = service.calls[1][1]
    assert patch_update["range"] == "'P&L'!H7"
    assert patch_update["valueInputOption"] == "USER_ENTERED"
    assert service.calls[2][1]["body"] == {"requests": [{"addSheet": {"properties": {"title": CHANGE_LOG_SHEET}}}]}
    log_update = service.calls[3][1]
    assert log_update["range"] == "'Change log'!A1"
    assert log_update["body"] == {"values": log_rows}
    assert "files.delete" not in names
    assert copy_id in service.data
    assert service.data[copy_id]["'P&L'!H8"] == 52.0


@pytest.mark.live
def test_google_sandbox_roundtrip_on_a_real_sheet() -> None:
    sheets, drive = build_google_services()
    sandbox = GoogleSandbox(sheets, drive)
    created = drive.files().create(
        body={"name": "model-x-ray sandbox live test", "mimeType": "application/vnd.google-apps.spreadsheet"},
    ).execute()
    spreadsheet_id = created["id"]
    try:
        sheets.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id, range="Sheet1!A1:A2", valueInputOption="USER_ENTERED",
            body={"values": [[2], [10]]},
        ).execute()
        sheets.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id, range="Sheet1!A3", valueInputOption="USER_ENTERED",
            body={"values": [["=A1+A2"]]},
        ).execute()

        copy_id = sandbox.create_copy(spreadsheet_id)
        try:
            assert sandbox.read_values(copy_id, ["Sheet1!A3"])["Sheet1!A3"] == 12
            sandbox.apply_patch(copy_id, {"cell": "Sheet1!A2", "old_formula": "10", "new_formula": "30", "source": "agent"})
            assert sandbox.read_values(copy_id, ["Sheet1!A3"])["Sheet1!A3"] == 32
        finally:
            sandbox.discard(copy_id)

        corrected = sandbox.write_corrected_copy(
            spreadsheet_id,
            {"cell": "Sheet1!A2", "old_formula": "10", "new_formula": "30", "source": "agent"},
            [["Timestamp", "Cell", "Old formula", "New formula", "Reason"], ["live", "Sheet1!A2", "10", "30", "roundtrip"]],
        )
        try:
            assert sandbox.read_values(corrected, ["Sheet1!A3"])["Sheet1!A3"] == 32
        finally:
            drive.files().delete(fileId=corrected).execute()
    finally:
        drive.files().delete(fileId=spreadsheet_id).execute()

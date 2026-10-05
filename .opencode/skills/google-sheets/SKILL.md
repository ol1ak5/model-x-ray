---
name: google-sheets
description: Google Sheets and Drive APIs for the SpreadsheetSource reader and the copy-patch-recalculate sandbox — render options, quota traps, and service-account setup
---

# Google Sheets API

Two integrations, deliberately separate (design: `docs/agent-architecture.md` §Platform):

1. **Reading** a model (values, formulas, labels, metadata) → Sheets API
2. **Sandbox** (copy → patch → read recalculated values) → Drive `files.copy` + Sheets `values.update`

Credentials: service account JSON **outside the repo**, path in `.env` as `GOOGLE_APPLICATION_CREDENTIALS` (issue #14). Client libraries: `uv add google-api-python-client google-auth` (or `gspread`, pick one in #5 and record it in `docs/`).

## Reading: the two render options

One `spreadsheets.values.batchGet` call should request each range twice:

- `valueRenderOption=FORMULA` → the formula text (`=SUM(F20:F24)`) or the literal if typed
- `valueRenderOption=UNFORMATTED_VALUE` → raw numbers for math

Never `FORMATTED_VALUE` (locale-formatted strings break parsing). A typed value inside a formula region is visible exactly when FORMULA output ≠ a formula but the cell sits among formulas — that's error type 1 detection.

Labels/headers: read the first column/row with `valueRenderOption=UNFORMATTED_VALUE`. Whole-grid structure: `spreadsheets.get?includeGridData=true` — but that's a quota-heavy call; prefer targeted `fields=sheets.data.rowData.values(...)`.

## Cell metadata (override judgment — issue #5)

Note, font color and number format come from grid data (`spreadsheets.get` with `includeGridData` + `fields=sheets.data.rowData.values(note,userEnteredFormat(textFormat.foregroundColor),numberFormat)`), not from values APIs. Blue font = typed input convention; notes like "per budget meeting" = deliberate override signal. Signals, never proof alone.

## Sandbox flow (issue #6)

```
Drive files.copy(fileId=<original>, supportsAllDrives=true)   -> copy id
Sheets values.update(range, valueInputOption=RAW, ...)        -> write the patched formula
Sheets values.batchGet(...FORMULA...UNFORMATTED_VALUE)        -> read what Google recalculated
```

- `valueInputOption=RAW` for formulas (no interpretation/rewriting).
- Never write to the original spreadsheet: only copies, created in a dedicated folder, `files.delete` on cleanup (`discard`).
- `write_corrected_copy` (post-approval only) additionally adds a `Change log` tab.

## Quota traps that will bite a 150-run benchmark

- Quotas are per project and mostly per minute; the planted-error generator creates ~150 spreadsheets → use `batchCreate`/loop with backoff, or generate into ONE spreadsheet with many tabs and copy on demand.
- `includeGridData` and per-cell `get`s multiply request counts — batch everything (`values.batchGet` accepts many ranges).
- Errors 403 (not shared with the service account), 429 (quota), 400 (bad A1 range). The demo sheet must be shared with the **service account email**, not a user.
- Docs: https://developers.google.com/sheets/api/limits and https://developers.google.com/drive/api/guides/manage-uploads

## Scopes

- `https://www.googleapis.com/auth/spreadsheets` (read/write sheets)
- `https://www.googleapis.com/auth/drive` (copy + delete sandbox files)

## Testing without network (AGENTS.md: deep tests, no unitary tests)

Recorded fixtures for reads; a fake `Sandbox` for graph tests; exactly one opt-in live test marked `@pytest.mark.live` that does not run by default.

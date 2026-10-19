from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font

PERIODS = ["2025A", "2026A", "2027E", "2028E", "2029E", "2030E", "2031E", "2032E"]
FORECAST_COLS = ["D", "E", "F", "G", "H", "I"]
PERIOD_COLS = ["B", "C", *FORECAST_COLS]
ASSUMPTION_COLS = ["B", "C", "D", "E", "F", "G"]

ASSUMPTIONS = [
    ("Revenue growth", [0.87, 0.70, 0.27, 0.21, 0.14, 0.08]),
    ("Gross margin", [0.745, 0.75, 0.75, 0.75, 0.75, 0.75]),
    ("R&D % of revenue", [0.063, 0.054, 0.050, 0.048, 0.047, 0.046]),
    ("Sales & marketing % of revenue", [0.014, 0.012, 0.012, 0.011, 0.011, 0.011]),
    ("G&A % of revenue", [0.007, 0.006, 0.006, 0.006, 0.006, 0.006]),
    ("Other opex % of revenue", [0.003, 0.003, 0.002, 0.002, 0.002, 0.001]),
    ("D&A % of revenue", [0.006, 0.005, 0.005, 0.005, 0.005, 0.005]),
]

P_AND_L_ROWS = [
    ("Revenue", 130.5, 215.9),
    ("Cost of revenue", 32.6, 62.5),
    ("Gross profit", None, None),
    ("Gross margin", None, None),
    ("R&D", 12.9, 18.5),
    ("Sales & marketing", 2.1, 2.6),
    ("General & administrative", 1.4, 2.0),
    ("Other operating expenses", 0.0, 0.0),
    ("Total operating expenses", None, None),
    ("EBITDA", None, None),
    ("EBITDA margin", None, None),
    ("D&A", 1.9, 2.8),
    ("EBIT", None, None),
    ("EBIT margin", None, None),
]

PLANTED_CELL = "G11"
PLANTED_VALUE = 45.0


def _forecast_formula(row: int, index: int) -> str:
    col = FORECAST_COLS[index]
    previous = PERIOD_COLS[PERIOD_COLS.index(col) - 1]
    assumption = ASSUMPTION_COLS[index]
    if row == 3:
        return f"={previous}3*(1+Assumptions!{assumption}3)"
    if row == 4:
        return f"={col}3*(1-Assumptions!{assumption}4)"
    if row == 7:
        return f"={col}3*Assumptions!{assumption}5"
    if row == 8:
        return f"={col}3*Assumptions!{assumption}6"
    if row == 9:
        return f"={col}3*Assumptions!{assumption}7"
    if row == 10:
        return f"={col}3*Assumptions!{assumption}8"
    if row == 14:
        return f"={col}3*Assumptions!{assumption}9"
    raise ValueError(f"row {row} has no forecast rule")


def _derived_formula(row: int, col: str) -> str:
    if row == 5:
        return f"={col}3-{col}4"
    if row == 6:
        return f"={col}5/{col}3"
    if row == 11:
        return f"=SUM({col}7:{col}10)"
    if row == 12:
        return f"={col}15+{col}14"
    if row == 13:
        return f"={col}12/{col}3"
    if row == 15:
        return f"={col}5-{col}11"
    if row == 16:
        return f"={col}15/{col}3"
    raise ValueError(f"row {row} is not a derived row")


def build_workbook(planted: str | None = None) -> Workbook:
    book = Workbook()
    assumptions = book.active
    assumptions.title = "Assumptions"
    pnl = book.create_sheet("P&L")
    assumptions["A1"] = "NVIDIA long-term assumptions (based on public estimates, rounded)"
    assumptions["A2"] = "Assumption"
    for col, period in zip(ASSUMPTION_COLS, PERIODS[2:]):
        assumptions[f"{col}2"] = period
    for offset, (label, values) in enumerate(ASSUMPTIONS):
        row = 3 + offset
        assumptions[f"A{row}"] = label
        for col, value in zip(ASSUMPTION_COLS, values):
            cell = assumptions[f"{col}{row}"]
            cell.value = value
            cell.number_format = "0.0%"
    pnl["A1"] = "NVIDIA P&L (USD bn, fiscal years, based on public estimates)"
    pnl["A2"] = "Line"
    for col, period in zip(PERIOD_COLS, PERIODS):
        cell = pnl[f"{col}2"]
        cell.value = period
        cell.font = Font(bold=True)
    assumptions["A2"].font = Font(bold=True)
    for offset, (label, actual_2025, actual_2026) in enumerate(P_AND_L_ROWS):
        row = 3 + offset
        pnl[f"A{row}"] = label
        for col, actual in zip(("B", "C"), (actual_2025, actual_2026)):
            if actual is not None:
                pnl[f"{col}{row}"] = actual
        for index, col in enumerate(FORECAST_COLS):
            if row in (3, 4, 7, 8, 9, 10, 14):
                pnl[f"{col}{row}"] = _forecast_formula(row, index)
            else:
                pnl[f"{col}{row}"] = _derived_formula(row, col)
        if row not in (3, 4, 7, 8, 9, 10, 14):
            for col in PERIOD_COLS:
                pnl[f"{col}{row}"] = _derived_formula(row, col)
        for col in PERIOD_COLS:
            cell = pnl[f"{col}{row}"]
            if row in (6, 13, 16):
                cell.number_format = "0.0%"
            else:
                cell.number_format = "#,##0.0"
    if planted:
        pnl[planted] = PLANTED_VALUE
        pnl[planted].number_format = "#,##0.0"
    return book


def generate(output: Path) -> list[Path]:
    output.mkdir(parents=True, exist_ok=True)
    clean = output / "nvidia-pnl.xlsx"
    error = output / "nvidia-pnl-error.xlsx"
    build_workbook().save(clean)
    build_workbook(planted=PLANTED_CELL).save(error)
    return [clean, error]

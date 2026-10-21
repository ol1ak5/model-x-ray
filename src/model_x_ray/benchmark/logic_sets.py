import json
from pathlib import Path

import openpyxl
from openpyxl.styles import Font

BUDGET_YEARS = "BCDEF"
SAAS_YEARS = "CDEFG"
INPUT_FONT = Font(color="0000FF")


def budget() -> openpyxl.Workbook:
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = "Budget"
    sheet["A1"] = "Simple budget (EUR k)"
    sheet["A3"] = "EUR k"
    for index, column in enumerate(BUDGET_YEARS):
        sheet[f"{column}3"] = str(2022 + index)
    sheet["G3"] = "Total"
    inputs = {
        4: ("Revenue", [500, 540, 590, 640, 700]),
        5: ("Cost of goods sold", [200, 214, 232, 250, 272]),
        7: ("Salaries", [120, 126, 133, 140, 147]),
        8: ("Rent", [30, 30, 32, 32, 34]),
        9: ("Marketing", [25, 28, 30, 33, 36]),
    }
    formulas = {
        6: ("Gross profit", "={c}4-{c}5"),
        10: ("Total operating costs", "=SUM({c}7:{c}9)"),
        11: ("EBITDA", "={c}6-{c}10"),
        12: ("Taxes", "={c}11*$B$17"),
        13: ("Net income", "={c}11-{c}12"),
        14: ("Revenue growth", "={c}4/{p}4-1"),
    }
    for row, (label, values) in inputs.items():
        sheet[f"A{row}"] = label
        for column, value in zip(BUDGET_YEARS, values):
            sheet[f"{column}{row}"] = value
            sheet[f"{column}{row}"].font = INPUT_FONT
    for row, (label, formula) in formulas.items():
        sheet[f"A{row}"] = label
        for index, column in enumerate(BUDGET_YEARS):
            if row == 14 and index == 0:
                continue
            sheet[f"{column}{row}"] = formula.format(c=column, p=BUDGET_YEARS[index - 1])
    for row in range(4, 14):
        sheet[f"G{row}"] = f"=SUM(B{row}:F{row})"
    sheet["A17"], sheet["B17"] = "Tax rate", 0.25
    sheet["B17"].font = INPUT_FONT
    return book


BUDGET_CASES = [
    ("01-typed-number", "A typed number where the row uses a formula", {"D6": 351}),
    ("02-flipped-sign", "Net income adds taxes instead of subtracting them, in one year", {"E13": "=E11+E12"}),
    ("03-sum-leaves-out-a-row", "Total operating costs leaves out marketing, in one year", {"D10": "=SUM(D7:D8)"}),
    ("04-total-misses-a-year", "The 5-year revenue total leaves out 2026", {"G4": "=SUM(B4:E4)"}),
    ("05-wrong-tax-rate-typed", "One year multiplies by a typed 30% instead of the tax-rate cell", {"E12": "=E11*0.3"}),
    ("06-growth-wrong-year", "Revenue growth 2025 compares with 2023 instead of 2024", {"E14": "=E4/C4-1"}),
    ("07-whole-row-wrong-sign", "Gross profit adds cost of goods sold in every year (consistent logic error)", {f"{c}6": f"={c}4+{c}5" for c in BUDGET_YEARS}),
    ("08-whole-row-wrong-line", "EBITDA subtracts only salaries instead of total operating costs, in every year", {f"{c}11": f"={c}6-{c}7" for c in BUDGET_YEARS}),
    ("09-input-typo", "A typed input with an extra zero: rent 2024 is 320 instead of 32", {"D8": 320}),
    ("10-net-income-ignores-taxes", "Net income equals EBITDA in every year (taxes never subtracted)", {f"{c}13": f"={c}11" for c in BUDGET_YEARS}),
]


def saas() -> openpyxl.Workbook:
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = "Forecast"
    sheet["A1"] = "SaaS subscription forecast (EUR k unless stated)"
    sheet["B3"] = "Unit"
    for index, column in enumerate(SAAS_YEARS):
        sheet[f"{column}3"] = f"{2025 + index}E"
    rows = {
        4: ("Opening customers", "#"), 5: ("New customers", "#"), 6: ("Churned customers", "#"), 7: ("Closing customers", "#"),
        8: ("Monthly price per customer", "EUR"), 9: ("Annual revenue", "EUR k"),
        10: ("Hosting costs", "EUR k"), 11: ("Support costs", "EUR k"), 12: ("Total cost of service", "EUR k"),
        13: ("Contribution margin", "EUR k"), 14: ("Contribution margin %", "%"),
    }
    for row, (label, unit) in rows.items():
        sheet[f"A{row}"], sheet[f"B{row}"] = label, unit
    new, churn, price = [400, 450, 500, 540, 580], [60, 75, 90, 100, 110], [49, 49, 52, 52, 55]
    hosting, support = [180, 220, 260, 300, 340], [90, 105, 120, 135, 150]
    for index, column in enumerate(SAAS_YEARS):
        previous = SAAS_YEARS[index - 1] if index else None
        sheet[f"{column}4"] = 1200 if previous is None else f"={previous}7"
        sheet[f"{column}5"], sheet[f"{column}6"], sheet[f"{column}8"] = new[index], churn[index], price[index]
        sheet[f"{column}7"] = f"={column}4+{column}5-{column}6"
        sheet[f"{column}9"] = f"={column}7*{column}8*12/1000"
        sheet[f"{column}10"], sheet[f"{column}11"] = hosting[index], support[index]
        sheet[f"{column}12"] = f"={column}10+{column}11"
        sheet[f"{column}13"] = f"={column}9-{column}12"
        sheet[f"{column}14"] = f"={column}13/{column}9"
    return book


SAAS_CASES = [
    ("01-churn-added", "Closing customers adds churned customers instead of subtracting them, in every year", {f"{c}7": f"={c}4+{c}5+{c}6" for c in SAAS_YEARS}),
    ("02-margin-skips-support", "Contribution margin subtracts only hosting, not the total cost of service, in every year", {f"{c}13": f"={c}9-{c}10" for c in SAAS_YEARS}),
    ("03-ten-months-a-year", "Annual revenue multiplies the monthly price by 10 months instead of 12, in every year", {f"{c}9": f"={c}7*{c}8*10/1000" for c in SAAS_YEARS}),
    ("04-price-typo", "Monthly price 2027 typed as 5200 instead of 52", {"E8": 5200}),
    ("05-margin-pct-on-costs", "Contribution margin % divides by total cost of service instead of revenue, in every year", {f"{c}14": f"={c}13/{c}12" for c in SAAS_YEARS}),
]

SETS = {"simple-errors": (budget, BUDGET_CASES), "saas-errors": (saas, SAAS_CASES)}


def generate(output: Path) -> list[Path]:
    written = []
    for folder, (build, cases) in SETS.items():
        target = output / folder
        target.mkdir(parents=True, exist_ok=True)
        build().save(target / "00-clean.xlsx")
        records = []
        sheet = build().active.title
        for name, description, changes in cases:
            book = build()
            for ref, content in changes.items():
                book[sheet][ref] = content
            book.save(target / f"{name}.xlsx")
            records.append({"file": f"{name}.xlsx", "description": description, "cells": [f"{sheet}!{ref}" for ref in changes]})
        (target / "cases.json").write_text(json.dumps(records, indent=1) + "\n")
        written += [target / "00-clean.xlsx", *(target / f"{name}.xlsx" for name, _, _ in cases), target / "cases.json"]
    return written

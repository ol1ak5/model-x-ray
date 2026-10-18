import inspect
from pathlib import Path

import pytest

from model_x_ray.finance import BY_KEY, FORMULAS, accepted_forms, find_formulas, render_markdown

ROOT = Path(__file__).resolve().parents[1]


def compute(key: str, **inputs: float) -> float:
    return BY_KEY[key].compute(**inputs)


def test_damodarans_heineken_valuation_is_reproduced_by_the_library() -> None:
    assert compute("levered_beta", unlevered_beta=0.80, tax_rate=0.25, debt_to_equity=0.6698) == pytest.approx(1.20, abs=0.005)
    after_tax_debt = compute("after_tax_cost_of_debt", pre_tax_cost_of_debt=compute("pre_tax_cost_of_debt", risk_free=-0.005, company_default_spread=0.02), tax_rate=0.25)
    assert after_tax_debt == pytest.approx(0.0113, abs=0.0001)
    wacc = compute("wacc", equity=59.9, debt=40.1, cost_of_equity=0.0766, pre_tax_cost_of_debt=0.015, tax_rate=0.25)
    assert wacc == pytest.approx(0.0504, abs=0.0001)
    assert compute("terminal_value_gordon", next_cash_flow=2972, discount_rate=0.05, stable_growth=-0.005) == pytest.approx(54_034, abs=5)
    equity = compute("value_of_equity", operating_assets=51_691.19, debt=19_709.52, minority_interests=1_069.00, cash=1_751.60, non_operating_assets=1_401.00)
    assert equity == pytest.approx(34_065.26, abs=0.05)
    assert compute("value_per_share", value_of_equity_in_common_stock=equity, shares_outstanding=571.10) == pytest.approx(59.65, abs=0.01)


def test_cash_flow_growth_debt_and_ratio_formulas_give_textbook_answers() -> None:
    assert compute("fcff", ebit=1000, tax_rate=0.25, capital_expenditure=300, depreciation=200, change_in_working_capital=50) == 600
    assert compute("fcff", ebit=-100, tax_rate=0.25, capital_expenditure=0, depreciation=0, change_in_working_capital=0) == -100
    assert compute("fcfe", net_income=500, capital_expenditure=300, depreciation=200, change_in_working_capital=50, new_debt=80, debt_repaid=30) == 400
    assert compute("terminal_value_fundamental", next_after_tax_operating_income=100, stable_growth=0.03, stable_return_on_capital=0.10, cost_of_capital=0.08) == pytest.approx(1400)
    assert compute("fundamental_growth", reinvestment_rate=0.5, return_on_capital=0.12) == pytest.approx(0.06)
    assert compute("loan_payment", principal=10_000, rate=0.08 / 12, periods=10) == pytest.approx(1037.032089, abs=1e-6)
    assert compute("dscr", cash_flow_available_for_debt_service=130, principal_repayment=70, interest_paid=30) == pytest.approx(1.3)
    assert compute("llcr", cash_flows=[110, 110], rate=0.10, debt_outstanding=100) == pytest.approx(1.909, abs=0.001)
    assert compute("present_value", cash_flows=[100, 100], rate=0.10) == pytest.approx(173.554, abs=0.001)
    assert compute("cagr", end_value=121, start_value=100, years=2) == pytest.approx(0.10)
    assert compute("days_sales_outstanding", receivables=50, revenue=365) == pytest.approx(50)
    assert compute("enterprise_value", equity_value=800, debt=300, minority_interests=20, cash=120) == 1000
    with pytest.raises(ZeroDivisionError):
        compute("wacc", equity=0, debt=0, cost_of_equity=0.1, pre_tax_cost_of_debt=0.05, tax_rate=0.25)


def test_banking_and_academic_forms_of_fcff_and_terminal_value_agree_where_they_should() -> None:
    from_ebit = compute("fcff", ebit=1000, tax_rate=0.25, capital_expenditure=300, depreciation=200, change_in_working_capital=50)
    from_ebitda = compute("fcff_from_ebitda", ebitda=1200, ebit=1000, tax_rate=0.25, capital_expenditure=300, change_in_working_capital=50)
    assert from_ebit == from_ebitda == 600

    grown = compute("terminal_value_final_year_grown", final_year_cash_flow=100, discount_rate=0.08, stable_growth=0.02)
    next_year = compute("terminal_value_gordon", next_cash_flow=102, discount_rate=0.08, stable_growth=0.02)
    assert grown == pytest.approx(next_year) == pytest.approx(1700)
    assert {f.key for f in accepted_forms("terminal value")} == {"terminal_value_final_year_grown", "terminal_value_gordon", "terminal_value_fundamental", "terminal_value_exit_multiple"}
    assert {f.practice for f in accepted_forms("fcff")} == {"banking", "academic"}
    assert "unlevered taxes" in " ".join(BY_KEY["fcff_from_ebitda"].conventions).lower()
    assert "not of the terminal column" in " ".join(BY_KEY["terminal_value_gordon"].conventions)


def test_every_formula_documents_its_inputs_and_names_the_lines_it_matches() -> None:
    assert len(FORMULAS) >= 45
    assert len(BY_KEY) == len(FORMULAS)
    for formula in FORMULAS:
        parameters = list(inspect.signature(formula.compute).parameters)
        assert parameters == list(formula.inputs), formula.key
        assert formula.expression and formula.source and formula.family, formula.key
    assert [f.key for f in find_formulas("WACC")] == ["wacc"]
    assert "after_tax_operating_income" in [f.key for f in find_formulas("EBIT(1-t)")]
    assert "dscr" in [f.key for f in find_formulas("Minimum DSCR")]


def test_the_committed_library_document_matches_the_code() -> None:
    assert (ROOT / "docs" / "financial-formulas.md").read_text() == render_markdown() + "\n"

from collections.abc import Callable
from dataclasses import dataclass

DAMODARAN_SLIDES = "Damodaran, Valuation lecture slides (NYU Stern, spring 2023): building blocks of valuation, stable growth"
DAMODARAN_WACC = "Damodaran, wacccalc.xls (cost of capital worksheet, synthetic rating)"
DAMODARAN_GINZU = "Damodaran, fcffsimpleginzu.xlsx (valuation output)"
STANDARD = "Standard corporate finance practice"
PROJECT_FINANCE = "Standard project finance practice"
BANKING = "European investment banking and M&A practice (reviewed by Olga Aksenova)"


@dataclass(frozen=True)
class FinancialFormula:
    key: str
    name: str
    family: str
    expression: str
    inputs: dict[str, str]
    compute: Callable[..., float]
    aliases: tuple[str, ...] = ()
    conventions: tuple[str, ...] = ()
    common_errors: tuple[str, ...] = ()
    typical_range: tuple[float, float] | None = None
    source: str = STANDARD
    concept: str = ""
    practice: str = "common"

    @property
    def concept_name(self) -> str:
        return self.concept or self.key


def ratio(numerator: float, denominator: float) -> float:
    if denominator == 0:
        raise ZeroDivisionError("the denominator is zero")
    return numerator / denominator


def present_value(cash_flows: list[float], rate: float) -> float:
    return sum(flow / (1 + rate) ** period for period, flow in enumerate(cash_flows, start=1))


FORMULAS: list[FinancialFormula] = [
    FinancialFormula(
        "capm_cost_of_equity", "Cost of equity (CAPM)", "cost of capital",
        "risk_free + beta * equity_risk_premium + country_lambda * country_risk_premium",
        {"risk_free": "risk-free rate in the currency of the cash flows", "beta": "levered beta of the equity", "equity_risk_premium": "mature market equity risk premium", "country_lambda": "exposure to country risk (0 when none)", "country_risk_premium": "additional premium for country risk (0 when none)"},
        lambda risk_free, beta, equity_risk_premium, country_lambda=0.0, country_risk_premium=0.0: risk_free + beta * equity_risk_premium + country_lambda * country_risk_premium,
        aliases=("cost of equity", "ke", "required return on equity"),
        conventions=("The risk-free rate is in the same currency as the cash flows.", "Use the levered beta, not the unlevered one."),
        common_errors=("Unlevered beta used in the cost of equity.", "Risk-free rate in a different currency from the cash flows.", "Country risk added twice, in the premium and in the risk-free rate."),
        typical_range=(0.04, 0.20), source=DAMODARAN_WACC,
    ),
    FinancialFormula(
        "levered_beta", "Levered beta (Hamada)", "cost of capital",
        "unlevered_beta * (1 + (1 - tax_rate) * debt_to_equity)",
        {"unlevered_beta": "business (asset) beta", "tax_rate": "marginal tax rate", "debt_to_equity": "market debt to market equity"},
        lambda unlevered_beta, tax_rate, debt_to_equity: unlevered_beta * (1 + (1 - tax_rate) * debt_to_equity),
        aliases=("levered beta", "equity beta", "relevered beta"),
        conventions=("Debt to equity at market values.", "Marginal tax rate."),
        common_errors=("Debt to capital used where debt to equity is needed.", "Book values instead of market values.", "Tax shield left out."),
        typical_range=(0.3, 3.0), source=DAMODARAN_WACC,
    ),
    FinancialFormula(
        "unlevered_beta", "Unlevered beta", "cost of capital",
        "levered_beta / (1 + (1 - tax_rate) * debt_to_equity)",
        {"levered_beta": "observed equity beta", "tax_rate": "marginal tax rate", "debt_to_equity": "market debt to market equity"},
        lambda levered_beta, tax_rate, debt_to_equity: ratio(levered_beta, 1 + (1 - tax_rate) * debt_to_equity),
        aliases=("unlevered beta", "asset beta", "business beta"),
        common_errors=("Levered and unlevered betas swapped.",),
        typical_range=(0.2, 2.5), source=DAMODARAN_WACC,
    ),
    FinancialFormula(
        "pre_tax_cost_of_debt", "Pre-tax cost of debt", "cost of capital",
        "risk_free + company_default_spread + country_default_spread",
        {"risk_free": "risk-free rate", "company_default_spread": "spread for the company's (synthetic) rating", "country_default_spread": "spread for country risk (0 when none)"},
        lambda risk_free, company_default_spread, country_default_spread=0.0: risk_free + company_default_spread + country_default_spread,
        aliases=("pre-tax cost of debt", "borrowing rate", "kd"),
        conventions=("The current borrowing rate, not the coupon on old debt.",),
        common_errors=("Historical coupon rate used instead of today's borrowing rate.",),
        typical_range=(0.0, 0.20), source=DAMODARAN_WACC,
    ),
    FinancialFormula(
        "after_tax_cost_of_debt", "After-tax cost of debt", "cost of capital",
        "pre_tax_cost_of_debt * (1 - tax_rate)",
        {"pre_tax_cost_of_debt": "current borrowing rate", "tax_rate": "marginal tax rate"},
        lambda pre_tax_cost_of_debt, tax_rate: pre_tax_cost_of_debt * (1 - tax_rate),
        aliases=("after-tax cost of debt", "cost of debt after tax"),
        common_errors=("Pre-tax rate used in the cost of capital.", "Effective instead of marginal tax rate."),
        typical_range=(0.0, 0.15), source=DAMODARAN_WACC,
    ),
    FinancialFormula(
        "wacc", "Weighted average cost of capital", "cost of capital",
        "equity / (equity + debt + preferred) * cost_of_equity + debt / (equity + debt + preferred) * pre_tax_cost_of_debt * (1 - tax_rate) + preferred / (equity + debt + preferred) * cost_of_preferred",
        {"equity": "market value of equity", "debt": "market value of debt, including lease debt", "cost_of_equity": "cost of equity", "pre_tax_cost_of_debt": "current borrowing rate", "tax_rate": "marginal tax rate", "preferred": "market value of preferred stock (0 when none)", "cost_of_preferred": "cost of preferred stock"},
        lambda equity, debt, cost_of_equity, pre_tax_cost_of_debt, tax_rate, preferred=0.0, cost_of_preferred=0.0: (
            ratio(equity * cost_of_equity + debt * pre_tax_cost_of_debt * (1 - tax_rate) + preferred * cost_of_preferred, equity + debt + preferred)
        ),
        aliases=("wacc", "cost of capital", "discount rate", "weighted average cost of capital"),
        conventions=("Market value weights.", "The cost of debt is after tax.", "FCFF is discounted at the WACC, FCFE at the cost of equity."),
        common_errors=("Pre-tax cost of debt (tax shield missing).", "Book value weights.", "Weights that do not add up to 100%.", "Nominal cash flows discounted at a real rate, or the reverse."),
        typical_range=(0.03, 0.15), source=DAMODARAN_SLIDES,
    ),
    FinancialFormula(
        "cost_of_preferred", "Cost of preferred stock", "cost of capital",
        "preferred_dividend / preferred_price",
        {"preferred_dividend": "annual dividend per preferred share", "preferred_price": "market price per preferred share"},
        lambda preferred_dividend, preferred_price: ratio(preferred_dividend, preferred_price),
        aliases=("cost of preferred", "preferred yield"), typical_range=(0.0, 0.15), source=DAMODARAN_WACC,
    ),
    FinancialFormula(
        "interest_coverage", "Interest coverage ratio", "debt",
        "ebit / interest_expense",
        {"ebit": "operating income", "interest_expense": "interest expense"},
        lambda ebit, interest_expense: ratio(ebit, interest_expense),
        aliases=("interest coverage", "times interest earned", "ebit / interest"),
        conventions=("Drives the synthetic rating and the default spread.",),
        common_errors=("EBITDA used where EBIT is meant.", "Interest income netted against interest expense without saying so."),
        typical_range=(0.0, 50.0), source=DAMODARAN_WACC,
    ),
    FinancialFormula(
        "market_value_of_debt", "Market value of debt (bond approximation)", "cost of capital",
        "interest * (1 - (1 + pre_tax_cost_of_debt) ** -maturity) / pre_tax_cost_of_debt + face_value / (1 + pre_tax_cost_of_debt) ** maturity",
        {"interest": "annual interest expense", "pre_tax_cost_of_debt": "current borrowing rate", "maturity": "weighted average maturity in years", "face_value": "book value of debt"},
        lambda interest, pre_tax_cost_of_debt, maturity, face_value: interest * ratio(1 - (1 + pre_tax_cost_of_debt) ** -maturity, pre_tax_cost_of_debt) + face_value / (1 + pre_tax_cost_of_debt) ** maturity,
        aliases=("market value of debt", "estimated market value of straight debt"), source=DAMODARAN_WACC,
    ),
    FinancialFormula(
        "after_tax_operating_income", "After-tax operating income (EBIT(1-t))", "cash flow",
        "ebit * (1 - tax_rate) when ebit > 0, else ebit",
        {"ebit": "operating income", "tax_rate": "tax rate"},
        lambda ebit, tax_rate: ebit * (1 - tax_rate) if ebit > 0 else ebit,
        aliases=("ebit(1-t)", "nopat", "after-tax operating income", "nopla"),
        conventions=("No tax is charged on an operating loss; losses carried forward reduce later taxes.",),
        common_errors=("Tax charged on negative EBIT.", "Interest deducted before the tax (that is net income, not NOPAT)."),
        source=DAMODARAN_GINZU,
    ),
    FinancialFormula(
        "net_capex", "Net capital expenditure", "cash flow",
        "capital_expenditure - depreciation",
        {"capital_expenditure": "capital expenditure (positive)", "depreciation": "depreciation and amortisation"},
        lambda capital_expenditure, depreciation: capital_expenditure - depreciation,
        aliases=("net capex", "net capital expenditure"),
        common_errors=("Sign convention mixed: capex entered negative and then subtracted again.",),
        source=DAMODARAN_SLIDES,
    ),
    FinancialFormula(
        "change_in_working_capital", "Change in non-cash working capital", "cash flow",
        "working_capital - prior_working_capital",
        {"working_capital": "non-cash working capital this period", "prior_working_capital": "non-cash working capital last period"},
        lambda working_capital, prior_working_capital: working_capital - prior_working_capital,
        aliases=("change in working capital", "increase in working capital", "delta nwc"),
        conventions=("Non-cash working capital excludes cash and short-term debt.", "An increase is a use of cash."),
        common_errors=("The sign is reversed (an increase added to cash flow).", "Cash included in working capital."),
        source=DAMODARAN_SLIDES,
    ),
    FinancialFormula(
        "fcff", "Free cash flow to the firm", "cash flow",
        "ebit * (1 - tax_rate) - (capital_expenditure - depreciation) - change_in_working_capital",
        {"ebit": "operating income", "tax_rate": "tax rate", "capital_expenditure": "capital expenditure", "depreciation": "depreciation and amortisation", "change_in_working_capital": "change in non-cash working capital"},
        lambda ebit, tax_rate, capital_expenditure, depreciation, change_in_working_capital: (ebit * (1 - tax_rate) if ebit > 0 else ebit) - (capital_expenditure - depreciation) - change_in_working_capital,
        aliases=("fcff", "free cash flow to firm", "unlevered free cash flow", "ufcf"),
        conventions=("Before any debt payment; discounted at the cost of capital.",),
        common_errors=("Interest deducted (that mixes FCFF and FCFE).", "Depreciation not added back.", "FCFF discounted at the cost of equity."),
        source=DAMODARAN_SLIDES, concept="fcff", practice="academic",
    ),
    FinancialFormula(
        "fcff_from_ebitda", "Free cash flow to the firm, built from EBITDA", "cash flow",
        "ebitda - ebit * tax_rate - capital_expenditure - change_in_working_capital",
        {"ebitda": "EBITDA", "ebit": "operating income, the base for the unlevered taxes", "tax_rate": "tax rate", "capital_expenditure": "capital expenditure", "change_in_working_capital": "change in non-cash working capital (and provisions, when the model tracks them)"},
        lambda ebitda, ebit, tax_rate, capital_expenditure, change_in_working_capital: ebitda - max(ebit, 0.0) * tax_rate - capital_expenditure - change_in_working_capital,
        aliases=("fcff", "free cash flow to firm", "unlevered free cash flow", "ufcf", "free cash flow"),
        conventions=(
            "Taxes are unlevered taxes: EBIT times the tax rate, as if the company had no debt. Levered taxes (the P&L tax, after interest) belong to FCFE. The tax saving on interest is in the WACC, through the after-tax cost of debt.",
            "Equal to EBIT(1-t) + D&A - capex - change in working capital; only the layout differs.",
        ),
        common_errors=(
            "Levered taxes (the P&L tax, after interest) used instead of unlevered taxes on EBIT, which counts the interest tax shield twice.",
            "Tax computed on EBITDA instead of EBIT.",
            "Interest deducted from the cash flow.",
            "An increase in working capital added instead of subtracted.",
        ),
        source=BANKING, concept="fcff", practice="banking",
    ),
    FinancialFormula(
        "fcfe", "Free cash flow to equity", "cash flow",
        "net_income - (capital_expenditure - depreciation) - change_in_working_capital + (new_debt - debt_repaid)",
        {"net_income": "net income", "capital_expenditure": "capital expenditure", "depreciation": "depreciation and amortisation", "change_in_working_capital": "change in non-cash working capital", "new_debt": "new debt issued", "debt_repaid": "debt repaid"},
        lambda net_income, capital_expenditure, depreciation, change_in_working_capital, new_debt=0.0, debt_repaid=0.0: net_income - (capital_expenditure - depreciation) - change_in_working_capital + new_debt - debt_repaid,
        aliases=("fcfe", "free cash flow to equity", "levered free cash flow"),
        conventions=("After debt payments; discounted at the cost of equity.",),
        common_errors=("FCFE discounted at the WACC.", "Net borrowing left out."),
        source=DAMODARAN_SLIDES,
    ),
    FinancialFormula(
        "fcfe_debt_ratio", "Free cash flow to equity (target debt ratio)", "cash flow",
        "net_income - (1 - debt_ratio) * (capital_expenditure - depreciation) - (1 - debt_ratio) * change_in_working_capital",
        {"net_income": "net income", "debt_ratio": "share of reinvestment funded with debt", "capital_expenditure": "capital expenditure", "depreciation": "depreciation and amortisation", "change_in_working_capital": "change in non-cash working capital"},
        lambda net_income, debt_ratio, capital_expenditure, depreciation, change_in_working_capital: net_income - (1 - debt_ratio) * (capital_expenditure - depreciation) - (1 - debt_ratio) * change_in_working_capital,
        aliases=("fcfe with debt ratio",), source=DAMODARAN_SLIDES,
    ),
    FinancialFormula(
        "reinvestment_rate", "Reinvestment rate", "growth",
        "(capital_expenditure - depreciation + change_in_working_capital) / after_tax_operating_income",
        {"capital_expenditure": "capital expenditure", "depreciation": "depreciation and amortisation", "change_in_working_capital": "change in non-cash working capital", "after_tax_operating_income": "EBIT(1-t)"},
        lambda capital_expenditure, depreciation, change_in_working_capital, after_tax_operating_income: ratio(capital_expenditure - depreciation + change_in_working_capital, after_tax_operating_income),
        aliases=("reinvestment rate",), typical_range=(-0.5, 1.5), source=DAMODARAN_SLIDES,
    ),
    FinancialFormula(
        "return_on_capital", "Return on invested capital", "growth",
        "after_tax_operating_income / invested_capital",
        {"after_tax_operating_income": "EBIT(1-t)", "invested_capital": "book equity + book debt - cash, at the start of the period"},
        lambda after_tax_operating_income, invested_capital: ratio(after_tax_operating_income, invested_capital),
        aliases=("roic", "roc", "return on capital", "return on invested capital"),
        conventions=("Invested capital at the start of the period.",),
        common_errors=("Pre-tax EBIT in the numerator.", "Cash left inside invested capital."),
        typical_range=(-0.5, 0.6), source=DAMODARAN_SLIDES,
    ),
    FinancialFormula(
        "fundamental_growth", "Expected growth in operating income", "growth",
        "reinvestment_rate * return_on_capital",
        {"reinvestment_rate": "reinvestment rate", "return_on_capital": "return on capital"},
        lambda reinvestment_rate, return_on_capital: reinvestment_rate * return_on_capital,
        aliases=("fundamental growth", "expected growth"),
        conventions=("Growth has to be paid for with reinvestment.",),
        common_errors=("High growth assumed with no reinvestment.",), source=DAMODARAN_SLIDES,
    ),
    FinancialFormula(
        "reinvestment_from_sales_to_capital", "Reinvestment from the sales-to-capital ratio", "growth",
        "(revenue - prior_revenue) / sales_to_capital",
        {"revenue": "revenue this period", "prior_revenue": "revenue last period", "sales_to_capital": "revenue generated per unit of capital invested"},
        lambda revenue, prior_revenue, sales_to_capital: ratio(revenue - prior_revenue, sales_to_capital),
        aliases=("reinvestment", "sales to capital"), source=DAMODARAN_GINZU,
    ),
    FinancialFormula(
        "equity_growth", "Expected growth in earnings per share", "growth",
        "retention_ratio * return_on_equity",
        {"retention_ratio": "1 - payout ratio", "return_on_equity": "net income / book equity"},
        lambda retention_ratio, return_on_equity: retention_ratio * return_on_equity,
        aliases=("eps growth", "sustainable growth"), source=DAMODARAN_SLIDES,
    ),
    FinancialFormula(
        "stable_payout_ratio", "Payout ratio in stable growth", "growth",
        "1 - stable_growth / return_on_equity",
        {"stable_growth": "growth rate in perpetuity", "return_on_equity": "return on equity in stable growth"},
        lambda stable_growth, return_on_equity: 1 - ratio(stable_growth, return_on_equity),
        aliases=("stable payout ratio",), source=DAMODARAN_SLIDES,
    ),
    FinancialFormula(
        "discount_factor", "Discount factor", "valuation",
        "1 / (1 + rate) ** period",
        {"rate": "discount rate per period", "period": "number of periods from today"},
        lambda rate, period: 1 / (1 + rate) ** period,
        aliases=("discount factor", "cumulated discount factor", "pv factor"),
        conventions=("When the rate changes over time, multiply the factors of each period instead of using one rate.",),
        common_errors=("Period counted from 0 for a cash flow at the end of year 1.", "One flat rate applied after the rate changed."),
        source=DAMODARAN_GINZU,
    ),
    FinancialFormula(
        "mid_year_discount_factor", "Mid-year discount factor", "valuation",
        "1 / (1 + rate) ** (period - 0.5)",
        {"rate": "discount rate", "period": "year number, 1 for the first year"},
        lambda rate, period: 1 / (1 + rate) ** (period - 0.5),
        aliases=("mid-year convention",),
        common_errors=("Mid-year factor applied to the terminal value as well as the yearly flows.",),
    ),
    FinancialFormula(
        "present_value", "Present value of a series of cash flows", "valuation",
        "sum(cash_flow_t / (1 + rate) ** t for t = 1..n)",
        {"cash_flows": "cash flows at the end of periods 1 to n", "rate": "discount rate"},
        present_value,
        aliases=("npv", "present value", "pv"),
        conventions=("Excel's NPV discounts the first value by one full period; add any cash flow at time 0 outside it.",),
        common_errors=("Time-0 investment included inside NPV(), discounting it by a year.",),
    ),
    FinancialFormula(
        "terminal_value_final_year_grown", "Terminal value from the last forecast year, grown one period", "valuation",
        "final_year_cash_flow * (1 + stable_growth) / (discount_rate - stable_growth)",
        {"final_year_cash_flow": "cash flow of the last forecast year, normalised (capex in line with D&A, working capital consistent with g)", "discount_rate": "WACC (or cost of equity for FCFE)", "stable_growth": "growth rate in perpetuity"},
        lambda final_year_cash_flow, discount_rate, stable_growth: ratio(final_year_cash_flow * (1 + stable_growth), discount_rate - stable_growth),
        aliases=("terminal value", "continuing value", "gordon growth", "tv", "perpetuity value"),
        conventions=("The last forecast year is a normal year, so it is grown by (1 + g) to get the first year of the perpetuity.", "Discounted with the factor of the last forecast year.", "Usually cross-checked against an exit multiple."),
        common_errors=(
            "The (1 + g) factor left out when the last year is a normal forecast year.",
            "The last year not normalised (capex below D&A, or working capital release carried into perpetuity).",
            "Growth at or above the discount rate.",
        ),
        source=BANKING, concept="terminal value", practice="banking",
    ),
    FinancialFormula(
        "terminal_value_gordon", "Terminal value from the first year of the perpetuity", "valuation",
        "next_cash_flow / (discount_rate - stable_growth)",
        {"next_cash_flow": "cash flow of the terminal column n+1 (2051 when the forecast ends in 2050)", "discount_rate": "cost of capital (or cost of equity for FCFE) in stable growth", "stable_growth": "growth rate in perpetuity"},
        lambda next_cash_flow, discount_rate, stable_growth: ratio(next_cash_flow, discount_rate - stable_growth),
        aliases=("terminal value", "continuing value", "gordon growth", "tv"),
        conventions=(
            "The cash flow is already the first year of the perpetuity: a separate normalised terminal-year column n+1 (2051 when the forecast ends in 2050).",
            "The terminal value is dated at the end of year n, so it is discounted with the factor of year n (2050), not of the terminal column (2051).",
            "Stable growth cannot exceed the growth of the economy (in practice the risk-free rate).",
        ),
        common_errors=(
            "Last forecast year's cash flow used without growth as if it were year n+1.",
            "The flow grown twice: the terminal-column (n+1) flow multiplied again by (1 + g).",
            "Terminal value discounted with the factor of the terminal column (n+1) instead of year n.",
            "Growth at or above the discount rate.",
        ),
        source=DAMODARAN_SLIDES, concept="terminal value", practice="both",
    ),
    FinancialFormula(
        "terminal_value_fundamental", "Terminal value with consistent reinvestment", "valuation",
        "next_after_tax_operating_income * (1 - stable_growth / stable_return_on_capital) / (cost_of_capital - stable_growth)",
        {"next_after_tax_operating_income": "EBIT(1-t) in the first stable year", "stable_growth": "growth rate in perpetuity", "stable_return_on_capital": "return on capital in perpetuity", "cost_of_capital": "cost of capital in stable growth"},
        lambda next_after_tax_operating_income, stable_growth, stable_return_on_capital, cost_of_capital: next_after_tax_operating_income * (1 - ratio(stable_growth, stable_return_on_capital)) / (cost_of_capital - stable_growth),
        aliases=("terminal value", "stable growth value"),
        conventions=("The stable reinvestment rate is growth divided by return on capital.",),
        common_errors=("Capex set equal to depreciation in stable growth while assuming positive growth.",),
        source=DAMODARAN_SLIDES, concept="terminal value", practice="academic",
    ),
    FinancialFormula(
        "terminal_value_exit_multiple", "Terminal value (exit multiple)", "valuation",
        "final_year_metric * exit_multiple",
        {"final_year_metric": "EBITDA (or other metric) in the last forecast year", "exit_multiple": "multiple applied at exit"},
        lambda final_year_metric, exit_multiple: final_year_metric * exit_multiple,
        aliases=("exit multiple", "exit value"),
        common_errors=("Multiple applied to next year's metric when it was quoted on trailing figures.",),
        source=BANKING, concept="terminal value", practice="banking",
    ),
    FinancialFormula(
        "value_of_equity", "Value of equity from the value of operating assets", "valuation",
        "operating_assets - debt - minority_interests + cash + non_operating_assets - options",
        {"operating_assets": "present value of the cash flows and terminal value", "debt": "debt, including lease debt", "minority_interests": "minority (non-controlling) interests", "cash": "cash and marketable securities", "non_operating_assets": "cross holdings and other non-operating assets", "options": "value of employee options outstanding (0 when none)"},
        lambda operating_assets, debt, minority_interests, cash, non_operating_assets=0.0, options=0.0: operating_assets - debt - minority_interests + cash + non_operating_assets - options,
        aliases=("value of equity", "equity value", "equity bridge"),
        common_errors=("Cash added twice (it is already in the operating assets).", "Minority interests forgotten.", "Lease debt left out of debt while the cost of capital includes it."),
        source=DAMODARAN_GINZU,
    ),
    FinancialFormula(
        "value_per_share", "Value per share", "valuation",
        "value_of_equity_in_common_stock / shares_outstanding",
        {"value_of_equity_in_common_stock": "value of equity after options", "shares_outstanding": "number of shares outstanding"},
        lambda value_of_equity_in_common_stock, shares_outstanding: ratio(value_of_equity_in_common_stock, shares_outstanding),
        aliases=("value per share", "estimated value per share"),
        common_errors=("Diluted shares used after options were already subtracted (counted twice).",),
        source=DAMODARAN_GINZU,
    ),
    FinancialFormula(
        "dividend_discount_stable", "Value of equity per share (stable dividend discount)", "valuation",
        "next_dividend / (cost_of_equity - stable_growth)",
        {"next_dividend": "expected dividend per share next year", "cost_of_equity": "cost of equity", "stable_growth": "growth rate in perpetuity"},
        lambda next_dividend, cost_of_equity, stable_growth: ratio(next_dividend, cost_of_equity - stable_growth),
        aliases=("ddm", "gordon growth model", "dividend discount model"),
        common_errors=("Current dividend used instead of next year's.",), source=DAMODARAN_SLIDES,
    ),
    FinancialFormula(
        "gross_margin", "Gross margin", "income statement",
        "gross_profit / revenue",
        {"gross_profit": "revenue - cost of goods sold", "revenue": "revenue"},
        lambda gross_profit, revenue: ratio(gross_profit, revenue),
        aliases=("gross margin", "gross profit margin"), typical_range=(-0.5, 1.0),
        common_errors=("COGS entered with a negative sign and subtracted again.",),
    ),
    FinancialFormula(
        "ebitda", "EBITDA", "income statement",
        "ebit + depreciation_and_amortisation",
        {"ebit": "operating income", "depreciation_and_amortisation": "depreciation and amortisation"},
        lambda ebit, depreciation_and_amortisation: ebit + depreciation_and_amortisation,
        aliases=("ebitda", "operating profit before depreciation"),
        common_errors=("D&A subtracted instead of added back.", "Non-recurring items mixed in without saying so."),
    ),
    FinancialFormula(
        "operating_margin", "Operating (EBIT) margin", "income statement",
        "ebit / revenue",
        {"ebit": "operating income", "revenue": "revenue"},
        lambda ebit, revenue: ratio(ebit, revenue),
        aliases=("operating margin", "ebit margin"), typical_range=(-1.0, 0.7), source=DAMODARAN_GINZU,
    ),
    FinancialFormula(
        "effective_tax_rate", "Effective tax rate", "income statement",
        "taxes / pre_tax_income",
        {"taxes": "taxes paid or accrued", "pre_tax_income": "income before taxes"},
        lambda taxes, pre_tax_income: ratio(taxes, pre_tax_income),
        aliases=("effective tax rate",), typical_range=(0.0, 0.5),
        common_errors=("Effective rate used where the marginal rate belongs (tax shield on debt).",),
    ),
    FinancialFormula(
        "growth_rate", "Period-on-period growth rate", "income statement",
        "value / prior_value - 1",
        {"value": "value this period", "prior_value": "value last period"},
        lambda value, prior_value: ratio(value, prior_value) - 1,
        aliases=("growth rate", "growth", "yoy"),
        common_errors=("Growth measured against the wrong period (lag error).",),
    ),
    FinancialFormula(
        "cagr", "Compound annual growth rate", "income statement",
        "(end_value / start_value) ** (1 / years) - 1",
        {"end_value": "value at the end", "start_value": "value at the start", "years": "number of years between them"},
        lambda end_value, start_value, years: ratio(end_value, start_value) ** (1 / years) - 1,
        aliases=("cagr", "compound annual growth rate"),
        common_errors=("Number of years counted as the number of data points.",),
    ),
    FinancialFormula(
        "days_sales_outstanding", "Days sales outstanding", "working capital",
        "receivables / revenue * days_in_period",
        {"receivables": "accounts receivable", "revenue": "revenue for the period", "days_in_period": "365 for a year"},
        lambda receivables, revenue, days_in_period=365.0: ratio(receivables, revenue) * days_in_period,
        aliases=("dso", "debtor days", "receivable days"), typical_range=(0.0, 365.0),
    ),
    FinancialFormula(
        "days_payables_outstanding", "Days payables outstanding", "working capital",
        "payables / cost_of_goods_sold * days_in_period",
        {"payables": "accounts payable", "cost_of_goods_sold": "cost of goods sold for the period", "days_in_period": "365 for a year"},
        lambda payables, cost_of_goods_sold, days_in_period=365.0: ratio(payables, cost_of_goods_sold) * days_in_period,
        aliases=("dpo", "creditor days", "payable days"), typical_range=(0.0, 365.0),
        common_errors=("Revenue used instead of cost of goods sold.",),
    ),
    FinancialFormula(
        "days_inventory_outstanding", "Days inventory outstanding", "working capital",
        "inventory / cost_of_goods_sold * days_in_period",
        {"inventory": "inventory", "cost_of_goods_sold": "cost of goods sold for the period", "days_in_period": "365 for a year"},
        lambda inventory, cost_of_goods_sold, days_in_period=365.0: ratio(inventory, cost_of_goods_sold) * days_in_period,
        aliases=("dio", "inventory days"), typical_range=(0.0, 365.0),
    ),
    FinancialFormula(
        "straight_line_depreciation", "Straight-line depreciation", "working capital",
        "(asset_cost - salvage_value) / useful_life",
        {"asset_cost": "cost of the asset", "salvage_value": "value at the end of its life", "useful_life": "useful life in periods"},
        lambda asset_cost, salvage_value, useful_life: ratio(asset_cost - salvage_value, useful_life),
        aliases=("depreciation", "straight-line depreciation"),
        common_errors=("Depreciation continuing after the asset is fully depreciated.",),
    ),
    FinancialFormula(
        "loan_payment", "Level loan payment (annuity)", "debt",
        "principal * rate / (1 - (1 + rate) ** -periods)",
        {"principal": "amount borrowed", "rate": "interest rate per period", "periods": "number of payments"},
        lambda principal, rate, periods: principal / periods if rate == 0 else principal * rate / (1 - (1 + rate) ** -periods),
        aliases=("pmt", "annuity payment", "debt service"),
        conventions=("Same as Excel's PMT, with the sign flipped.",),
        common_errors=("Annual rate used with monthly periods.",),
    ),
    FinancialFormula(
        "dscr", "Debt service coverage ratio", "debt",
        "cash_flow_available_for_debt_service / (principal_repayment + interest_paid)",
        {"cash_flow_available_for_debt_service": "CFADS for the period", "principal_repayment": "principal repaid in the period", "interest_paid": "interest paid in the period"},
        lambda cash_flow_available_for_debt_service, principal_repayment, interest_paid: ratio(cash_flow_available_for_debt_service, principal_repayment + interest_paid),
        aliases=("dscr", "debt service coverage"),
        conventions=("Measured period by period; lenders test the minimum and the average.",),
        common_errors=("Interest only in the denominator (that is interest cover).", "CFADS after debt service instead of before."),
        typical_range=(0.0, 10.0), source=PROJECT_FINANCE,
    ),
    FinancialFormula(
        "llcr", "Loan life coverage ratio", "debt",
        "present value of CFADS over the remaining loan life at the debt rate / debt outstanding",
        {"cash_flows": "CFADS for each remaining period of the loan", "rate": "interest rate of the debt", "debt_outstanding": "debt outstanding at the test date"},
        lambda cash_flows, rate, debt_outstanding: ratio(present_value(cash_flows, rate), debt_outstanding),
        aliases=("llcr", "loan life coverage"),
        common_errors=("Discounted at the cost of equity or the WACC instead of the debt rate.", "Cash flows beyond the loan's maturity included."),
        typical_range=(0.0, 10.0), source=PROJECT_FINANCE,
    ),
    FinancialFormula(
        "net_debt_to_ebitda", "Net debt to EBITDA", "debt",
        "(debt - cash) / ebitda",
        {"debt": "total debt", "cash": "cash and equivalents", "ebitda": "EBITDA"},
        lambda debt, cash, ebitda: ratio(debt - cash, ebitda),
        aliases=("leverage", "net debt / ebitda", "net leverage"), typical_range=(-5.0, 15.0),
    ),
    FinancialFormula(
        "enterprise_value", "Enterprise value", "multiples",
        "equity_value + debt + minority_interests - cash",
        {"equity_value": "market value of equity", "debt": "debt", "minority_interests": "minority interests", "cash": "cash and equivalents"},
        lambda equity_value, debt, minority_interests, cash: equity_value + debt + minority_interests - cash,
        aliases=("enterprise value", "ev", "firm value"),
        common_errors=("Cash added instead of subtracted.", "Minority interests left out while EBITDA consolidates the subsidiary."),
    ),
    FinancialFormula(
        "ev_to_ebitda", "EV / EBITDA", "multiples",
        "enterprise_value / ebitda",
        {"enterprise_value": "enterprise value", "ebitda": "EBITDA"},
        lambda enterprise_value, ebitda: ratio(enterprise_value, ebitda),
        aliases=("ev/ebitda", "ebitda multiple"), typical_range=(0.0, 50.0),
        common_errors=("Equity value divided by EBITDA (numerator and denominator inconsistent).",),
    ),
    FinancialFormula(
        "price_to_earnings", "Price to earnings", "multiples",
        "price_per_share / earnings_per_share",
        {"price_per_share": "share price", "earnings_per_share": "earnings per share"},
        lambda price_per_share, earnings_per_share: ratio(price_per_share, earnings_per_share),
        aliases=("p/e", "pe ratio", "price earnings"), typical_range=(0.0, 100.0),
        common_errors=("Trailing and forward EPS mixed across comparables.",),
    ),
]

BY_KEY = {formula.key: formula for formula in FORMULAS}


def accepted_forms(concept: str) -> list[FinancialFormula]:
    return [formula for formula in FORMULAS if formula.concept_name == concept]


def find_formulas(label: str) -> list[FinancialFormula]:
    text = label.strip().lower()
    return [formula for formula in FORMULAS if any(alias == text or alias in text for alias in formula.aliases)]


def render_markdown() -> str:
    lines = [
        "# Financial formula library",
        "",
        "The reference formulas Model X-Ray checks a model against. A concept can have several accepted forms (for example European banking practice and Damodaran's academic form); a model passes when it matches any of them, and is flagged only when it matches none or mixes conventions. Each one has the names a model usually gives the line, the formula, its conventions, the errors analysts typically make and, where it helps, a plausible range. Formulas are standard finance; the wording is ours. Conventions follow Aswath Damodaran's public material where noted (NYU Stern), without implying his endorsement.",
        "",
        "Generated from `src/model_x_ray/finance.py` by `tools/export_formulas.py`.",
        "",
    ]
    for family in dict.fromkeys(formula.family for formula in FORMULAS):
        lines += [f"## {family.capitalize()}", ""]
        for formula in (f for f in FORMULAS if f.family == family):
            lines.append(f"### {formula.name}")
            lines.append("")
            lines.append(f"`{formula.expression}`")
            lines.append("")
            if formula.aliases:
                lines.append(f"- **Usual names:** {', '.join(formula.aliases)}")
            lines.append(f"- **Inputs:** " + "; ".join(f"`{name}` ({text})" for name, text in formula.inputs.items()))
            for convention in formula.conventions:
                lines.append(f"- **Convention:** {convention}")
            for error in formula.common_errors:
                lines.append(f"- **Typical error:** {error}")
            if formula.typical_range:
                low, high = formula.typical_range
                lines.append(f"- **Plausible range:** {low:g} to {high:g}")
            if formula.concept:
                lines.append(f"- **Accepted form of:** {formula.concept} ({formula.practice} practice)")
            lines.append(f"- **Source:** {formula.source}")
            lines.append("")
    return "\n".join(lines)

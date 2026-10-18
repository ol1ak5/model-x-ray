# Financial formula library

The reference formulas Model X-Ray checks a model against. A concept can have several accepted forms (for example European banking practice and Damodaran's academic form); a model passes when it matches any of them, and is flagged only when it matches none or mixes conventions. Each one has the names a model usually gives the line, the formula, its conventions, the errors analysts typically make and, where it helps, a plausible range. Formulas are standard finance; the wording is ours. Conventions follow Aswath Damodaran's public material where noted (NYU Stern), without implying his endorsement.

Generated from `src/model_x_ray/finance.py` by `tools/export_formulas.py`.

## Cost of capital

### Cost of equity (CAPM)

`risk_free + beta * equity_risk_premium + country_lambda * country_risk_premium`

- **Usual names:** cost of equity, ke, required return on equity
- **Inputs:** `risk_free` (risk-free rate in the currency of the cash flows); `beta` (levered beta of the equity); `equity_risk_premium` (mature market equity risk premium); `country_lambda` (exposure to country risk (0 when none)); `country_risk_premium` (additional premium for country risk (0 when none))
- **Convention:** The risk-free rate is in the same currency as the cash flows.
- **Convention:** Use the levered beta, not the unlevered one.
- **Typical error:** Unlevered beta used in the cost of equity.
- **Typical error:** Risk-free rate in a different currency from the cash flows.
- **Typical error:** Country risk added twice, in the premium and in the risk-free rate.
- **Plausible range:** 0.04 to 0.2
- **Source:** Damodaran, wacccalc.xls (cost of capital worksheet, synthetic rating)

### Levered beta (Hamada)

`unlevered_beta * (1 + (1 - tax_rate) * debt_to_equity)`

- **Usual names:** levered beta, equity beta, relevered beta
- **Inputs:** `unlevered_beta` (business (asset) beta); `tax_rate` (marginal tax rate); `debt_to_equity` (market debt to market equity)
- **Convention:** Debt to equity at market values.
- **Convention:** Marginal tax rate.
- **Typical error:** Debt to capital used where debt to equity is needed.
- **Typical error:** Book values instead of market values.
- **Typical error:** Tax shield left out.
- **Plausible range:** 0.3 to 3
- **Source:** Damodaran, wacccalc.xls (cost of capital worksheet, synthetic rating)

### Unlevered beta

`levered_beta / (1 + (1 - tax_rate) * debt_to_equity)`

- **Usual names:** unlevered beta, asset beta, business beta
- **Inputs:** `levered_beta` (observed equity beta); `tax_rate` (marginal tax rate); `debt_to_equity` (market debt to market equity)
- **Typical error:** Levered and unlevered betas swapped.
- **Plausible range:** 0.2 to 2.5
- **Source:** Damodaran, wacccalc.xls (cost of capital worksheet, synthetic rating)

### Pre-tax cost of debt

`risk_free + company_default_spread + country_default_spread`

- **Usual names:** pre-tax cost of debt, borrowing rate, kd
- **Inputs:** `risk_free` (risk-free rate); `company_default_spread` (spread for the company's (synthetic) rating); `country_default_spread` (spread for country risk (0 when none))
- **Convention:** The current borrowing rate, not the coupon on old debt.
- **Typical error:** Historical coupon rate used instead of today's borrowing rate.
- **Plausible range:** 0 to 0.2
- **Source:** Damodaran, wacccalc.xls (cost of capital worksheet, synthetic rating)

### After-tax cost of debt

`pre_tax_cost_of_debt * (1 - tax_rate)`

- **Usual names:** after-tax cost of debt, cost of debt after tax
- **Inputs:** `pre_tax_cost_of_debt` (current borrowing rate); `tax_rate` (marginal tax rate)
- **Typical error:** Pre-tax rate used in the cost of capital.
- **Typical error:** Effective instead of marginal tax rate.
- **Plausible range:** 0 to 0.15
- **Source:** Damodaran, wacccalc.xls (cost of capital worksheet, synthetic rating)

### Weighted average cost of capital

`equity / (equity + debt + preferred) * cost_of_equity + debt / (equity + debt + preferred) * pre_tax_cost_of_debt * (1 - tax_rate) + preferred / (equity + debt + preferred) * cost_of_preferred`

- **Usual names:** wacc, cost of capital, discount rate, weighted average cost of capital
- **Inputs:** `equity` (market value of equity); `debt` (market value of debt, including lease debt); `cost_of_equity` (cost of equity); `pre_tax_cost_of_debt` (current borrowing rate); `tax_rate` (marginal tax rate); `preferred` (market value of preferred stock (0 when none)); `cost_of_preferred` (cost of preferred stock)
- **Convention:** Market value weights.
- **Convention:** The cost of debt is after tax.
- **Convention:** FCFF is discounted at the WACC, FCFE at the cost of equity.
- **Typical error:** Pre-tax cost of debt (tax shield missing).
- **Typical error:** Book value weights.
- **Typical error:** Weights that do not add up to 100%.
- **Typical error:** Nominal cash flows discounted at a real rate, or the reverse.
- **Plausible range:** 0.03 to 0.15
- **Source:** Damodaran, Valuation lecture slides (NYU Stern, spring 2023): building blocks of valuation, stable growth

### Cost of preferred stock

`preferred_dividend / preferred_price`

- **Usual names:** cost of preferred, preferred yield
- **Inputs:** `preferred_dividend` (annual dividend per preferred share); `preferred_price` (market price per preferred share)
- **Plausible range:** 0 to 0.15
- **Source:** Damodaran, wacccalc.xls (cost of capital worksheet, synthetic rating)

### Market value of debt (bond approximation)

`interest * (1 - (1 + pre_tax_cost_of_debt) ** -maturity) / pre_tax_cost_of_debt + face_value / (1 + pre_tax_cost_of_debt) ** maturity`

- **Usual names:** market value of debt, estimated market value of straight debt
- **Inputs:** `interest` (annual interest expense); `pre_tax_cost_of_debt` (current borrowing rate); `maturity` (weighted average maturity in years); `face_value` (book value of debt)
- **Source:** Damodaran, wacccalc.xls (cost of capital worksheet, synthetic rating)

## Debt

### Interest coverage ratio

`ebit / interest_expense`

- **Usual names:** interest coverage, times interest earned, ebit / interest
- **Inputs:** `ebit` (operating income); `interest_expense` (interest expense)
- **Convention:** Drives the synthetic rating and the default spread.
- **Typical error:** EBITDA used where EBIT is meant.
- **Typical error:** Interest income netted against interest expense without saying so.
- **Plausible range:** 0 to 50
- **Source:** Damodaran, wacccalc.xls (cost of capital worksheet, synthetic rating)

### Level loan payment (annuity)

`principal * rate / (1 - (1 + rate) ** -periods)`

- **Usual names:** pmt, annuity payment, debt service
- **Inputs:** `principal` (amount borrowed); `rate` (interest rate per period); `periods` (number of payments)
- **Convention:** Same as Excel's PMT, with the sign flipped.
- **Typical error:** Annual rate used with monthly periods.
- **Source:** Standard corporate finance practice

### Debt service coverage ratio

`cash_flow_available_for_debt_service / (principal_repayment + interest_paid)`

- **Usual names:** dscr, debt service coverage
- **Inputs:** `cash_flow_available_for_debt_service` (CFADS for the period); `principal_repayment` (principal repaid in the period); `interest_paid` (interest paid in the period)
- **Convention:** Measured period by period; lenders test the minimum and the average.
- **Typical error:** Interest only in the denominator (that is interest cover).
- **Typical error:** CFADS after debt service instead of before.
- **Plausible range:** 0 to 10
- **Source:** Standard project finance practice

### Loan life coverage ratio

`present value of CFADS over the remaining loan life at the debt rate / debt outstanding`

- **Usual names:** llcr, loan life coverage
- **Inputs:** `cash_flows` (CFADS for each remaining period of the loan); `rate` (interest rate of the debt); `debt_outstanding` (debt outstanding at the test date)
- **Typical error:** Discounted at the cost of equity or the WACC instead of the debt rate.
- **Typical error:** Cash flows beyond the loan's maturity included.
- **Plausible range:** 0 to 10
- **Source:** Standard project finance practice

### Net debt to EBITDA

`(debt - cash) / ebitda`

- **Usual names:** leverage, net debt / ebitda, net leverage
- **Inputs:** `debt` (total debt); `cash` (cash and equivalents); `ebitda` (EBITDA)
- **Plausible range:** -5 to 15
- **Source:** Standard corporate finance practice

## Cash flow

### After-tax operating income (EBIT(1-t))

`ebit * (1 - tax_rate) when ebit > 0, else ebit`

- **Usual names:** ebit(1-t), nopat, after-tax operating income, nopla
- **Inputs:** `ebit` (operating income); `tax_rate` (tax rate)
- **Convention:** No tax is charged on an operating loss; losses carried forward reduce later taxes.
- **Typical error:** Tax charged on negative EBIT.
- **Typical error:** Interest deducted before the tax (that is net income, not NOPAT).
- **Source:** Damodaran, fcffsimpleginzu.xlsx (valuation output)

### Net capital expenditure

`capital_expenditure - depreciation`

- **Usual names:** net capex, net capital expenditure
- **Inputs:** `capital_expenditure` (capital expenditure (positive)); `depreciation` (depreciation and amortisation)
- **Typical error:** Sign convention mixed: capex entered negative and then subtracted again.
- **Source:** Damodaran, Valuation lecture slides (NYU Stern, spring 2023): building blocks of valuation, stable growth

### Change in non-cash working capital

`working_capital - prior_working_capital`

- **Usual names:** change in working capital, increase in working capital, delta nwc
- **Inputs:** `working_capital` (non-cash working capital this period); `prior_working_capital` (non-cash working capital last period)
- **Convention:** Non-cash working capital excludes cash and short-term debt.
- **Convention:** An increase is a use of cash.
- **Typical error:** The sign is reversed (an increase added to cash flow).
- **Typical error:** Cash included in working capital.
- **Source:** Damodaran, Valuation lecture slides (NYU Stern, spring 2023): building blocks of valuation, stable growth

### Free cash flow to the firm

`ebit * (1 - tax_rate) - (capital_expenditure - depreciation) - change_in_working_capital`

- **Usual names:** fcff, free cash flow to firm, unlevered free cash flow, ufcf
- **Inputs:** `ebit` (operating income); `tax_rate` (tax rate); `capital_expenditure` (capital expenditure); `depreciation` (depreciation and amortisation); `change_in_working_capital` (change in non-cash working capital)
- **Convention:** Before any debt payment; discounted at the cost of capital.
- **Typical error:** Interest deducted (that mixes FCFF and FCFE).
- **Typical error:** Depreciation not added back.
- **Typical error:** FCFF discounted at the cost of equity.
- **Accepted form of:** fcff (academic practice)
- **Source:** Damodaran, Valuation lecture slides (NYU Stern, spring 2023): building blocks of valuation, stable growth

### Free cash flow to the firm, built from EBITDA

`ebitda - ebit * tax_rate - capital_expenditure - change_in_working_capital`

- **Usual names:** fcff, free cash flow to firm, unlevered free cash flow, ufcf, free cash flow
- **Inputs:** `ebitda` (EBITDA); `ebit` (operating income, the base for the notional tax); `tax_rate` (tax rate); `capital_expenditure` (capital expenditure); `change_in_working_capital` (change in non-cash working capital (and provisions, when the model tracks them))
- **Convention:** Taxes are notional (operating) taxes: EBIT times the tax rate, as if the company had no debt. The tax saving on interest is in the WACC, through the after-tax cost of debt.
- **Convention:** Equal to EBIT(1-t) + D&A - capex - change in working capital; only the layout differs.
- **Typical error:** Actual P&L taxes used instead of notional taxes on EBIT (the interest tax shield counted twice).
- **Typical error:** Tax computed on EBITDA instead of EBIT.
- **Typical error:** Interest deducted from the cash flow.
- **Typical error:** An increase in working capital added instead of subtracted.
- **Accepted form of:** fcff (banking practice)
- **Source:** European investment banking and M&A practice (reviewed by Olga Aksenova)

### Free cash flow to equity

`net_income - (capital_expenditure - depreciation) - change_in_working_capital + (new_debt - debt_repaid)`

- **Usual names:** fcfe, free cash flow to equity, levered free cash flow
- **Inputs:** `net_income` (net income); `capital_expenditure` (capital expenditure); `depreciation` (depreciation and amortisation); `change_in_working_capital` (change in non-cash working capital); `new_debt` (new debt issued); `debt_repaid` (debt repaid)
- **Convention:** After debt payments; discounted at the cost of equity.
- **Typical error:** FCFE discounted at the WACC.
- **Typical error:** Net borrowing left out.
- **Source:** Damodaran, Valuation lecture slides (NYU Stern, spring 2023): building blocks of valuation, stable growth

### Free cash flow to equity (target debt ratio)

`net_income - (1 - debt_ratio) * (capital_expenditure - depreciation) - (1 - debt_ratio) * change_in_working_capital`

- **Usual names:** fcfe with debt ratio
- **Inputs:** `net_income` (net income); `debt_ratio` (share of reinvestment funded with debt); `capital_expenditure` (capital expenditure); `depreciation` (depreciation and amortisation); `change_in_working_capital` (change in non-cash working capital)
- **Source:** Damodaran, Valuation lecture slides (NYU Stern, spring 2023): building blocks of valuation, stable growth

## Growth

### Reinvestment rate

`(capital_expenditure - depreciation + change_in_working_capital) / after_tax_operating_income`

- **Usual names:** reinvestment rate
- **Inputs:** `capital_expenditure` (capital expenditure); `depreciation` (depreciation and amortisation); `change_in_working_capital` (change in non-cash working capital); `after_tax_operating_income` (EBIT(1-t))
- **Plausible range:** -0.5 to 1.5
- **Source:** Damodaran, Valuation lecture slides (NYU Stern, spring 2023): building blocks of valuation, stable growth

### Return on invested capital

`after_tax_operating_income / invested_capital`

- **Usual names:** roic, roc, return on capital, return on invested capital
- **Inputs:** `after_tax_operating_income` (EBIT(1-t)); `invested_capital` (book equity + book debt - cash, at the start of the period)
- **Convention:** Invested capital at the start of the period.
- **Typical error:** Pre-tax EBIT in the numerator.
- **Typical error:** Cash left inside invested capital.
- **Plausible range:** -0.5 to 0.6
- **Source:** Damodaran, Valuation lecture slides (NYU Stern, spring 2023): building blocks of valuation, stable growth

### Expected growth in operating income

`reinvestment_rate * return_on_capital`

- **Usual names:** fundamental growth, expected growth
- **Inputs:** `reinvestment_rate` (reinvestment rate); `return_on_capital` (return on capital)
- **Convention:** Growth has to be paid for with reinvestment.
- **Typical error:** High growth assumed with no reinvestment.
- **Source:** Damodaran, Valuation lecture slides (NYU Stern, spring 2023): building blocks of valuation, stable growth

### Reinvestment from the sales-to-capital ratio

`(revenue - prior_revenue) / sales_to_capital`

- **Usual names:** reinvestment, sales to capital
- **Inputs:** `revenue` (revenue this period); `prior_revenue` (revenue last period); `sales_to_capital` (revenue generated per unit of capital invested)
- **Source:** Damodaran, fcffsimpleginzu.xlsx (valuation output)

### Expected growth in earnings per share

`retention_ratio * return_on_equity`

- **Usual names:** eps growth, sustainable growth
- **Inputs:** `retention_ratio` (1 - payout ratio); `return_on_equity` (net income / book equity)
- **Source:** Damodaran, Valuation lecture slides (NYU Stern, spring 2023): building blocks of valuation, stable growth

### Payout ratio in stable growth

`1 - stable_growth / return_on_equity`

- **Usual names:** stable payout ratio
- **Inputs:** `stable_growth` (growth rate in perpetuity); `return_on_equity` (return on equity in stable growth)
- **Source:** Damodaran, Valuation lecture slides (NYU Stern, spring 2023): building blocks of valuation, stable growth

## Valuation

### Discount factor

`1 / (1 + rate) ** period`

- **Usual names:** discount factor, cumulated discount factor, pv factor
- **Inputs:** `rate` (discount rate per period); `period` (number of periods from today)
- **Convention:** When the rate changes over time, multiply the factors of each period instead of using one rate.
- **Typical error:** Period counted from 0 for a cash flow at the end of year 1.
- **Typical error:** One flat rate applied after the rate changed.
- **Source:** Damodaran, fcffsimpleginzu.xlsx (valuation output)

### Mid-year discount factor

`1 / (1 + rate) ** (period - 0.5)`

- **Usual names:** mid-year convention
- **Inputs:** `rate` (discount rate); `period` (year number, 1 for the first year)
- **Typical error:** Mid-year factor applied to the terminal value as well as the yearly flows.
- **Source:** Standard corporate finance practice

### Present value of a series of cash flows

`sum(cash_flow_t / (1 + rate) ** t for t = 1..n)`

- **Usual names:** npv, present value, pv
- **Inputs:** `cash_flows` (cash flows at the end of periods 1 to n); `rate` (discount rate)
- **Convention:** Excel's NPV discounts the first value by one full period; add any cash flow at time 0 outside it.
- **Typical error:** Time-0 investment included inside NPV(), discounting it by a year.
- **Source:** Standard corporate finance practice

### Terminal value from the last forecast year, grown one period

`final_year_cash_flow * (1 + stable_growth) / (discount_rate - stable_growth)`

- **Usual names:** terminal value, continuing value, gordon growth, tv, perpetuity value
- **Inputs:** `final_year_cash_flow` (cash flow of the last forecast year, normalised (capex in line with D&A, working capital consistent with g)); `discount_rate` (WACC (or cost of equity for FCFE)); `stable_growth` (growth rate in perpetuity)
- **Convention:** The last forecast year is a normal year, so it is grown by (1 + g) to get the first year of the perpetuity.
- **Convention:** Discounted with the factor of the last forecast year.
- **Convention:** Usually cross-checked against an exit multiple.
- **Typical error:** The (1 + g) factor left out when the last year is a normal forecast year.
- **Typical error:** The last year not normalised (capex below D&A, or working capital release carried into perpetuity).
- **Typical error:** Growth at or above the discount rate.
- **Accepted form of:** terminal value (banking practice)
- **Source:** European investment banking and M&A practice (reviewed by Olga Aksenova)

### Terminal value from the first year of the perpetuity

`next_cash_flow / (discount_rate - stable_growth)`

- **Usual names:** terminal value, continuing value, gordon growth, tv
- **Inputs:** `next_cash_flow` (cash flow in the first year after the forecast); `discount_rate` (cost of capital (or cost of equity for FCFE) in stable growth); `stable_growth` (growth rate in perpetuity)
- **Convention:** The cash flow is already the first year of the perpetuity: a separate normalised terminal-year column, or a projection whose last year (e.g. 2050) is taken as year n+1.
- **Convention:** Stable growth cannot exceed the growth of the economy (in practice the risk-free rate).
- **Typical error:** Last-year cash flow used instead of next year's.
- **Typical error:** The flow grown twice: a terminal-year (n+1) flow multiplied again by (1 + g).
- **Typical error:** Growth at or above the discount rate.
- **Typical error:** Terminal value discounted one period too many or too few.
- **Accepted form of:** terminal value (both practice)
- **Source:** Damodaran, Valuation lecture slides (NYU Stern, spring 2023): building blocks of valuation, stable growth

### Terminal value with consistent reinvestment

`next_after_tax_operating_income * (1 - stable_growth / stable_return_on_capital) / (cost_of_capital - stable_growth)`

- **Usual names:** terminal value, stable growth value
- **Inputs:** `next_after_tax_operating_income` (EBIT(1-t) in the first stable year); `stable_growth` (growth rate in perpetuity); `stable_return_on_capital` (return on capital in perpetuity); `cost_of_capital` (cost of capital in stable growth)
- **Convention:** The stable reinvestment rate is growth divided by return on capital.
- **Typical error:** Capex set equal to depreciation in stable growth while assuming positive growth.
- **Accepted form of:** terminal value (academic practice)
- **Source:** Damodaran, Valuation lecture slides (NYU Stern, spring 2023): building blocks of valuation, stable growth

### Terminal value (exit multiple)

`final_year_metric * exit_multiple`

- **Usual names:** exit multiple, exit value
- **Inputs:** `final_year_metric` (EBITDA (or other metric) in the last forecast year); `exit_multiple` (multiple applied at exit)
- **Typical error:** Multiple applied to next year's metric when it was quoted on trailing figures.
- **Accepted form of:** terminal value (banking practice)
- **Source:** European investment banking and M&A practice (reviewed by Olga Aksenova)

### Value of equity from the value of operating assets

`operating_assets - debt - minority_interests + cash + non_operating_assets - options`

- **Usual names:** value of equity, equity value, equity bridge
- **Inputs:** `operating_assets` (present value of the cash flows and terminal value); `debt` (debt, including lease debt); `minority_interests` (minority (non-controlling) interests); `cash` (cash and marketable securities); `non_operating_assets` (cross holdings and other non-operating assets); `options` (value of employee options outstanding (0 when none))
- **Typical error:** Cash added twice (it is already in the operating assets).
- **Typical error:** Minority interests forgotten.
- **Typical error:** Lease debt left out of debt while the cost of capital includes it.
- **Source:** Damodaran, fcffsimpleginzu.xlsx (valuation output)

### Value per share

`value_of_equity_in_common_stock / shares_outstanding`

- **Usual names:** value per share, estimated value per share
- **Inputs:** `value_of_equity_in_common_stock` (value of equity after options); `shares_outstanding` (number of shares outstanding)
- **Typical error:** Diluted shares used after options were already subtracted (counted twice).
- **Source:** Damodaran, fcffsimpleginzu.xlsx (valuation output)

### Value of equity per share (stable dividend discount)

`next_dividend / (cost_of_equity - stable_growth)`

- **Usual names:** ddm, gordon growth model, dividend discount model
- **Inputs:** `next_dividend` (expected dividend per share next year); `cost_of_equity` (cost of equity); `stable_growth` (growth rate in perpetuity)
- **Typical error:** Current dividend used instead of next year's.
- **Source:** Damodaran, Valuation lecture slides (NYU Stern, spring 2023): building blocks of valuation, stable growth

## Income statement

### Gross margin

`gross_profit / revenue`

- **Usual names:** gross margin, gross profit margin
- **Inputs:** `gross_profit` (revenue - cost of goods sold); `revenue` (revenue)
- **Typical error:** COGS entered with a negative sign and subtracted again.
- **Plausible range:** -0.5 to 1
- **Source:** Standard corporate finance practice

### EBITDA

`ebit + depreciation_and_amortisation`

- **Usual names:** ebitda, operating profit before depreciation
- **Inputs:** `ebit` (operating income); `depreciation_and_amortisation` (depreciation and amortisation)
- **Typical error:** D&A subtracted instead of added back.
- **Typical error:** Non-recurring items mixed in without saying so.
- **Source:** Standard corporate finance practice

### Operating (EBIT) margin

`ebit / revenue`

- **Usual names:** operating margin, ebit margin
- **Inputs:** `ebit` (operating income); `revenue` (revenue)
- **Plausible range:** -1 to 0.7
- **Source:** Damodaran, fcffsimpleginzu.xlsx (valuation output)

### Effective tax rate

`taxes / pre_tax_income`

- **Usual names:** effective tax rate
- **Inputs:** `taxes` (taxes paid or accrued); `pre_tax_income` (income before taxes)
- **Typical error:** Effective rate used where the marginal rate belongs (tax shield on debt).
- **Plausible range:** 0 to 0.5
- **Source:** Standard corporate finance practice

### Period-on-period growth rate

`value / prior_value - 1`

- **Usual names:** growth rate, growth, yoy
- **Inputs:** `value` (value this period); `prior_value` (value last period)
- **Typical error:** Growth measured against the wrong period (lag error).
- **Source:** Standard corporate finance practice

### Compound annual growth rate

`(end_value / start_value) ** (1 / years) - 1`

- **Usual names:** cagr, compound annual growth rate
- **Inputs:** `end_value` (value at the end); `start_value` (value at the start); `years` (number of years between them)
- **Typical error:** Number of years counted as the number of data points.
- **Source:** Standard corporate finance practice

## Working capital

### Days sales outstanding

`receivables / revenue * days_in_period`

- **Usual names:** dso, debtor days, receivable days
- **Inputs:** `receivables` (accounts receivable); `revenue` (revenue for the period); `days_in_period` (365 for a year)
- **Plausible range:** 0 to 365
- **Source:** Standard corporate finance practice

### Days payables outstanding

`payables / cost_of_goods_sold * days_in_period`

- **Usual names:** dpo, creditor days, payable days
- **Inputs:** `payables` (accounts payable); `cost_of_goods_sold` (cost of goods sold for the period); `days_in_period` (365 for a year)
- **Typical error:** Revenue used instead of cost of goods sold.
- **Plausible range:** 0 to 365
- **Source:** Standard corporate finance practice

### Days inventory outstanding

`inventory / cost_of_goods_sold * days_in_period`

- **Usual names:** dio, inventory days
- **Inputs:** `inventory` (inventory); `cost_of_goods_sold` (cost of goods sold for the period); `days_in_period` (365 for a year)
- **Plausible range:** 0 to 365
- **Source:** Standard corporate finance practice

### Straight-line depreciation

`(asset_cost - salvage_value) / useful_life`

- **Usual names:** depreciation, straight-line depreciation
- **Inputs:** `asset_cost` (cost of the asset); `salvage_value` (value at the end of its life); `useful_life` (useful life in periods)
- **Typical error:** Depreciation continuing after the asset is fully depreciated.
- **Source:** Standard corporate finance practice

## Multiples

### Enterprise value

`equity_value + debt + minority_interests - cash`

- **Usual names:** enterprise value, ev, firm value
- **Inputs:** `equity_value` (market value of equity); `debt` (debt); `minority_interests` (minority interests); `cash` (cash and equivalents)
- **Typical error:** Cash added instead of subtracted.
- **Typical error:** Minority interests left out while EBITDA consolidates the subsidiary.
- **Source:** Standard corporate finance practice

### EV / EBITDA

`enterprise_value / ebitda`

- **Usual names:** ev/ebitda, ebitda multiple
- **Inputs:** `enterprise_value` (enterprise value); `ebitda` (EBITDA)
- **Typical error:** Equity value divided by EBITDA (numerator and denominator inconsistent).
- **Plausible range:** 0 to 50
- **Source:** Standard corporate finance practice

### Price to earnings

`price_per_share / earnings_per_share`

- **Usual names:** p/e, pe ratio, price earnings
- **Inputs:** `price_per_share` (share price); `earnings_per_share` (earnings per share)
- **Typical error:** Trailing and forward EPS mixed across comparables.
- **Plausible range:** 0 to 100
- **Source:** Standard corporate finance practice


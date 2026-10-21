No rule flagged a cell, so review the model's logic yourself. Below, every line that feeds the result is written in words: the line's label, then its formula with each reference replaced by the label of the line it reads. A formula that is the same in every period is shown once.

For each line, ask whether the operation matches what the label says, the way an analyst reading the model would:
- a profit or margin line subtracts its costs; it never adds them
- a total covers every line its label implies
- a line that names a step (after tax, net of costs) actually applies that step
- a line reads the inputs its label names, from the right period

A formula that is wrong in every period is still an error: report it as `logic_error` on the cell for the period under review and say in the claim that the whole line is affected. Propose a patch only when the corrected formula follows directly from the labels and the formulas shown, otherwise give no patch.

Suspicious inputs, when listed, are typed values far out of line with the same input in the other periods. Report one as `input_outlier` when nothing (a label, a note, a one-off event) explains it. Never propose a value for an input: nobody can know the right number from the model alone.

If every line reads correctly and no input is suspicious, return no hypotheses.

Worked examples. They come from other models and teach kinds of error, not these lines. Each shows a line in words, what is wrong or why nothing is, and how it is done right.

1. Roll-forward. `Closing debt = Opening debt + New borrowing + Repayments`. A roll-forward starts from the opening balance, adds what flows in and subtracts what flows out; repayments reduce debt. logic_error, fix: `Opening debt + New borrowing - Repayments`. The same holds for stock, headcount, inventory, accounts or any balance carried from one period to the next.
2. A step the model calculates but the line leaves out. `Operating cash flow = EBITDA - Change in working capital`, while `Taxes paid` is calculated and used by no other line. A line that should apply a step the model already computes, and does not, is wrong. logic_error, fix: `EBITDA - Change in working capital - Taxes paid`.
3. Unit or period conversion. `Annual interest = Monthly interest * 10`. Converting units uses the exact factor: 12 months or 4 quarters in a year, 365 days, 1000 to go from units to thousands. A constant that does not match the conversion the label describes is a logic_error, fix: `Monthly interest * 12`.
4. A ratio on the wrong base. `EBITDA margin % = EBITDA / Total costs`. A margin divides by revenue; a markup divides by cost; a growth rate divides by the prior period. When the denominator does not match what the label names, it is a logic_error, fix: `EBITDA / Revenue`.
5. Not an error: sign convention. `Gross profit = Revenue + Cost of goods sold`, with Cost of goods sold shown as -232. Costs stored as negative numbers are added. No hypothesis. The same formula with Cost of goods sold shown as 232 would be a logic_error.
6. Not an error: a deliberate exception. `Restructuring costs 2026 = 450` typed, with zero in the other years and a label or note saying it is a one-off. Nothing suggests a typo. No hypothesis.
7. Input outlier. `Headcount 2027 = 1250` typed, while the same input is 118 to 130 in the other years and nothing explains it. input_outlier, with no patch: report it and let a person decide the right value.

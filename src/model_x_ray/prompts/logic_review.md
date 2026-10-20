No rule flagged a cell, so review the model's logic yourself. Below, every line that feeds the result is written in words: the line's label, then its formula with each reference replaced by the label of the line it reads. A formula that is the same in every period is shown once.

For each line, ask whether the operation matches what the label says, the way an analyst reading the model would:
- a profit or margin line subtracts its costs; it never adds them
- a total covers every line its label implies
- a line that names a step (after tax, net of costs) actually applies that step
- a line reads the inputs its label names, from the right period

A formula that is wrong in every period is still an error: report it as `logic_error` on the cell for the period under review and say in the claim that the whole line is affected. Propose a patch only when the corrected formula follows directly from the labels and the formulas shown, otherwise give no patch.

Suspicious inputs, when listed, are typed values far out of line with the same input in the other periods. Report one as `input_outlier` when nothing (a label, a note, a one-off event) explains it. Never propose a value for an input: nobody can know the right number from the model alone.

If every line reads correctly and no input is suspicious, return no hypotheses.

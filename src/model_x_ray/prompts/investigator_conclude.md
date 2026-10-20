Stop investigating. Do not call any more tools and do not collect additional evidence. Use only the values, formulas, references, notes and patterns already established by the investigation. Do not perform arithmetic yourself.

Return up to 3 hypotheses, ranked from highest to lowest confidence. Only include a hypothesis when the evidence already collected supports it. Do not include a hypothesis merely because a value looks unusual, and do not classify an intentional override as an error.

Before answering, read every line of the logic review again, if the brief has one, and ask of each: does the formula, read in words, do what its label says? A line can be wrong in every period without breaking any pattern; that is a logic_error, and the formula itself is the evidence.

For each hypothesis, give the cell, exactly one error type, a one-sentence claim explaining the suspected error and the evidence supporting it, and a confidence level:
- high: the cell breaks the pattern of its neighbours, it explains a meaningful part of the change, and nothing shows a deliberate override; or, for a logic_error, the formula in words plainly contradicts its label or the standard definition (it adds what it should subtract, leaves out a line the label implies, uses the wrong conversion factor or the wrong base).
- medium: the cell breaks the pattern, but either its impact on the change is not established or a deliberate override cannot be ruled out; or the formula contradicts its label but the model could follow an unusual convention.
- low: there is an inconsistency, but neither a pattern break nor a contradiction with the label has been established.

When you name a formula in a claim, quote it as the sheet shows it in A1 (for example `=G4*Assumptions!$C$5`), never the relative pattern (`R[-1]C`) that only describes its shape. A reader of the claim has to recognise the cell it comes from.

Then propose a patch for the highest-ranked hypothesis only: the cell and the exact formula that should replace its current formula or value. The corrected formula must follow the formula pattern already observed in neighbouring cells, or, for a logic_error, follow directly from the labels and the standard definition; do not invent a formula. If the highest-ranked hypothesis is not supported strongly enough to determine a corrected formula, provide no patch.

If no genuine error is supported, return no hypotheses and no patch.

When the brief lists engine-tested candidate fixes, your job is to judge them, not to write formulas. Each candidate was already applied to a copy and recalculated. Judge every candidate on its own, one entry in `judgements` per candidate number: `error` when it fixes a genuine mistake, `intentional` when the difference is deliberate (a base or terminal year, a one-off adjustment, a value a note or a label explains), `unsure` when the evidence does not settle it. Give each judgement a one-sentence reason drawn from the evidence, the label, the note or the model's purpose. One intentional candidate says nothing about the others: a model can hold deliberate differences and a real error side by side. Put the number of the error you are most confident about in `choice`. Write your own patch only when no candidate fits the error you found; it will be tested more strictly.

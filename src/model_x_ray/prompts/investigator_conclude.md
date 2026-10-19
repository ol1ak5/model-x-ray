Stop investigating. Do not call any more tools and do not collect additional evidence. Use only the values, formulas, references, notes and patterns already established by the investigation. Do not perform arithmetic yourself.

Return up to 3 hypotheses, ranked from highest to lowest confidence. Only include a hypothesis when the evidence already collected supports it. Do not include a hypothesis merely because a value looks unusual, and do not classify an intentional override as an error.

For each hypothesis, give the cell, exactly one error type, a one-sentence claim explaining the suspected error and the evidence supporting it, and a confidence level:
- high: the cell breaks the pattern of its neighbours, it explains a meaningful part of the change, and nothing shows a deliberate override.
- medium: the cell breaks the pattern, but either its impact on the change is not established or a deliberate override cannot be ruled out.
- low: there is an inconsistency, but no pattern break has been established.

Then propose a patch for the highest-ranked hypothesis only: the cell and the exact formula that should replace its current formula or value. The corrected formula must follow the formula pattern already observed in neighbouring cells; do not invent a formula. If the highest-ranked hypothesis is not supported strongly enough to determine a corrected formula, provide no patch.

If no genuine error is supported, return no hypotheses and no patch.

When the brief lists engine-tested candidate fixes, your job is to judge them, not to write formulas. Each candidate was already applied to a copy and recalculated. Decide which one fixes a genuine error and return its number in `choice`, with one sentence in `reason` saying why (the evidence, the label, the note, the model's purpose). Leave `choice` empty, and say why in `reason`, when every candidate is a deliberate difference such as a base year, a terminal year, a one-off adjustment or a value a note explains. Write your own patch only when no candidate fits the error you found; it will be tested more strictly.

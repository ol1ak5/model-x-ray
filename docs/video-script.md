# Demo video script

The ≤3-minute video for the Devpost submission (#76). Target length: **2:40**.

## The idea

Style: an Apple keynote film. Big type on a plain background, one idea per shot, short sentences, silence and music doing half the work, the product filmed like a hero object. Every number on screen is one the README can back up.

Three things the viewer must remember:

1. **What it is:** an AI agent that checks a financial model the way a financial analyst does.
2. **Why trust it:** Nemotron reasons, a calculation engine does the maths, and every fix is proven on a copy before you see it.
3. **The line:** *Every formula, checked. Every fix, proven.*

Words we never use: "deal", "M&A", "ask a question". The agent does not wait for a question any more: you give it the whole workbook and it checks it on its own.

## Look and sound

- **Type:** Geist, very large, black on white for the problem, white on black for the stakes, the site's green for the answer. One line on screen at a time, cut on the beat.
- **Motion:** slow push-ins on the spreadsheet, a red cell that pulses, numbers that roll like the counters on the landing page, hard cuts on the music.
- **Music:** a minimal pulse that builds (piano or soft synth, ~100 BPM), a full stop of silence before the reveal, then the drop under the product name.
- **Voice:** one calm, confident voice, never rushed. Shorter is better; when in doubt, cut the line and let the screen speak.
- **Screen recording:** 1440x900, browser chrome hidden, cursor enlarged, every click zoomed in. Waits are cut or sped up with a visible timer, never shown in real time.

## Script

### 1. Cold open (0:00 – 0:10)

| Screen | Voice |
|---|---|
| Black. A single spreadsheet cell fades in, centred, with a blinking cursor. | *(silence, one low note)* |
| The cell fills with a number: `285.76`. | Every big financial decision starts in a spreadsheet. |
| Zoom out fast: the cell is one of thousands, tabs multiplying left and right. | And somewhere in it, there is a cell nobody checked. |

### 2. The stakes (0:10 – 0:30)

| Screen | Voice |
|---|---|
| White on black, a counter rolls to **$6,000,000,000**. Under it: *JPMorgan · 2012*. | A broken risk model. Six billion dollars in losses. |
| Counter rolls to **$2,600,000,000**. *Fidelity Magellan · 1995*. | One missing minus sign. A loss reported as a gain. |
| Two quick cuts: *Kodak · $11M*, *TransAlta · $24M*. | |
| All four amounts shrink into one line: **One cell. Real money.** | None of them was fraud. They were spreadsheet errors. |

### 3. Who it is for (0:30 – 0:45)

| Screen | Voice |
|---|---|
| Quick cuts of people at laptops (stock or staged), one title per shot: *Financial analysts*, *FP&A and corporate finance teams*, *M&A and investment banking teams*, *Valuation and deal advisory*, *Auditors*. | We built it for the people who build financial models, review them, and make decisions on what they say. |
| The cuts widen: *Researchers*, *Students*, *Founders*, *Small business owners*, then one big line: **Anyone who works in Excel.** | But it works for anyone whose numbers have to be right: researchers, students, founders, small business owners. If you work in Excel, it works for you. |
| A hand scrolling an endless formula bar: `=SUMPRODUCT(Calc!M51:Calc!AH51, ...)`; function names fly past: `XLOOKUP`, `SUMIFS`, `NPV`, `IRR`, `OFFSET`. Overlay: **50+ Excel functions**. | Thousands of formulas. Dozens of tabs. More than fifty Excel functions it understands. And no time to trace every one by hand. |

### 4. Why AI alone is not enough (0:45 – 0:58)

| Screen | Voice |
|---|---|
| A chat bubble types a confident answer, then the number in it flickers and turns red. | You could ask an AI. It will sound convincing. |
| Text: **Language models reason well.** then **But they guess numbers.** | But language models are built to reason, not to calculate. And a financial model doesn't need a plausible answer. It needs a proven one. |

### 5. The reveal (0:58 – 1:08)

| Screen | Voice |
|---|---|
| Two seconds of black and silence. | |
| The X logo draws itself, then **Model X-Ray** in large type, music drops. | Meet Model X-Ray. |
| Under it, word by word: *Your AI agent for financial model analysis.* | An AI agent that checks your financial model the way a financial analyst does. |

### 6. The demo (1:08 – 1:55) – required

Screen recording of the live site, <https://model-x-ray.vercel.app>.

| Screen | Voice |
|---|---|
| Landing page, cursor clicks **Try the demo**. | Here is a real one. |
| The check page opens: *PPA Model Europe.xlsx*, its five sheets. Overlay: **10 renewable offers · 2,400 formulas**. | A European power purchase agreement model. Ten offers, two thousand four hundred formulas, and errors we planted ourselves. |
| Progress rail, **Read** spins then turns green. | No question needed. It reads every sheet and labels every line. |
| **Investigate** spins. Overlay: *Nemotron 3.5 Super*. | It finds the suspects and works out the cause. |
| **Prove** spins. Overlay: *Tested in a copy*. Timer in the corner speeds from 0:00 to the real run time. | Then it proves the fix: it changes a copy, recalculates the whole workbook, and tries to break its own answer. |
| **Errors detected: 1**. The row opens: *Where*, *Error*, *Solution*, *Explanation*. Zoom on the formula as it is, then the tested formula. | *[read the sentence the page shows, e.g. "Strike price is a typed number"]* The cell. The cause. The fix. The evidence. |
| **Open in the sheet**: the Excel-like dialog, the error cell red, every cell the fix changes in blue. | And every number it touches, so you can see the impact before you accept it. |
| Type in **Ask the agent**: *Could this value be deliberate?* The answer appears in green. | Not sure? Ask it. |
| Click **Approve fix**, then download the corrected copy. Overlay: **Your original file is never touched.** | You decide. It writes a corrected copy, and your original never changes. |

### 7. Built on NVIDIA Nemotron (1:55 – 2:15)

| Screen | Voice |
|---|---|
| Black. Line one in white: **Nemotron reasons.** | Inside, two minds work together. |
| Line two in green: **The engine calculates.** | NVIDIA Nemotron does the thinking. A deterministic calculation engine does the maths. |
| Three model names light up one by one, each with its job: **Nemotron 3 Super** – maps the model · **Nemotron 3.5 Super** – investigates and challenges every fix · **Nemotron 3.5 Lightning** – writes the report. | Nemotron maps the model, judges every suspect, tells a real error from a deliberate choice, and argues against its own fix. |
| Logo line: *Running on Nebius Token Factory*. | All of it running on Nebius Token Factory. |

### 8. The proof (2:15 – 2:30)

| Screen | Voice |
|---|---|
| A big number rolls up: **98%** · *of planted errors fixed*. | Ninety-eight percent of planted errors, fixed. |
| **0** · *false alarms on deliberate values*. | Zero false alarms on values put there on purpose. |
| **14 of 15** · *on models it had never seen*. | Fourteen of fifteen on models it had never seen. |
| **1.5¢ · 85 s** · *to check the demo model*. | For about one and a half cents. |

### 9. Close (2:30 – 2:40)

| Screen | Voice |
|---|---|
| White. The line, in two beats: **Every formula, checked.** / **Every fix, proven.** | Every formula, checked. Every fix, proven. |
| **Model X-Ray** · model-x-ray.vercel.app · github.com/ol1ak5/model-x-ray. Small, at the bottom: *Built with NVIDIA Nemotron on Nebius Token Factory*. | Model X-Ray. |

## Fact check

Every claim above, with its source:

| Claim | Source |
|---|---|
| $6B, $2.6B, $11M, $24M and the four cases | Landing page, `frontend/src/landing/Sections.tsx` |
| PPA model: ten offers, 2,400 formulas, planted errors | README, Try it Live |
| More than fifty Excel functions | README, Supported Excel functions (52 named, plus cross-sheet references, defined names and circular references) |
| 98% fixed (82 of 84), vs 86% for rules alone | README, What Nemotron Adds |
| 0 false alarms on deliberate values (rules alone: 12 of 12) | README, What Nemotron Adds |
| 14 of 15 on held-out Damodaran models | README, Tested on Models It Never Saw |
| 1.5 cents and 85 s for the PPA demo | README, Cost and Time per Check |
| Roles of the three Nemotron models | README, How Nemotron and Token Factory Power It |
| Original never changes, fix tested in a copy | README, How it Works (`test`, `apply_fix`) |

## Before recording

- The agent fixes one error per run, so the demo shows one row under *Errors detected*. Do not say "it found all three".
- Read the error sentence and the cell from the run you recorded, and put them into the voice line of section 6.
- Record the run end to end once and keep it; cut it to ~45 seconds in the edit.

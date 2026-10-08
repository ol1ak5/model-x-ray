---
name: testing
description: How to write tests in this repo — deep end-to-end tests only, no unitary tests, fake LLM/sandbox patterns, fixtures, and opt-in live tests
---

# Testing

## The rule (AGENTS.md)

**No unitary tests — only deep, useful tests.** A test must prove the system works on realistic data. If it doesn't exercise real behavior end to end (a whole formula trace, a full audit run, a benchmark scenario against a planted error), don't write it. Isolated functions with mocked inputs are explicitly unwanted.

Also: TDD — write the failing test first, then implement. Modern types only. No inline comments (explain decisions in `docs/`).

## How to be deep without being slow

"Deep" means realistic inputs and real orchestration, not live APIs. Layered pattern that stays fast:

1. **Fixture spreadsheets, real parsers** — fixture builders live in `tests/conftest.py` (`write_demo_workbook`, `demo_workbook_path`, `demo_workbook_with_override_note`: a small P&L with formulas, labels, one planted typed value, optional cell notes). Feed them through the *real* formula parser, dependency graph, contribution math. Never mock the code under test.
2. **Fake LLM, real graph** — scripted `ChatModel` stub that returns predetermined tool calls / verdicts in sequence (`ScriptedDiagnosis`, `OutlierScanner`, `AlwaysCallsATool` in `tests/test_investigator.py`). Runs the *actual* LangGraph with interrupts, reducers, conditional edges, retry loop. Assert on state fields (`hypotheses`, `verifications`, `evidence`), not on message text.
3. **Real patch logic** — patch a fixture copy with `Workbook.with_patch` and read the recalculated values from the engine, so before/after values are real numbers (the Google sandbox, issue #6, will do the same on a Sheet copy).

```python
def test_blended_error_symptom_is_not_cause(fixture_sheet: Workbook, scripted_llm: ChatModel) -> None:
    graph = run_investigation(scripted_llm, "blend-03", fixture_source)
    config = {"configurable": {"thread_id": "blend-03"}}
    graph.invoke({"spreadsheet_id": "blend-03", "question": "Why did EBITDA 2027 jump?"}, config)
    result = graph.get_state(config).values
    planted = load_ground_truth("blend-03")
    assert top_hypothesis(result).cell == planted.cells[0]
    assert top_hypothesis(result).error_type == planted.error_types[0]
```

That one test covers: parser → graph → tool loop → hypothesis merge → routing → report. This is the shape tests should have.

## What good acceptance looks like here

- Full paths: `diagnose → test → verify → diagnose (retry) → explain`, and the exhausted → inconclusive path.
- Interrupt/resume: run to `human_review` with `InMemorySaver`, assert payload, resume with `Command(resume=...)`, assert the tail ran.
- Determinism: contributions sum to observed change within tolerance; `merge_by_id` never duplicates under Verifier updates.
- Ground truth from planted-error JSON (issue #12), not hand-written expectations.
- Four-way comparison stays configuration (the graph takes its models as parameters) — a test that swaps the Investigator model proves that.

## Live tests

Google API and Token Factory tests are **opt-in**: mark `@pytest.mark.live`, register a `live` marker that skips by default. Unit/deep tests never touch the network — this is also what keeps `uv run pytest` usable offline.

## Commands

Exactly as in AGENTS.md §Commands:

```sh
uv run pytest                                  # offline, no credits
uv run pytest path::test_name -k <pattern>     # single test, filtered
uv run pytest -m live                          # opt-in network tests (spend credits)
```

# AGENTS.md

## Project

Model X-Ray ("the debugger for financial models"): an evidence-first Nemotron agent that investigates surprising outputs in financial models. It locates the cell behind a question such as "Why did EBITDA jump?", traces the dependency graph, diagnoses the root cause, tests a fix in a sandbox copy, verifies it (looping back if verification fails), explains it with clickable evidence, and returns a corrected copy after human approval. The design is in `docs/agent-architecture.md`; read it before changing the agent. Roadmap: issue #2.

- Target users: M&A / deal teams. Built for the Nebius x NVIDIA Global AI Hackathon (Devpost, deadline 30 Oct 2026 10:00 PDT).
- Spreadsheet platform: **Google Sheets first**, behind a `SpreadsheetSource` / `Sandbox` interface so `.xlsx` can follow as a stretch goal (#13). One good model plus many copies with planted errors is the data strategy; no external data needed.
- Proof of value: plant ~50 known errors in generated models and measure detection accuracy. Numbers are the centerpiece of the demo.
- Agent must not be "naked": it gets tools (dependency graph traversal, formula trace, checklist validation) and skills built from financial-modeling best-practice literature. Per-model checklist of things to verify; the agent reads source material and writes its own context notes per workflow.
- Optional leverage: Tavily for real-world lookups (there is a "Best Use of Tavily" prize).

## Hackathon constraints (change the definition of "done")

- Must run on Nebius Token Factory or Nebius AI Cloud and use at least one NVIDIA open-source model (Nemotron). Judges score Token Factory / Nemotron usage, design completeness, real-problem fit, idea quality.
- Submission needs: working demo URL, public GitHub repo with an open-source license and a README with setup instructions that highlights Nebius/NVIDIA usage, ≤3-minute YouTube demo video, project description on Devpost.
- Track: likely "Best Apps and Agents". Read https://nebiusglobalaihackathon.devpost.com/ before finalizing scope.
- Token Factory is OpenAI-compatible: `base_url=https://api.tokenfactory.us-central1.nebius.com/v1/`, key in `NEBIUS_API_KEY` (`.env`, never committed). Nemotron model IDs and credit details are in the feasibility brief (see below); confirm current IDs in the Token Factory console before hardcoding them.

## Verified repo state

No code exists yet. Do not assume tooling that is not there:

- Committed on `main`: `README.md` (empty), `AGENTS.md`, `.gitignore`, `docs/agent-architecture.md`, `docs/evaluation.md`, plus a bare `pyproject.toml` / `.python-version` uv scaffold (Python 3.13.2, zero dependencies).
- No package, dependencies, test runner, linter, formatter, typechecker, CI, pre-commit, or `opencode.json`. The scaffold's console script `data-room-sentinel = "data_room_sentinel:main"` points at a module that does not exist (`src/` is empty) — the real Python project is created by the Nemotron tool-calling spike (#4), which should rename it (the repo is now `model-x-ray`). When you add tooling, commit the config and update the Commands section here with the exact invocation.
- `docs/feasibility.html` (the prior leak-tracing direction) was deleted from the working tree; it remains readable via git history (`git show <commit>:docs/feasibility.html`) and still holds verified Nebius credits, model IDs, and the four-week plan to 30 Oct. Deleted or uncommitted files in the working tree are someone's in-progress work: never `git add -A` or discard them.

## Commands

- Dependencies: `uv add <pkg>` (dev: `uv add --dev <pkg>`). Never `pip` or `uv pip`.
- Run: `uv run <script>` / `uv run python -m ...`.
- Tests (once pytest is added): `uv run pytest`, single test `uv run pytest path::test_name -k <pattern>`.
- `scripts/*.sh` are zero-flag wrappers that call `uv run x.py` with fixed, curated flags (e.g. `scripts/benchmark.sh` → `uv run tools/benchmark.py --models planted-50 --output docs/benchmark.md`). They must run from the repo root with no arguments.

## Code rules (these differ from Python defaults, so they matter)

- Modern types only: `dict`, `list`, `X | None` — never `Dict`, `List`, `Optional`, `Tuple`.
- **No inline comments anywhere** (no `#` comments on code lines, no trailing comments). Explain decisions in `docs/*.md` instead.
- Test-driven development: write the failing test first, then implement. Every behavior change ships with tests.
- Each change = one commit, staged with explicit `git add <paths>` (never `-A`), message format `type(scope): summary`, e.g. `feat(engine): implemented formula trace parser`. Scopes in use: `engine` (LLM API/clients), `agent` (audit workflow, tools, skills), `research`, `benchmark`, `docs`, `scripts`.
- Follow the original design documented in `docs/`; when code and docs disagree, fix both in the same change.
- `docs/` holds `.md` files for design and implementation details. New subsystem → new doc before or with the code.

## Multi-agent / multi-person workflow

Work is issue-driven and expected to be executed by agents as much as people.

- **Branches and PRs**: never commit to `main` directly. Create `feat/<issue-number>-<slug>`, `fix/...`, `research/...`, `bench/...` branches; open a PR referencing the issue (`Closes #123`); get review before merge. One issue per PR when possible.
- **Issue labels**: `research`, `agent`, `engine`, `benchmark`, `docs`, plus `bug`, `chore`, `blocked`. Add more as needed, but keep this set stable — agents filter on it.
- **Standardized issue format** (contract between agents): title `[label] one-line goal`, body with context, concrete acceptance criteria (checkable), links to related issues/contracts, and a final "Follow-ups" section. An issue without acceptance criteria is not ready to be worked.
- **Lifecycle rules**:
  - Every `research` issue MUST spawn, as part of its output, at least one `benchmark` issue (does the idea actually work?) and one `agent`/`engine`/`docs` issue (build it if the benchmark passes).
  - Every solved issue MUST leave behind new issues for what it could not finish, what it unblocked, and what it found broken. Closing an issue with zero follow-ups is suspicious unless it is trivial.
  - The roadmap lives in GitHub Issues, not in prose docs: epics link to children; keep one open "roadmap" issue per milestone updated as things move.
- PR descriptions state which issue they close, how it was tested, and which follow-ups were filed.

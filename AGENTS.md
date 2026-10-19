# AGENTS.md

## Project

Model X-Ray ("the debugger for financial models"): an evidence-first Nemotron agent that investigates surprising outputs in financial models. It locates the cell behind a question such as "Why did EBITDA jump?", traces the dependency graph, diagnoses the root cause, tests a fix in a sandbox copy, verifies it (looping back if verification fails), explains it with clickable evidence, and returns a corrected copy after human approval. The design is in `docs/agent-architecture.md`; read it before changing the agent. Roadmap: issue #2.

- Target users: M&A / deal teams. Built for the Nebius x NVIDIA Global AI Hackathon (Devpost, deadline 30 Oct 2026 10:00 PDT).
- Spreadsheet platform: **Google Sheets first**, behind a `SpreadsheetSource` / `Sandbox` interface so `.xlsx` can follow as a stretch goal (#13). One good model plus many copies with planted errors is the data strategy; no external data needed.
- Proof of value: plant ~50 known errors in generated models and measure detection accuracy. Numbers are the centerpiece of the demo.
- Agent must not be "naked": it gets tools (dependency graph traversal, formula trace, checklist validation) and skills built from financial-modeling best-practice literature. Per-model checklist of things to verify; the agent reads source material and writes its own context notes per workflow.
- Optional leverage: Tavily for real-world lookups (there is a "Best Use of Tavily" prize).

## Development agent vs product agent (keep them separate)

- Everything addressed by this file, by `.opencode/skills/`, and by the `docs/` design docs is for the **development agents building** Model X-Ray.
- The **product agent** (the LangGraph/Nemotron investigation graph) must never read any of it. Its prompts, checklists and domain notes live inside the package (`src/model_x_ray/prompts/`) and ship with the product.
- Product prompt text never goes into `.opencode/skills/`; development conventions never go into product prompts. If something seems useful to both, keep two copies, one in each home.

## Hackathon constraints (change the definition of "done")

- Must run on Nebius Token Factory or Nebius AI Cloud and use at least one NVIDIA open-source model (Nemotron). Judges score Token Factory / Nemotron usage, design completeness, real-problem fit, idea quality.
- Submission needs: working demo URL, public GitHub repo with an open-source license and a README with setup instructions that highlights Nebius/NVIDIA usage, ≤3-minute YouTube demo video, project description on Devpost.
- Track: likely "Best Apps and Agents". Read https://nebiusglobalaihackathon.devpost.com/ before finalizing scope.
- Token Factory is OpenAI-compatible: `base_url=https://api.tokenfactory.nebius.com/v1/` (verified 6 Oct 2026; the regional `us-central1` URL lists fewer models), key in `NEBIUS_API_KEY` (`.env`, never committed). Verified model IDs, context and prices are in `docs/agent-architecture.md` §Models; IDs are case-sensitive, so re-check `GET /v1/models` before hardcoding a new one.

## Verified repo state

Verified 8 Oct 2026. Do not assume tooling that is not there — re-check the tree when it matters:

- uv project `model-x-ray` (Python 3.13.2, build backend `uv_build`), package in `src/model_x_ray/`, `uv.lock` committed.
- Product code: `state.py` (`InvestigationState`, `merge_by_id` / `merge_verifications` reducers), `graph.py` / `nodes.py` / `routing.py` (main graph, stub nodes, bounded retry loop, human-in-the-loop), `llm.py` (role registry `ROLE_MODELS` + `build_chat_model` against Token Factory with clear env errors, timeouts and retries, `invoke_with_usage` recording tokens and latency into `state.run_log`; `NEBIUS_BASE_URL` + `NEBIUS_API_KEY`), `memory.py` (SQLite checkpointer), `agents/investigator.py` (tool-budgeted Investigator subgraph with structured diagnosis), `agents/verifier.py` (deterministic checks, fixed evidence package, structured `Verdict`), `prompts/` (`load_prompt` reads the product-agent `.md` files).
- The console script `model-x-ray` still only prints a banner. The graph has no default `diagnose` node: `run_investigation(llm, spreadsheet_id, source, sandbox, verifier=None)` wires the Investigator (with the real read-only tools built from the loaded workbook), the real `trace` node (causal contributions plus evidence records), the real `test` node (sandbox before/after values), the real `verify` node (deterministic checks, then the adversarial Verifier agent), the real `explain` node (validated narrative report from the wired explainer with the deterministic evidence-citing report as fallback, or honest inconclusive), and the real `apply_fix` node (writes the corrected copy through the sandbox after approval) as an entrypoint, and `build_graph(checkpointer, diagnose=...)` requires an explicit choice — the fabricating test stub is `nodes.stub_diagnose`.
- `tools/` holds `measure_tool_calling.py` and `benchmark.py`, wrapped by `scripts/measure_tool_calling.sh` and `scripts/benchmark.sh`.
- Benchmark: `src/model_x_ray/benchmark/` has the per-step evaluators, the rules-only diagnose baseline (`rules.py`), Wilson intervals and the four-set-up runner; `docs/evaluation.md` defines the metrics, `docs/benchmark-results.json` is its raw output.
- Dependencies: `langgraph`, `langchain-openai`, `langgraph-checkpoint-sqlite`, `openpyxl`, `python-dotenv`, `google-api-python-client` (Google Sandbox, imported lazily); dev: `pytest`. `.env.example` lists every variable with empty or default values.
- pytest is configured in `pyproject.toml`: tests live in `tests/`, and tests marked `live` (they call Token Factory or Google APIs and spend credits) are skipped unless requested with `-m live`.
- No linter, formatter, typechecker, CI, pre-commit, or `opencode.json` yet. When you add tooling, commit the config and update the Commands section here with the exact invocation.
- `docs/feasibility.html` (the prior leak-tracing direction) was deleted from the working tree; it remains readable via git history (`git show <commit>:docs/feasibility.html`) and still holds verified Nebius credits, model IDs, and the four-week plan to 30 Oct. Deleted or uncommitted files in the working tree are someone's in-progress work: never `git add -A` or discard them.

## GitHub access: use `gh`, never touch `~/.ssh`

- For anything GitHub auth related, use `gh` (already authenticated; `gh` also provides the git credential helper over HTTPS). `gh pr ...`, `gh issue ...`, `gh api ...`.
- **Never list, read, test, or reference files in `~/.ssh/`** — private keys are the user's territory, off limits to agents. No `ls ~/.ssh`, no `ssh -i`, no diagnosing which key works.
- If a git push/pull fails with an auth error: do not debug keys. Retry via `gh`-backed HTTPS (`git push https://github.com/<owner>/<repo>.git <branch>`) or tell the user to run `gh auth status` / `gh auth login`. The user has instructed: use `gh`, always.

## Commands

- Dependencies: `uv add <pkg>` (dev: `uv add --dev <pkg>`). Never `pip` or `uv pip`.
- Run: `uv run <script>` / `uv run python -m ...`.
- Setup after cloning: `uv sync`, then `cp .env.example .env` and fill in your own keys.
- Tests: `uv run pytest` (offline, no credits), single test `uv run pytest path::test_name -k <pattern>`, live tests `uv run pytest -m live`.
- Smoke check: `uv run model-x-ray`.
- Frontend: `scripts/dev.sh` runs the API and the Vite dev server together (http://localhost:8000 + http://localhost:5173, bun install and bun run when bun is present, npm otherwise); frontend tests: `npm --prefix frontend test` or `cd frontend && bun run test`. The frontend uses bun/npm, not uv.
- Run the API locally: `uv run tools/generate_dataset.py --output models --per-set 2` once, then `scripts/serve.sh` (http://localhost:8000/docs).
- Re-record the demo stories against a running API: `uv run tools/export_demo_run.py --review <id> --done <id>` (reads `GET /investigations/{id}` and `/sheet`, writes `frontend/src/test/recorded/*.json`, spends no credits).
- Graph picture: `scripts/export_graph.sh` (writes `docs/investigation-graph.mmd` and `.png`; re-run after any change to nodes or edges — a test fails if the committed diagram is stale).
- Tool-calling measurement (live, about 3 cents): `scripts/measure_tool_calling.sh`.
- Benchmark: `uv run tools/benchmark.py --setups rules` (offline, free, generates the dataset if missing) or `scripts/benchmark.sh` (all four set-ups; the LLM ones spend Token Factory credits; writes `docs/benchmark-results.json`).
- `scripts/*.sh` are zero-flag wrappers that call `uv run x.py` with fixed, curated flags; they must run from the repo root with no arguments. The ones that exist today are `scripts/measure_tool_calling.sh`, `scripts/export_graph.sh` and `scripts/benchmark.sh`.

## Code rules (these differ from Python defaults, so they matter)

- Modern types only: `dict`, `list`, `X | None` — never `Dict`, `List`, `Optional`, `Tuple`.
- **No inline comments anywhere** (no `#` comments on code lines, no trailing comments). Explain decisions in `docs/*.md` instead.
- Test-driven development: write the failing test first, then implement. Every behavior change ships with tests.
- **No unitary tests** — only deep, useful tests. Test real behavior end to end (a whole formula trace, a full audit run, a benchmark scenario against a planted error), not isolated functions with mocked inputs. If a test doesn't prove the system actually works on realistic data, don't write it.
- Each change = one commit, staged with explicit `git add <paths>` (never `-A`), message format `type(scope): summary`, e.g. `feat(engine): implemented formula trace parser`. Scopes in use: `engine` (LLM API/clients), `agent` (audit workflow, tools, skills), `research`, `benchmark`, `docs`, `scripts`.
- Follow the original design documented in `docs/`; when code and docs disagree, fix both in the same change.
- `docs/` holds `.md` files for design and implementation details. New subsystem → new doc before or with the code.

## Multi-agent / multi-person workflow

Work is issue-driven and expected to be executed by agents as much as people.

- **Branches and PRs**: never commit to `main` directly. Create `feat/<issue-number>-<slug>`, `fix/...`, `research/...`, `bench/...` branches; open a PR referencing the issue (`Closes #123`); get review before merge. One issue per PR when possible.
- **Delete branches after merge** — a branch exists only to carry one PR. Once merged: `gh pr merge <n> --merge --delete-branch`, or manually `git branch -d <branch>` and `git push origin --delete <branch>`. Never reuse a merged branch for new work; open a fresh one. Keep the repo at `main` plus at most the branches with open PRs.
- **Issue labels**: `research`, `agent`, `engine`, `benchmark`, `docs`, plus `bug`, `chore`, `blocked`. Add more as needed, but keep this set stable — agents filter on it.
- **Standardized issue format** (contract between agents): title `[label] one-line goal`, body with context, concrete acceptance criteria (checkable), links to related issues/contracts, and a final "Follow-ups" section. An issue without acceptance criteria is not ready to be worked.
- **Lifecycle rules**:
  - Every `research` issue MUST spawn, as part of its output, at least one `benchmark` issue (does the idea actually work?) and one `agent`/`engine`/`docs` issue (build it if the benchmark passes).
  - Every solved issue MUST leave behind new issues for what it could not finish, what it unblocked, and what it found broken. Closing an issue with zero follow-ups is suspicious unless it is trivial.
  - The roadmap lives in GitHub Issues, not in prose docs: epics link to children; keep one open "roadmap" issue per milestone updated as things move.
- PR descriptions state which issue they close, how it was tested, and which follow-ups were filed.

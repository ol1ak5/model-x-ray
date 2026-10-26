# AGENTS.md

## Project

Model X-Ray ("the debugger for financial models"): an evidence-first Nemotron agent that investigates surprising outputs in financial models. It locates the cell behind a question such as "Why did EBITDA jump?", traces the dependency graph, diagnoses the root cause, tests a fix in a sandbox copy, verifies it (looping back if verification fails), explains it with clickable evidence, and returns a corrected copy after human approval. The design is in `docs/agent-architecture.md`; read it before changing the agent. Roadmap: issue #2.

- Target users: M&A / deal teams. Built for the Nebius x NVIDIA Global AI Hackathon (Devpost, deadline 30 Oct 2026 10:00 PDT).
- Spreadsheet platform: `.xlsx` today — the API, the sandbox, the demo models and every test run on it. Google Sheets sits behind the same `SpreadsheetSource` / `Sandbox` interface (`GoogleSandbox`, exercised only against fake services) and is not wired into the server yet (#13); do not claim it works.
- Proof of value: planted errors, measured per step. The generated Damodaran set carries 75 of them (frozen splits in `docs/damodaran-split.json`) and the Enron Errors Corpus adds real-world ones (`docs/enron-split.json`). Numbers are the centerpiece of the demo.
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

Verified 21 Oct 2026. Do not assume tooling that is not there — re-check the tree when it matters:

- uv project `model-x-ray` (Python 3.13.2, build backend `uv_build`), package in `src/model_x_ray/`, `uv.lock` committed.
- Server: `api.py` (FastAPI, twelve routes: health, spreadsheet list and upload, investigation create/read/resume plus their `/stream` variants, questions about a finding (`/ask`, answered by `agents/ask.py`), the whole workbook for the page's sheet viewer, the sheet window and the corrected copy; the run state travels in the browser, an upload lives only until its run ends or its TTL passes and is then deleted from disk and from the source — `api.Uploads`), `server.py` (`app_from_env`; every setting is read there from `.env`; with `VERCEL` set, every writable path defaults to the temp folder). The stream endpoints also take the visitor's `.xlsx` in the request and the final view carries the sheet window and the corrected file, so no state waits on the server between requests (`docs/api.md`, "Requests that carry the model").
- Deployment: one Vercel project (`app.py` entrypoint at the root, `vercel.json` builds the frontend and serves it from the same origin); the owner's one-time steps are in `docs/deployment.md`.
- Graph: `graph.py` / `routing.py` (ten nodes — load_sheet, map_model, locate, trace, diagnose, test, verify, explain, human_review, apply_fix — with a bounded retry loop and the human-in-the-loop pause), `nodes.py` (the real nodes, the deterministic reports, the prose guard for the writer), `state.py` (`InvestigationState`, `merge_by_id` / `merge_verifications`), `llm.py` (`ROLE_MODELS`: investigator and verifier on `NVIDIA Nemotron 3.5 Super`, mapper and locate on 3 Super (3.5 Super burns its output budget mapping a 436-line DCF), explain on Lightning; `provider_error` retries the `[ERROR: ...]` answers Token Factory returns with HTTP 200 and raises `ProviderFailure`; `NEBIUS_BASE_URL` + `NEBIUS_API_KEY`; `invoke_with_usage`), `memory.py` (SQLite checkpointer and store), `causal.py` (causal tree and contributions), `rules.py` (row and column patterns, incomplete totals, double counts, typed values, table scan), `tools.py` (the read-only tools the Investigator sees).
- Agents: `agents/locator.py` (code first, Nemotron only when ambiguous; table mode and the whole-model check), `agents/mapper.py` (model map), `agents/investigator.py` (tool-budgeted subgraph, structured diagnosis, per-candidate judgement, the logic review in words, and three votes with a majority rule when no rule flagged a cell), `agents/verifier.py` (three deterministic checks with their human labels in `CHECK_LABELS`, whole-line patches judged as `line logic error`, then the adversarial Verifier), `prompts/` (`load_prompt` reads the product-agent `.md` files).
- Spreadsheet core: `spreadsheet/engine.py` (parser, evaluation, dependency graph, iterative calculation for circular references, `OFFSET`, Excel error semantics), `spreadsheet/xlsx.py` (loader), `spreadsheet/source.py` (`XlsxSource`, `add` / `remove`), `spreadsheet/sandbox.py` (`XlsxSandbox` writes copies; `GoogleSandbox` exists but no server path uses it).
- Written but not wired: `structure.py` (model profile — typed blocks per sheet, `profile` / `describe`) is imported only by `tests/test_structure.py` and drives nothing (#170). `finance.py` (reference formulas, rendered into `docs/financial-formulas.md` by `tools/export_formulas.py`) is no longer test-only: the logic brief states each line's standard definition through `standard_definition` in `agents/investigator.py`; the rest of the wiring stays as #141 B step 5.
- Data: `dataset.py` (clean base plus planted variants), `demo_model.py` (the NVIDIA pair in `demo/`), `benchmark/` (per-step evaluators, rules-only diagnose baseline, Wilson intervals, five set-ups `rules` / `nano` / `super` / `super-3` / `no-tools`, the logic sets in `benchmark/logic_sets.py`, planting, Enron reader, report renderer).
- Demo models: the API serves `demo_models/demo.xlsx` by default (three-sheet deal model: `P&L!G5` has the sign flip and `P&L!I6` a typed value), and that is the model the frontend fixtures and the demo tests use; `demo/nvidia-pnl.xlsx` and `demo/nvidia-pnl-error.xlsx` are the NVIDIA pair, and `demo/simple-errors` and `demo/saas-errors` are the logic sets (one planted error per file, plus a clean copy) the README's model comparison was measured on, reachable with `MODEL_X_RAY_MODELS_DIR=demo`.
- The console script `model-x-ray` still only prints a banner. `run_investigation(...)` wires the real nodes, `build_graph(checkpointer, diagnose=...)` requires an explicit choice, and the fabricating test stub is `nodes.stub_diagnose`.
- Tests: `uv run pytest` is 231 offline tests; 26 marked `live` call Token Factory or Google APIs and are skipped by default. The frontend has 20 Vitest tests, and `tsc -b` plus `vite build` are clean.
- `tools/`: `benchmark.py`, `damodaran_benchmark.py`, `enron_benchmark.py`, `export_demo_run.py`, `export_formulas.py`, `export_graph.py`, `generate_dataset.py`, `generate_demo_model.py`, `generate_logic_sets.py`, `measure_tool_calling.py`, `screenshots.py`, `trace_run.py`.
- `scripts/`: `dev.sh`, `serve.sh`, `benchmark.sh`, `export_graph.sh`, `measure_tool_calling.sh`, `screenshots.sh`.
- Benchmark outputs are generated, never committed: `tools/benchmark.py` writes `docs/benchmark-results.json`, `docs/benchmark.md` and `docs/benchmark.svg`, which stay untracked in the working tree after a run; the only committed run is `docs/benchmark-before101.*`. The splits are frozen in `docs/damodaran-split.json` and `docs/enron-split.json`.
- Dependencies: `fastapi`, `uvicorn`, `langgraph`, `langchain-openai`, `langgraph-checkpoint-sqlite`, `openpyxl`, `python-dotenv`, `google-api-python-client` (imported lazily); dev: `pytest`, `httpx`. `.env.example` lists every variable with empty or default values.
- pytest is configured in `pyproject.toml`: tests live in `tests/`, and tests marked `live` are skipped unless requested with `-m live`.
- No linter, formatter, typechecker, CI, pre-commit or `opencode.json`. The only layout check is `scripts/screenshots.sh`: headless Chromium over the recorded story at 1280x800 and 1440x900. When you add tooling, commit the config and update the Commands section here.
- Docs: `docs/agent-architecture.md` (design and models), `api.md`, `deployment.md`, `evaluation.md`, `frontend.md`, `persistence.md`, `spreadsheet-core.md`, `financial-formulas.md`, `benchmark-before101.md`, the graph picture and the splits. Missing: a doc for the model profile and table mode (#161), the video and Devpost text (#76).
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
- Run the deployed setup locally (page and API on one origin): `npm --prefix frontend run build`, then `VERCEL=1 uv run uvicorn app:app --port 8000`.
- Run the API locally: `scripts/serve.sh` (http://localhost:8000/docs) serves `demo_models/` by default; for the benchmark set run `uv run tools/generate_dataset.py --output models --per-set 2` once and point `MODEL_X_RAY_MODELS_DIR` at `models/`. `scripts/dev.sh` starts this API and the Vite app together.
- Re-record the demo stories against a running API: `uv run tools/export_demo_run.py --review <id> --done <id>` (reads `GET /investigations/{id}` and `/sheet`, writes `frontend/src/test/recorded/*.json`, spends no credits).
- Graph picture: `scripts/export_graph.sh` (writes `docs/investigation-graph.mmd` and `.png`; re-run after any change to nodes or edges — a test fails if the committed diagram is stale).
- Logic sets (a simple budget and a SaaS forecast, one planted error per file plus a clean copy, in `demo/simple-errors` and `demo/saas-errors`): `uv run tools/generate_logic_sets.py`; a test fails if the committed files drift from the generator.
- Trace one run step by step (target, logic brief, every vote, decisions, verifications, report): `uv run tools/trace_run.py <model.xlsx>` (free, rules baseline) or `--setup super` (live, about 4 cents for a small model).
- Layout check: `scripts/screenshots.sh` renders the recorded story through headless Chromium at 1280x800 and 1440x900 into `/tmp/model-x-ray-screenshots`; it needs the dev app running and spends nothing.
- Tool-calling measurement (live, about 3 cents): `scripts/measure_tool_calling.sh`.
- Benchmark: `uv run tools/benchmark.py --setups rules` (offline, free, generates the dataset if missing) or `scripts/benchmark.sh` (all four set-ups, six workers; the LLM ones spend Token Factory credits; writes `docs/benchmark-results.json`, `docs/benchmark.md` and `docs/benchmark.svg`, which are generated and not committed; `--render-only` re-renders from an existing results file). `tools/damodaran_benchmark.py` and `tools/enron_benchmark.py` run the frozen splits.
- `scripts/*.sh` are zero-flag wrappers that call `uv run x.py` (or start the two dev servers) with fixed, curated flags; they must run from the repo root with no arguments. The ones that exist today are `dev.sh`, `serve.sh`, `benchmark.sh`, `export_graph.sh`, `measure_tool_calling.sh` and `screenshots.sh`.

## Code rules (these differ from Python defaults, so they matter)

- Modern types only: `dict`, `list`, `X | None` — never `Dict`, `List`, `Optional`, `Tuple`.
- **No inline comments anywhere** (no `#` comments on code lines, no trailing comments). Explain decisions in `docs/*.md` instead.
- Test-driven development: write the failing test first, then implement. Every behavior change ships with tests.
- **No unitary tests** — only deep, useful tests. Test real behavior end to end (a whole formula trace, a full audit run, a benchmark scenario against a planted error), not isolated functions with mocked inputs. If a test doesn't prove the system actually works on realistic data, don't write it.
- Each change = one commit, staged with explicit `git add <paths>` (never `-A`), message format `type(scope): summary`, e.g. `feat(engine): implemented formula trace parser`. Scopes in use: `engine` (spreadsheet core and the LLM clients), `agent` (graph, nodes, tools, agents, prompts), `api` (FastAPI surface), `frontend` (React app), `benchmark`, `docs`, `scripts`.
- Follow the original design documented in `docs/`; when code and docs disagree, fix both in the same change.
- `docs/` holds `.md` files for design and implementation details. New subsystem → new doc before or with the code.

## Multi-agent / multi-person workflow

Work is issue-driven and expected to be executed by agents as much as people.

- **Branches and PRs**: never commit to `main` directly. Create `feat/<issue-number>-<slug>`, `fix/...`, `research/...`, `bench/...` branches; open a PR referencing the issue (`Closes #123`); get review before merge. One issue per PR when possible.
- **A merge is a decision, not a click.** On 20 Oct #169 was merged while its author was still pushing to it, and a day of work (#181) was left outside `main`. To keep that from happening again:
  - Open a PR as a **draft** while you are still working on it (`gh pr create --draft`), and mark it ready only when it is finished (`gh pr ready <n>`). Merge only PRs marked ready.
  - The reviewer merges only after leaving a review comment that says, in a few lines, what they checked (the tests they ran, the numbers they looked at, what they did not check). Approving without reading is not a review.
  - Before every push, an agent or a person checks that the branch's PR is still open: `gh pr view --json state -q .state`. Once it is `MERGED`, the branch is closed: new commits go to a fresh branch and a new PR.
  - Keep PRs small: one coherent change, opened as soon as it is done, instead of one PR that keeps growing for a day.
- **Delete branches after merge** — a branch exists only to carry one PR. Once merged: `gh pr merge <n> --merge --delete-branch`, or manually `git branch -d <branch>` and `git push origin --delete <branch>`. Never reuse a merged branch for new work; open a fresh one. Keep the repo at `main` plus at most the branches with open PRs.
- **Issue labels**: `research`, `agent`, `engine`, `benchmark`, `frontend`, `docs`, `roadmap`, plus `bug`, `chore`, `blocked`. Add more as needed, but keep this set stable — agents filter on it.
- **Standardized issue format** (contract between agents): title `[label] one-line goal`, body with context, concrete acceptance criteria (checkable), links to related issues/contracts, and a final "Follow-ups" section. An issue without acceptance criteria is not ready to be worked.
- **Lifecycle rules**:
  - Every `research` issue MUST spawn, as part of its output, at least one `benchmark` issue (does the idea actually work?) and one `agent`/`engine`/`docs` issue (build it if the benchmark passes).
  - Every solved issue MUST leave behind new issues for what it could not finish, what it unblocked, and what it found broken. Closing an issue with zero follow-ups is suspicious unless it is trivial.
  - The roadmap lives in GitHub Issues, not in prose docs: epics link to children; keep one open "roadmap" issue per milestone updated as things move.
- PR descriptions state which issue they close, how it was tested, and which follow-ups were filed.

---
name: uv
description: Python project and dependency management with uv — adding packages, running scripts, and locking
---

# uv

`uv` is the only package manager allowed in this repo. Never use `pip`, `python -m pip`, or `uv pip` (AGENTS.md rule).

## Commands

```sh
uv add <pkg>                    # add runtime dependency (writes pyproject + uv.lock)
uv add --dev <pkg>              # add dev dependency (pytest is the current one)
uv remove <pkg>
uv run python -m <pkg>          # run a module
uv run <script>.py              # run a file
uv run pytest                   # run the dev dependencies (tests)
uv sync                         # install exactly what uv.lock pins
uv lock                         # re-resolve the lockfile after manual edits
uvx <tool>                      # run a tool ephemerally without adding it
```

## Facts verified locally (2026-10-08)

- uv 0.12.10, Python pinned to 3.13.2 via `.python-version`
- The console script works: `uv run model-x-ray` prints the banner (its `main()` is still a placeholder — that is a product gap, not a tooling one)
- `uv run pytest` collects and runs the suite; `-m live` opts into network tests
- `uv run --with <pkg>` resolves extra packages without touching `pyproject.toml`

There is no known broken scaffold: the package is `model-x-ray` in `src/model_x_ray/`, and every `uv run` path above works from the repo root. If a `uv run` fails, debug it — do not reach for `--no-project` isolation.

## Lockfile

- Commit `uv.lock` whenever dependencies change; it is part of the same commit as the `pyproject.toml` edit.
- Prefer `uv add` over editing `pyproject.toml` by hand so the lock stays consistent.

## Reading project metadata

```sh
uv tree                         # dependency tree
uv run python -c "import importlib.metadata as m; print(m.version('langgraph'))"
```

Runtime version checks beat guessing from docs: libraries move symbols between minors (see the `langgraph` skill).

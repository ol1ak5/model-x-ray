---
name: uv
description: Python project and dependency management with uv — adding packages, running scripts, locking, and workarounds for this repo's broken scaffold
---

# uv

`uv` is the only package manager allowed in this repo. Never use `pip`, `python -m pip`, or `uv pip` (AGENTS.md rule).

## Commands

```sh
uv add <pkg>                    # add runtime dependency (writes pyproject + uv.lock)
uv add --dev <pkg>              # add dev dependency (pytest, ruff, mypy...)
uv remove <pkg>
uv run python -m <pkg>          # run a module
uv run <script>.py              # run a file
uv run pytest                   # run a tool installed as a dev dependency
uv sync                         # install exactly what uv.lock pins
uv lock                         # re-resolve the lockfile after manual edits
uvx <tool>                      # run a tool ephemerally without adding it
```

## This repo's current breakage (important)

`pyproject.toml` declares `[project.scripts] data-room-sentinel = "data_room_sentinel:main"` but `src/data_room_sentinel/` no longer exists, so **any `uv run` in this repo fails** with:

```
× Failed to build `data-room-sentinel`
  ╰─▶ Expected a Python module at: src/data_room_sentinel/__init__.py
```

Until issue #4 replaces the scaffold, run one-off code isolated from the project:

```sh
uv run --no-project --with langgraph --with langchain-openai python -c "..."
uvx ruff check
```

Do not "fix" this as a side effect of an unrelated change — renaming the package and console script belongs to #4.

## Facts verified locally (2026-10-06)

- uv 0.12.10, Python pinned to 3.13.2 via `.python-version`
- `uv run --with <pkg>` resolves extra packages without touching `pyproject.toml`

## Lockfile

- Commit `uv.lock` whenever dependencies change; it is part of the same commit as the `pyproject.toml` edit.
- Prefer `uv add` over editing `pyproject.toml` by hand so the lock stays consistent.

## Reading project metadata

```sh
uv tree                         # dependency tree
uv run python -c "import importlib.metadata as m; print(m.version('langgraph'))"
```

Runtime version checks beat guessing from docs: libraries move symbols between minors (see the `langgraph` skill).

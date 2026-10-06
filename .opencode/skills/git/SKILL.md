---
name: git
description: Git conventions for this repo — commit message format, staged paths, feature branches, and recovering files from history
---

# Git

## Commit message format (AGENTS.md, enforced in review)

```
type(scope): summary
```

Types in use: `feat`, `fix`, `edit`, `chore`, `docs`. Scopes: `engine` (LLM client/config), `agent` (graph, nodes, tools, prompts), `research`, `benchmark`, `docs`, `scripts`.

Examples that already merged:

```
docs(agents): added AGENTS.md with project context, conventions and agent workflow
edit(agent): forbid unitary tests, require only deep useful tests
chore(engine): committed bare uv scaffold pyproject and python version
```

## Staging rules

- Stage explicit paths only: `git add path/to/file`. **Never `git add -A` or `git add .`** — the working tree often contains other agents' in-progress work (deleted files, uncommitted scaffolds) that must not be swept into your commit.
- One logical change = one commit. If a change touches code and its docs, put both in the same commit.
- Commit a subset of the index with pathspec: `git commit -m "..." -- <paths>`.
- Untracked files must be `git add`-ed first or `git commit -- <path>` fails with `pathspec ... did not match any file(s) known to git`.

## Branches (AGENTS.md: never commit to `main` directly)

```
feat/<issue>-<slug>     fix/<issue>-<slug>     research/<issue>-<slug>
bench/<issue>-<slug>    chore/<issue>-<slug>   docs/<issue>-<slug>
```

Flow: create branch → commit → push with `-u origin <branch>` → open PR referencing the issue → merge. See the `github` skill for PR/issue commands.

**Auth: use `gh`, never touch `~/.ssh`.** If a push fails with an auth error, do not inspect or test SSH keys — that directory is off limits. Push over HTTPS via the `gh` credential helper instead: `git push https://github.com/<owner>/<repo>.git <branch>`, or tell the user to run `gh auth status`.

## Working-tree facts for this repo

- `.env` and service-account JSON files are gitignored — verify with `git check-ignore -v .env` before worrying, and never commit keys.
- A file deleted in the working tree but not committed shows as ` D path`. Restoring it accidentally is a real hazard: `git reset --hard` or `git checkout -- <path>` will resurrect it. Check `git status` before and after any reset/checkout.
- Deleted files stay readable: `git show HEAD~2:docs/feasibility.html` (pathspec relative to that commit).

## Useful checks before pushing

```sh
git status --short            # what is dirty, staged vs unstaged
git log --oneline origin/<branch>..HEAD   # what your branch adds
git diff --cached --stat      # what a commit will contain
```

---
name: github
description: GitHub workflow with the gh CLI — creating issues in this repo's contract format, opening PRs, merging, and reading the roadmap
---

# GitHub (gh CLI)

Authenticated and available (`gh` 2.79). The repo is **`ol1ak5/model-x-ray`** (renamed from `data-room-sentinel`; the old remote path redirects).

**`gh` is the only auth path.** Never read, list, or test SSH keys in `~/.ssh` — user territory, off limits. If git transport fails with an auth error, push over HTTPS with the `gh` credential helper (`git push https://github.com/<owner>/<repo>.git <branch>`) or ask the user to run `gh auth status`.

## Issue contract (AGENTS.md — issues are the agent-to-agent contract)

Every issue body must contain, in order:

```markdown
## Context
Why this exists, links to the design doc (`docs/agent-architecture.md`, `docs/evaluation.md`) and parent issue.

## Acceptance criteria
- [ ] Checkable, concrete, testable item
- [ ] ...

## Follow-ups
- Issues this one cannot finish, unblocks, or finds broken
```

Title format: `[label] one-line goal` where label is one of `research`, `agent`, `engine`, `benchmark`, `docs`, `chore`, `bug`, `blocked`, `roadmap`.

```sh
gh issue create --title "[agent] Do the thing" --label agent --body "$(cat <<'EOF'
## Context
...
## Acceptance criteria
- [ ] ...
## Follow-ups
- ...
EOF
)"
```

An issue without acceptance criteria is not ready to be worked. Labels must already exist; create with `gh label create <name> --color <hex>`.

## Lifecycle rules (from AGENTS.md)

- A `research` issue MUST, as its output, spawn ≥1 `benchmark` issue and ≥1 `agent`/`engine`/`docs` issue.
- Closing an issue with zero follow-ups is suspicious unless trivial.
- Roadmap = issue #2; keep its checklist updated as children open/close.

## PRs

```sh
gh pr create --title "type(scope): summary" --body "..."
gh pr list --state open
gh pr view <n> --json state,mergeable,mergeStateStatus
gh pr merge <n> --merge        # merge commit is this repo's convention (see PRs #1, #15, #21)
```

PR body convention (used on merged PRs):

```markdown
Closes #<issue>
## What
## How it was tested
## Follow-ups filed
```

`Closes #N` in the body auto-closes the issue on merge — verify with `gh issue view <n> --json state -q .state` after merging.

## Reading the board

```sh
gh issue list --state open --limit 50        # what to work on
gh issue view <n>                            # full contract for one issue
gh issue view <n> --json labels,state        # fast filter
```

## Research shortcut

Issues #4 (Nebius tool calling) and #14/#18 (credentials) are the critical path; #5/#6 (Sheets source + sandbox) block most agent work.

# AI Skills Workflow

## Change Documents

All design and implementation change documents live in `docs/changelogs/`.

Filename:
- With Jira ID: `{jira-id}-{topic}.md`
- Without Jira ID: `YYYY-MM-DD-{topic}.md`

Every change document is the SSOT for one change, grows in-place, and must not be duplicated. Resume work by reading its `status`. See template at the bottom of this file.

When implemented behavior is described, update `source_paths` with repository-relative paths actually created or inspected.

## Lifecycle

| Skill | Input status | Output status | Required change document updates |
|---|---|---|---|
| `idea-refine` | none | `Draft` | Create Problem Statement, Recommended Direction, Key Assumptions, MVP Scope / Not Doing |
| `planning-and-task-breakdown` | `Draft` | `Ready-to-implement` | Append `## Tasks`; update metadata; update related docs when applicable |
| `incremental-implementation` | `Ready-to-implement` or `Issues-confirmed` | `Ready-to-review` | Check off completed tasks or review issues |
| `code-review-and-quality` | `Ready-to-review` | `Done` or `Issues-confirmed` | Append `## Review Issues` only when issues are found |
| `code-simplification` | any | unchanged | No status change |

## Stage Execution

- Before any stage work, use the skill with the same name as the stage.
- If the matching skill is unavailable or cannot be read, stop and report that blocker.
- At stage completion, report the completed stage, resulting status, commit hash if committed, and next allowed stage.
- The main agent runs `idea-refine` directly because it may require user interaction. For every other stage, the main agent reads **only the `status` field** from the change document frontmatter, then spawns that stage as a sub agent passing only the change document path. The main agent must not read or reason about any other part of the change document before spawning.
- Each stage sub agent is responsible for reading the change document itself and determining what to do.

## Stage Rules

### `idea-refine`

Creates one change document. Must not touch any existing file.

To understand the current system, read only files under `docs/`. Do not read source code files.

After creating the change document, if it contains any unresolved Key Assumptions (`[ ]`), stop and present each assumption to the user as an explicit question. Do not proceed until all assumptions are confirmed. This overrides the auto-advance rule.

### `planning-and-task-breakdown`

Updates the change document only (append tasks, update metadata and status).

Must also update SSOT documents that own the behavior being changed. If none exist and the plan affects setup, usage, commands, configuration, public behavior, or developer workflow, create the smallest appropriate doc, usually `README.md`.

### `incremental-implementation`

On entry, read **only** the task list from the change document: task indices, one-line titles, and any explicit dependency markers. Do not read task descriptions or any other section before spawning.

Determine parallelism from dependency markers: spawn independent tasks simultaneously in a single message; spawn dependent tasks only after their prerequisites complete.

Spawn one sub agent per task (or confirmed review fix) using `isolation: "worktree"`. Pass only the change document path and the task index — the sub agent must read the change document itself to understand what to implement.

Each sub agent must:
1. Implement the task or fix.
2. Implement or update relevant test cases when behavior, configuration, commands, or public interfaces are affected.
3. Update SSOT documents that own any behavior changed by this task or fix.
4. Mark the task or issue `[x]` in the change document.
5. Spawn a review sub agent (following Review Agent Rules) scoped to this task only. Fix any issues found before proceeding.
6. Commit code, updated SSOT documents, and change document together in one commit.

After all sub agents complete, merge their worktree branches in dependency order. Resolve any conflicts before proceeding. When all tasks are merged, update status to `Ready-to-review`, then commit.

For new Python projects, create Python git ignores before running Python commands that may generate cache files.

### `code-review-and-quality`

Reviews all tasks and all previous review issues on every cycle. Re-check fixed issues against the current implementation before accepting them as resolved.

Verify implementation, related docs, metadata, `source_paths`, links, setup commands, environment variables, and behavior claims against inspected code.

If all tasks pass: run `doc-audit`, add work to `CHANGELOG.md` (create if missing), set status to `Done`, commit all together.

If issues are found: append `## Review Issues`, set status to `Issues-confirmed`, commit, highlight issues in console output. Reviewers flag issues; they do not fix them.

### `code-simplification`

Refactors only. Zero behavior changes. No marks in the change document. Commit when done.

## Universal Rules

- Every skill ends with a commit: code, change document, or both.
- Commit task checkboxes and status changes with the code they describe.
- Commit message format: `type: description` (e.g., `feat: implement login flow`).
- Commit type labels: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`.
- Auto-advance to the next stage; no user approval required between stages.
- Only `incremental-implementation` may change source code, configuration files, or any file that affects runtime behavior.
- When spawning a review agent, use a **different** agent than the one currently running. Since the primary agent is `claude`, use `codex` first, then fall back to `copilot`. Both are Bash CLI tools — invoke via `codex exec review` or `copilot -p "..." --allow-all-tools`. Do not use the `Agent` tool with `subagent_type: "claude"` for review.

## Documentation Rules

- Root `README.md` is a service overview only: features, brief architecture, top-level folders, and link to `docs/README.md`.
- `docs/README.md` is the documentation entry point. All repository docs must be reachable from it.
- Keep change lifecycle records in `docs/changelogs/`; do not use them as user-facing guides.
- Prefer one canonical owner for each topic; cross-link instead of duplicating details.

## Python Rules

- Use `uv` for Python commands by default.
- Prefer `uv run python ...` over `python` or `python3`.
- Prefer `uv run python -m pytest` for tests.
- Commit `uv.lock` when dependency resolution changes.
- Add Python ignores before running commands that may generate cache files.

## Change Document Template

```markdown
---
title: "..."
status: Draft
created: YYYY-MM-DD
doc_type: change
last_reviewed: YYYY-MM-DD
source_paths: []
scope: "Tracks this change from design through review."
---

## Problem Statement
## Recommended Direction
## Key Assumptions
## MVP Scope / Not Doing
## Tasks
- [ ] Task 1: ...

## Review Issues
- [ ] Issue 1: ...
```

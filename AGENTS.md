# AI Skills Workflow

## Change Documents

All design and implementation change documents live in `docs/changelogs/`.

Filename:
- With Jira ID: `{jira-id}-{topic}.md`
- Without Jira ID: `YYYY-MM-DD-{topic}.md`

Use a Jira ID when the work is tied to Jira. Otherwise use the current date in `YYYY-MM-DD`.

Every change document is the SSOT for one change, grows in-place, and must not be duplicated. Resume work by reading its `status`.

Frontmatter follows the repository documentation metadata convention. When none exists, use `doc-audit` style metadata:

```yaml
---
title: "..."
status: Draft
created: YYYY-MM-DD
doc_type: change
last_reviewed: YYYY-MM-DD
source_paths: []
scope: "Tracks this change from design through review."
---
```

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
- Proceed to the next stage automatically without waiting for user approval.

## Stage Rules

### `idea-refine`

May change:
- Create one change document.

Must not change:
- Existing source code, docs, or config files.
- Any existing file, even if incomplete or relevant.

### `planning-and-task-breakdown`

May change:
- The change document in `docs/changelogs/`: append tasks, update metadata, update status.

Must change when applicable:
- Related documentation to reflect what is about to change.
- If no related doc exists and the plan affects setup, usage, commands, configuration, public behavior, or developer workflow, create the smallest appropriate doc, usually `README.md`.

Must not change:
- Source code.
- Configuration files.
- Any file that affects runtime behavior.

### `incremental-implementation`

For each task or confirmed review fix:
1. Implement the task or fix.
2. Implement or update relevant test cases in the same change when behavior, configuration, commands, or public interfaces are affected.
3. Mark the task or issue `[x]` in the change document.
4. Commit code and change document together, one commit per task or fix.

When all tasks are complete, update status to `Ready-to-review`, then commit.

For new Python projects, create Python git ignores before running Python commands that may generate cache files.

### `code-review-and-quality`

May change:
- The change document: append `## Review Issues`, update metadata, update status.
- `CHANGELOG.md` only when setting the change document status to `Done`.
- Documentation files only through `doc-audit` after all implementation review issues are resolved and before setting status to `Done`.

Must not change:
- Source code.
- Configuration files.
- Any file that affects runtime behavior.

Review all tasks and all previous review issues on every cycle regardless of prior review history. Re-check fixed issues against the current implementation before accepting them as resolved.

Review must verify implementation, related docs, metadata, `source_paths`, links, setup commands, environment variables, and behavior claims against inspected code.

If all tasks pass:
- Run `doc-audit` after all tasks and previous review issues are resolved, before setting status to `Done`.
- Add the current work to `CHANGELOG.md`; create it if missing.
- Set status to `Done`.
- Commit `CHANGELOG.md`, the change document, and any `doc-audit` documentation updates together.

If issues are found:
- Append `## Review Issues` with one checkbox per issue.
- Set status to `Issues-confirmed`.
- Commit the change document.
- Highlight issues clearly in console output.
- Advise the user to proceed to `incremental-implementation`.

Reviewers flag issues; they do not fix them. Fixing belongs to `incremental-implementation`.

### `code-simplification`

- Refactors only.
- Zero behavior changes.
- No marks left in the change document.
- Commit simplified code when done.

## Universal Rules

- Every skill ends with a commit: code, change document, or both.
- Commit task checkboxes and status changes with the code they describe.
- Commit message format: `[YYYY.MM.DD.NN] type: description` (e.g., `[2026.04.07.00] feat: implement login flow`). Use the current date and increment `NN` from `00` for each commit that day.
- Commit type labels: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`.
- Auto-advance to the next stage; no user approval required between stages.
- `code-review-and-quality` reviews all tasks on every cycle; all pass means `Done`.
- `code-simplification` is optional and does not affect change completeness.

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
- [ ] Task 2: ...

## Review Issues
- [ ] Issue 1: ...
- [ ] Issue 2: ...
```

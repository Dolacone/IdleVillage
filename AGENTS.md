# AI Skills Workflow

## Change Documents

All design and implementation change documents live in `docs/changelogs/`.

Filename:
- With Jira ID: `{jira-id}-{topic}.md`
- Without Jira ID: `YYYY-MM-DD-{topic}.md`

Every change document is the SSOT for one change, grows in-place, and must not be duplicated. Resume work by reading its `status`. See template at the bottom of this file.

When implemented behavior is described, update `source_paths` with repository-relative paths actually created or inspected.

## Universal Rules

- Every skill ends with a commit: code, change document, or both.
- Commit task checkboxes and status changes with the code they describe.
- Commit message format: `type: description` (e.g., `feat: implement login flow`).
- Commit type labels: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`.
- Auto-advance to the next stage; no user approval required between stages.
- Only the `code` stage may change source code, configuration files, or any file that affects runtime behavior.
- `refine` is the only stage where user interaction is permitted. All subsequent stages run autonomously without waiting for user input.
- Reviews use the reviewer agent that the running skill names (for example `opus-5.5`). Each review round runs in a new, independent agent session.

## Documentation Rules

- Root `README.md` is a service overview only: features, brief architecture, top-level folders, and link to `docs/README.md`.
- `docs/README.md` is the documentation entry point. All repository docs must be reachable from it.
- Keep change lifecycle records in `docs/changelogs/`; do not use them as user-facing guides.
- Prefer one canonical owner for each topic; cross-link instead of duplicating details.
- Only documents under `docs/` carry frontmatter metadata (`doc_type`, `last_reviewed`, and the rest). `CHANGELOG.md` and root `README.md` are not documents and must have no frontmatter.

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
## Clarifications
<!-- Q: [question] / A: [answer] — resolved during refine stage -->
## MVP Scope / Not Doing
## Architecture Decisions
<!-- Key technical choices and rationale — added during plan stage -->
## Tasks
- [ ] Task 1: ...

## Review Issues
- [ ] Issue 1: ...
```

# AI Skills Workflow

## Change Documents

All design and implementation change documents live in `docs/changelogs/`.

Filename:
- With Jira ID: `{jira-id}-{topic}.md`
- Without Jira ID: `YYYY-MM-DD-{topic}.md`

Every change document is the SSOT for one change, grows in-place, and must not be duplicated. Resume work by reading its `status`. See template at the bottom of this file.

When implemented behavior is described, update `source_paths` with repository-relative paths actually created or inspected.

## Lifecycle

| Stage | Skill | Input status | Output status | Required change document updates |
|---|---|---|---|---|
| `refine` | `idea-refine` | none | `Draft` | Create Problem Statement, Recommended Direction, Clarifications, MVP Scope / Not Doing |
| `plan` | `planning-and-task-breakdown` | `Draft` | `Ready-to-implement` | Append `## Architecture Decisions` and `## Tasks`; update metadata; update related docs when applicable |
| `code` | `incremental-implementation` | `Ready-to-implement` or `Issues-confirmed` | `Ready-to-review` | Check off completed tasks or review issues |
| `review` | `code-review-and-quality` | `Ready-to-review` | `Done` or `Issues-confirmed` | Append `## Review Issues` only when issues are found |
| `refactor` | `code-simplification` | any | unchanged | No status change |

## Stage Execution

- Before any stage work, use the skill mapped to that stage.
- If the matching skill is unavailable or cannot be read, stop and report that blocker.
- At stage completion, report the completed stage, resulting status, commit hash if committed, and next allowed stage.
- The main agent runs all stages directly except `review`.
- For `review`, the main agent spawns a review agent (per Universal Rules), passing the change document path. The review agent is responsible for reading the change document and running the review.

## Stage Rules

### `refine`

Skill: `idea-refine`

Creates one change document in `docs/changelogs/`. Must not touch any existing file.

To understand the current system, read only files under `docs/`. Do not read source code files.

Before finalizing the change document, identify all ambiguous or unclear aspects and ask the user to resolve them. Record every question and answer in `## Clarifications` using Q&A format. Do not advance until all clarifications are resolved.

**Completion checklist (must verify before advancing):**
- [ ] 所有模糊點已在 `## Clarifications` 以 Q&A 紀錄並解決
- [ ] 變更文件已建立於 `docs/changelogs/`
- [ ] 未觸碰任何既有檔案

### `plan`

Skill: `planning-and-task-breakdown`

Updates the change document only (append `## Architecture Decisions` and `## Tasks`, update metadata and status).

Must also update SSOT documents that own the behavior being changed. If none exist and the plan affects setup, usage, commands, configuration, public behavior, or developer workflow, create the smallest appropriate doc, usually `README.md`.

Each task must bundle its own tests: if a task changes behavior, configuration, commands, or public interfaces, the relevant test updates belong in that same task — not in a separate task. Do not create standalone "update tests" tasks.

After completing the plan, spawn a review agent (per Universal Rules) to review the Architecture Decisions and task breakdown. If issues are found, revise and re-review. Maximum 2 review rounds; if still unresolved, stop and report. Auto-advance after the review agent approves — no human confirmation required.

**Completion checklist (must verify before advancing):**
- [ ] Architecture Decisions 已寫入變更文件
- [ ] Tasks 已寫入變更文件，每個 task 已包含測試
- [ ] 相關 SSOT 文件已更新（或確認無需更新）
- [ ] 已 spawn review agent 審查 Architecture Decisions 與 task breakdown
- [ ] Review agent 核准（或已修正並重新審查，最多 2 輪）
- [ ] 狀態已更新為 `Ready-to-implement`

### `code`

Skill: `incremental-implementation`

Read the change document and implement tasks sequentially in dependency order.

For each task:
1. Implement the task or fix.
2. Implement or update relevant test cases when behavior, configuration, commands, or public interfaces are affected.
3. Update SSOT documents that own any behavior changed by this task or fix.
4. Mark the task or issue `[x]` in the change document.
5. Commit code, updated SSOT documents, and change document together in one commit.

After all tasks are complete, update status to `Ready-to-review`, then commit.

For new Python projects, create Python git ignores before running Python commands that may generate cache files.

**Completion checklist (must verify before advancing):**
- [ ] 每個 task 已在變更文件勾選 `[x]`
- [ ] 每個 task 的 code、文件、變更文件已一起 commit
- [ ] 狀態已更新為 `Ready-to-review`

### `review`

Skill: `code-review-and-quality`

The review agent (per Universal Rules) runs the skill and reports results to the main agent:
- Reviews all tasks and all previous review issues on every cycle. Re-checks fixed issues against the current implementation before accepting them as resolved.
- Verifies implementation, related docs, metadata, `source_paths`, links, setup commands, environment variables, and behavior claims against inspected code.
- If issues are found: append `## Review Issues`, set status to `Issues-confirmed`, commit, highlight issues in console output. Review agents flag issues; they do not fix them.

After the review agent approves, the main agent:
1. Runs `doc-audit`.
2. Adds work to `CHANGELOG.md` (create if missing).
3. Sets status to `Done`.
4. Commits all together.

Completion checklist — 共同（每輪必做）：
- [ ] 所有 tasks 與前輪 review issues 均已重新審查
- [ ] 實作、文件、metadata、`source_paths`、行為描述均已對照程式碼驗證

若有問題（→ `Issues-confirmed`）：
- [ ] `## Review Issues` 已寫入變更文件
- [ ] 狀態已設為 `Issues-confirmed` 並 commit

若核准（→ `Done`）：
- [ ] `doc-audit` 已執行
- [ ] `CHANGELOG.md` 已更新
- [ ] 狀態已設為 `Done` 並 commit

### `refactor`

Skill: `code-simplification`

Refactors only. Zero behavior changes. No marks in the change document.

After each simplification, run tests. If tests fail, revert the simplification. Follow skill rules for commit strategy.

## Universal Rules

- Every skill ends with a commit: code, change document, or both.
- Commit task checkboxes and status changes with the code they describe.
- Commit message format: `type: description` (e.g., `feat: implement login flow`).
- Commit type labels: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`.
- Auto-advance to the next stage; no user approval required between stages.
- Only the `code` stage may change source code, configuration files, or any file that affects runtime behavior.
- `refine` is the only stage where user interaction is permitted. All subsequent stages run autonomously without waiting for user input.
- Whenever doing reviews, use a **different** agent than the one currently running. Since the primary agent is `claude`, use `codex` first, then fall back to `copilot`. Both are Bash CLI tools — invoke via `codex exec review` or `copilot -p "..." --allow-all-tools`. Do not use the `Agent` tool with `subagent_type: "claude"` for review.

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

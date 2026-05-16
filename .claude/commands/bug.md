# /bug

Investigate a bug report against documentation and, if valid, start the AGENTS.md workflow to plan a fix.

## Input

`/bug <description>` — describe the bug: what you expected to happen and what actually happened.

## Steps

### 1. Check documentation

Read only files under `docs/`. Do not read any source code files.

Determine whether the expected behavior described by the user is consistent with the documented behavior.

- **If NOT consistent**: tell the user their expected behavior differs from the documented design, and suggest filing a feature request via `/feature` instead. Stop — do not proceed further.
- **If consistent**: continue to Step 2.

### 2. Investigate source code

Read source code files to identify the root cause of the discrepancy between the documented behavior and the actual behavior.

Report your findings: which file and line contain the bug, and why it causes the observed behavior.

### 3. Start the AGENTS.md workflow

Use the bug description and root cause findings as input to start the `refine` stage of the AGENTS.md workflow.

Follow all stage rules and universal rules defined in AGENTS.md. AGENTS.md takes precedence over any other default behavior.

The `refine` stage will create a change document. After `refine` completes, auto-advance through `plan` → `code` → `review` following the normal pipeline.

## Rules

- Steps 1 and 2 are read-only. Do not modify any file until the AGENTS.md workflow begins.
- Do not skip Step 1. Even if the bug seems obvious, always verify against documentation first.

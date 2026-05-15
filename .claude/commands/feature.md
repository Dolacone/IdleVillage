# /feature

Run the full AI Skills Workflow defined in AGENTS.md.

## Input

- **New idea** (`/feature <idea>`): no change document exists yet. Begin at the `refine` stage.
- **Resume** (`/feature <change-doc-path>`): a change document exists. Read its `status` field and begin at the first stage whose expected input status matches.

## Pipeline

Run stages in order: `refine` → `plan` → `code` → `review`

Skip any stage whose expected input status does not match the current change document status. The `refactor` stage is optional and excluded from this pipeline — it must be triggered separately.

## Entry Logic

1. If input is an idea (text), start at `refine`.
2. If input is a change document path, read `status` and find the matching stage:
   - `Draft` → start at `plan`
   - `Ready-to-implement` or `Issues-confirmed` → start at `code`
   - `Ready-to-review` → start at `review`
   - `Done` → report "Workflow already complete" and stop.
3. Auto-advance through each subsequent stage following AGENTS.md rules.
4. Do not pause between stages unless a stage explicitly requires it.

## Rules

Follow all stage rules and universal rules defined in AGENTS.md. AGENTS.md takes precedence over any skill's default behavior.

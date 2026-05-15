# /refactor

Run the `refactor` stage of the AI Skills Workflow defined in AGENTS.md.

## Input

- **Change document** (`/refactor <change-doc-path>`): read `source_paths` from the change document to focus simplification on recently changed files.
- **File paths** (`/refactor <file-or-directory>`): simplify the specified files directly.
- **No argument** (`/refactor`): simplify the most recently changed files in the working tree.

## Rules

Use the `code-simplification` skill. Follow all stage rules defined in AGENTS.md under the `refactor` stage. AGENTS.md takes precedence over any skill's default behavior.

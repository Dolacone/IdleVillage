# AI Agent Development Guidelines (Discord Idle Village)

## Core Philosophies
1. Async First: All database I/O and network requests MUST use `async/await`.
2. Stateless Logic: Bot logic should rely on database state rather than in-memory variables.
3. Plain Text Formatting: Never use Markdown emphasis (** or *). Use plain text, headings, or backticks.
4. Language Standards: English for changelogs, Traditional Chinese for other community-facing docs.
5. Specialized Roles: Activate the relevant skill from `.agents/skills/` based on the lifecycle phase.
6. Role Activation Protocol: ONLY the user can authorize switching between planning, implementation, and QA. The AI MUST wait for a clear directive before activating a different specialized skill.

## Gameplay Logic Standards
- SSOT First: Resolve mechanic names, formulas, and lifecycle rules from the latest `docs/` content instead of reusing older skill or code wording.
- Settlement & Action Lifecycle: Use `docs/core/engine.md` and `docs/modules/village.md` as the SSOT for trigger levels, settlement steps, Action Cycle start rules, and pre-deduction behavior.
- Efficiency Formula: `(StatA + StatB) / 2 / 100`. (SSOT: `docs/modules/player_stats.md`)
- Stat Window Rules: Use `docs/modules/player_stats.md` and `docs/terminology.md` for the current stat-window name, size, and partial-slice recalculation method.

## Command & UI Standards
- Ephemeral First: All Slash Command responses MUST be `ephemeral=True`.
- UI Persistence: Use `inter.response.edit_message()` to update the interface instead of sending new messages whenever possible.
- Admin Gating: Admin-only slash commands must check `ADMIN_IDS` via `is_admin()`. `/idlevillage-initial` must remain admin-gated.

## Commit & Workflow Standards
- Commit Format: `[YYYY.MM.DD.NN] type: description` (e.g., `[2026.04.07.00] feat: implement ...`).
- Status Lifecycle: Draft -> In-Progress -> Done. (SSOT: `docs/core/development_workflow.md`)

## Testing Standards
- Mechanic-First Tests: Tests should be named and structured around documented game behaviors in `docs/modules/`, not around implementation details.
- Implementation Phase: The implementing agent should add or update automated tests for any changed mechanic and run `.venv/bin/python -m unittest discover -s tests -v` before handoff.
- Verification Phase: The reviewing agent must audit both the code and the tests against `docs/modules/`; passing tests are evidence, not ground truth.
- Expected Failures: Use `expectedFailure` only for known, explicitly acknowledged gaps. Review output must distinguish them from unexpected regressions.

## Database Standards
- Use `aiosqlite` for asynchronous connections.
- Table names are plural. Parse `docs/` for table structures (Markdown SSOT).
- Location: `data/village.db` (git-ignored).

## Project Structure
- `src/`: Core application source.
- `.agents/skills/`: Specialized AI skills defining expert roles.
- `docs/`: Game design and planning documents (The Source of Truth).

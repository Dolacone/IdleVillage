# AI Agent Development Guidelines (Discord Idle Village)

## Core Philosophies
1. Async First: All database I/O and network requests MUST use `async/await`.
2. Stateless Logic: Bot logic should rely on database state rather than in-memory variables.
3. Plain Text Formatting: Never use Markdown emphasis (** or *). Use plain text, headings, or backticks.
4. Language Standards: English for changelogs, Traditional Chinese for other community-facing docs.
5. Specialized Roles: Activate the relevant skill from `.agents/skills/` based on the lifecycle phase (Planning, Implementation, QA).

## Gameplay Logic Standards
- 1-Hour Lease Model: Resources are pre-deducted at the start. Settlement at the end. (SSOT: `docs/modules/village.md`)
- Efficiency Formula: `(StatA + StatB) / 2 / 100`. (SSOT: `docs/modules/player_stats.md`)
- Stats Invariants: Stats are calculated using a 150h sliding window. (SSOT: `docs/modules/player_stats.md`)

## Command & UI Standards
- Ephemeral First: All Slash Command responses MUST be `ephemeral=True`.
- UI Persistence: Use `inter.response.edit_message()` to update the interface instead of sending new messages whenever possible.
- Owner Only: `/idlevillage-initial` must check for `ALLOWED_OWNER_ID`.

## Commit & Workflow Standards
- Commit Format: `type: [YYYY.MM.DD.NN] description` (e.g., `feat: [2026.04.07.00] implement ...`).
- Status Lifecycle: Draft -> In-Progress -> Done. (SSOT: `docs/core/development_workflow.md`)

## Database Standards
- Use `aiosqlite` for asynchronous connections.
- Table names are plural. Parse `docs/` for table structures (Markdown SSOT).
- Location: `data/village.db` (git-ignored).

## Project Structure
- `src/`: Core application source.
- `.agents/skills/`: Specialized AI skills defining expert roles.
- `docs/`: Game design and planning documents (The Source of Truth).

# AI Agent Development Guidelines (Discord Idle Village)

## Core Philosophies
1. Async First: All database I/O and network requests MUST use `async/await`.
2. Stateless Logic: Bot logic should rely on database state rather than in-memory variables to ensure resilience across restarts.
3. Dynamic Stats: All attribute calculations must be handled through a unified service (e.g., `src/core/stats.py`) that aggregates data from the last 150 action records.
4. Plain Text Formatting: Never use Markdown emphasis syntax in documents or responses. Do not use double-asterisk bold markers or single-asterisk italic markers. Use plain text, headings, lists, or backticks instead.

## Database Standards
- Use `aiosqlite` for asynchronous connections.
- Prefer `async with get_connection() as db` for scoped database access. Do NOT use `async with await get_connection()`, as this can double-start the underlying `aiosqlite` worker thread.
- Table names should be plural (e.g., `players`, `actions_history`).
- Markdown SSOT: The database schema is defined in Markdown files under `docs/`. AI agents MUST parse these documents to determine table structures and initial values. Do NOT maintain a separate `schema.sql`.
- Database file location: `data/village.db` (MUST be git-ignored).
- Player identity is village-scoped. Treat `(discord_id, village_id)` as the stable uniqueness key rather than assuming a global player row per Discord user.
- `player_actions_log` is transition-based: record completed action segments using `action_type`, `start_time`, and `end_time`. Do not default to hourly stat-category rows unless the docs are explicitly changed.

## Commit Standards
- Use Conventional Commits with versioning (e.g., `feat: [2026.04.06.00] ...`).
- All significant changes MUST follow the lifecycle defined in `docs/core/development_workflow.md`.
- Status transition: Draft -> In-Progress -> Done.
- Conventional Commit types:
  - `feat:`: New features or game modules.
  - `fix:`: Bug fixes in logic or commands.
  - `docs:`: Updates to game design or documentation.
  - `refactor:`: Code restructuring without behavior changes.
  - `chore:`: Dependency updates or configuration changes.

## Command Standards
- Implement all Slash Commands within Cog classes located in `src/cogs/`.
- Prefer `@commands.slash_command` for slash command registration inside Cogs.
- The main `/action` menu logic should reside in `src/cogs/actions.py`.
- Use `disnake`'s UI components (Select menus, Buttons) for complex interactions.
- Command responses should default to caller-only (`ephemeral=True`) unless the design docs explicitly call for a public message.
- Guild setup is manual via `/idlevillage-initial`; do not assume automatic initialization on guild join unless the docs are updated.

## Core Logic & Engine
- The hourly settlement engine resides in `src/core/engine.py`.
- Before modifying any gameplay values or formulas, refer to the balance settings in `docs/plan_v1.md`.
- Ensure all automated tasks (loops) are managed via `disnake.ext.tasks`.
- Satiety should only drain while the player is not `idle`. Refill checks should happen at village idle boundaries according to the current design docs.

## Project Structure
- `src/`: Core application source (entrypoint, cogs, core, database, requirements).
- `data/`: Local SQLite storage (excluded from git and docker).
- `tests/`: Root-level automated test suite (excluded from Docker images).
- `docs/`: Game design and planning documents.
- `docs/changelogs/`: Historical change plans and changelogs.
- `docs/core/development_workflow.md`: Standards for versioning and AI collaboration.

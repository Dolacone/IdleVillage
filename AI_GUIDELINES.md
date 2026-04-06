# AI Agent Development Guidelines (Discord Idle Village)

## Core Philosophies
1. Async First: All database I/O and network requests MUST use `async/await`.
2. Stateless Logic: Bot logic should rely on database state rather than in-memory variables to ensure resilience across restarts.
3. Dynamic Stats: All attribute calculations must be handled through a unified service (e.g., `src/core/stats.py`) that aggregates data from the last 150 action records.

## Database Standards
- Use `aiosqlite` for asynchronous connections.
- Table names should be plural (e.g., `players`, `actions_history`).
- Markdown SSOT: The database schema is defined in `docs/**/*.md`. AI agents MUST parse these documents to determine table structures and initial values. Do NOT maintain a separate `schema.sql`.
- Database file location: `data/village.db` (MUST be git-ignored).

## Commit Standards
- Use Conventional Commits for all changes:
  - `feat:`: New features or game modules.
  - `fix:`: Bug fixes in logic or commands.
  - `docs:`: Updates to game design or documentation.
  - `refactor:`: Code restructuring without behavior changes.
  - `chore:`: Dependency updates or configuration changes.

## Command Standards
- Implement all Slash Commands within Cog classes located in `src/cogs/`.
- The main `/action` menu logic should reside in `src/cogs/actions.py`.
- Use `disnake`'s UI components (Select menus, Buttons) for complex interactions.

## Core Logic & Engine
- The hourly settlement engine resides in `src/core/engine.py`.
- Before modifying any gameplay values or formulas, refer to the balance settings in `docs/plan_v1.md`.
- Ensure all automated tasks (loops) are managed via `disnake.ext.tasks`.

## Project Structure
- `src/cogs/`: Command implementations.
- `src/core/`: Game engine and logic (stats, settlement, satiety).
- `src/database/`: DB connection and schema management.
- `data/`: Local SQLite storage (excluded from git).
- `docs/`: Game design and planning documents.

# IdleVillage v2 Preview SSOT Map

This directory is the v2 design preview. v2 is a fresh restart and replaces v1 gameplay rules.

## SSOT Rules

- Each gameplay rule belongs to exactly one functional module file.
- Other files may reference the owning module, but should not redefine the same formula, lifecycle, or notification rule.
- `.env.example` is the SSOT for default environment values.
- `docs/db-schema.md` is the SSOT for SQLite structure only, not gameplay logic.

## Functional Modules

| Area | SSOT file |
| :--- | :--- |
| Environment keys and global formulas | `engine/formula.md` |
| Cycle timing, triggers, refresh, burst, partial timing | `engine/cycle-engine.md` |
| Action settlement, resource shortage, output distribution | `engine/action-resolver.md` |
| Stage sequence, targets, overtime, clears | `managers/stage-manager.md` |
| Building XP, level cap, capped progress | `managers/building-manager.md` |
| Player state, AP, materials | `managers/player-manager.md` |
| Gear upgrade rates, pity, costs | `managers/gear-manager.md` |
| Village resources | `managers/resource-manager.md` |
| SQLite schema | `db-schema.md` |
| Slash command routing | `discord/command-handler.md` |
| Embed and component rendering | `discord/ui-renderer.md` |
| Public notifications and ordering | `discord/notification.md` |

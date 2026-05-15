# Changelog

## 2026-05-15

- Replaced five `/idlevillage-manager` sub-commands with a single unified interface: admin selects a player via User Select dropdown, views a full stats panel (embed), and edits any field via Modal dialogs. Extracted `_fetch_player_data()` helper to eliminate duplicated DB query logic; `on_modal_submit` now defers with `ephemeral=True` to keep admin operations private.
- Added `/idlevillage-manager` admin slash command with five subcommands (`player-view`, `player-gear`, `player-material`, `player-pity`, `player-risky`) to view and set individual player stats directly. Also added `set_material` and `set_risky_failed_levels` setters to `player_manager`.
- Completed risky mode enhancements: risky failures now reset gear and pity to zero while adding the pre-reset gear level to `risky_failed_levels`; risky success rate uses permanent failed-level bonus; pity-free risky successes can gain multiple levels.

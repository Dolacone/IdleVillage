# Changelog

## 2026-05-15

- Simplified risky mode success: removed pity=0 random multi-level gain (+1/+2/+3 at 60/30/10%); success now always grants exactly gear +1 regardless of pity state. Failure behavior and success rate formula unchanged.
- Replaced five `/idlevillage-manager` sub-commands with a single unified interface: admin selects a player via User Select dropdown, views a full stats panel (embed), and edits any field via Modal dialogs. Extracted `_fetch_player_data()` helper to eliminate duplicated DB query logic; `on_modal_submit` now defers with `ephemeral=True` to keep admin operations private.
- Added `/idlevillage-manager` admin slash command with five subcommands (`player-view`, `player-gear`, `player-material`, `player-pity`, `player-risky`) to view and set individual player stats directly. Also added `set_material` and `set_risky_failed_levels` setters to `player_manager`.
- Completed risky mode enhancements: risky failures now reset gear and pity to zero while adding the pre-reset gear level to `risky_failed_levels`; risky success rate uses permanent failed-level bonus; pity-free risky successes can gain multiple levels.

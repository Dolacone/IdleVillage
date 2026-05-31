# Changelog

## 2026-05-31

- Added "🩸 獻祭素材" button to the gear upgrade sub-menu. Players select a gear type (which determines the material type consumed), then enter a quantity via a Discord Modal. Each material sacrificed increases `risky_failed_levels` by 1 (+0.01% permanent success rate bonus). No AP is consumed, no public announcement is made — only the player's gear embed updates to reflect the result. Insufficient materials or invalid input shows an error message in the embed.

## 2026-05-23

- Added new "奉獻" (Offering) action type — the 5th action. Players select one village resource (food/wood/knowledge) to consume each cycle; cost equals the sum of their 4 productive action outputs. Village-wide accumulator tracks all contributions across resource types. When accumulator reaches `OFFERING_THRESHOLD_PER_PLAYER × total players`, all players receive +1 to each of the 4 material types and the accumulator resets. Dashboard and main UI show accumulator progress. A public announcement fires on threshold trigger.
- Fixed `upgrade_cost_reduce` affix display sign: gear embed and affix notifications now show `-X%` instead of `+X%` for this affix type, matching the spec.

## 2026-05-22

- Affix extract/clear actions now post a public announcement showing the player name, gear type, and the affix type and value drawn or removed.
- Added tool affix slot system for all four gear types (gathering / building / combat / research). Each gear level 5+ unlocks one affix slot (every 5 levels). Players can spend materials to extract a random affix (1–5%, 7 types) or clear an existing slot. Affixes boost efficiency, material drop rate, upgrade success rate, upgrade cost reduction, AP refund chance, material refund chance, or cycle time reduction. Risky mode failure now clears all affixes for that gear type. Burst settle applies affixes from the current action's gear type.

## 2026-05-16

- Fixed risky mode upgrade Dropdown description: removed stale `成功無保底時 +1~+3` text (feature removed 2026-05-15) and added failure note that gear level and pity both reset to zero.
- Gear upgrade embed: success rate line now shows both pity and risky bonus components (`+保底X% +鐵齒Y%`); two detail lines (保底率、鐵齒率) are inserted below for normal/risky modes; bottom 鐵齒等級 line removed.
- Standard upgrade (normal mode) success rate now includes `risky_failed_levels × 0.0001` bonus, same as risky mode. `get_upgrade_info()` returns `risky_failed_levels` and `risky_bonus_pct` for normal mode. UI embed displays the risky bonus line in normal mode.

## 2026-05-15

- Simplified risky mode success: removed pity=0 random multi-level gain (+1/+2/+3 at 60/30/10%); success now always grants exactly gear +1 regardless of pity state. Failure behavior and success rate formula unchanged.
- Replaced five `/idlevillage-manager` sub-commands with a single unified interface: admin selects a player via User Select dropdown, views a full stats panel (embed), and edits any field via Modal dialogs. Extracted `_fetch_player_data()` helper to eliminate duplicated DB query logic; `on_modal_submit` now defers with `ephemeral=True` to keep admin operations private.
- Added `/idlevillage-manager` admin slash command with five subcommands (`player-view`, `player-gear`, `player-material`, `player-pity`, `player-risky`) to view and set individual player stats directly. Also added `set_material` and `set_risky_failed_levels` setters to `player_manager`.
- Completed risky mode enhancements: risky failures now reset gear and pity to zero while adding the pre-reset gear level to `risky_failed_levels`; risky success rate uses permanent failed-level bonus; pity-free risky successes can gain multiple levels.

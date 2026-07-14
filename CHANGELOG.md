# Changelog

## 2026-07-14

- Added "萬能素材" (universal material), a 5th material type (`materials_universal`) currently unobtainable through any drop or acquisition path (admin-only, via `/idlevillage-manager`). During gear upgrade (standard/buffer/risky), if the tool type's own material is insufficient, universal material automatically covers the shortfall; own-type material is always spent first. If the combined total is still short, the upgrade cannot proceed (no AP or material spent). The `upgrade_material_refund` affix only refunds the own-type-sourced portion of the cost, never the universal-sourced portion. Sacrifice and affix extract/clear are unaffected. `/idlevillage` and the gear upgrade sub-menu now show universal material holdings; `/idlevillage-manager`'s material edit modal gains a 5th field for it.
- Removed the "奉獻" (Offering) action system entirely: `village_state.offering_accumulator` column, `OFFERING_THRESHOLD_PER_PLAYER` env var, offering settlement logic, offering-threshold public notification, and the action dropdown option / resource-select dropdown / Dashboard progress line in the UI. Players are back to the original 4 actions (採集/建設/戰鬥/研究).
- Added `/idlevillage-trial`: any player can spend X of a chosen village resource (food/wood/knowledge, X a multiple of 1000) to open a global village trial with target X. While active, every player's action output (any type, full/partial cycles, and burst) counts toward the same shared progress counter, running in parallel with and independent of the stage system. Reaching the target within 24h splits `X/100` universal material among participants by contribution ratio, each share individually rounded up; missing the deadline forfeits the spent resource (no refund) and blocks a new trial for 12h. Dashboard and `/idlevillage` show trial progress and personal contribution; public notifications fire on start, success, and failure.

## 2026-06-27

- Gear upgrade interface: both dropdowns (tool type and upgrade mode) now start with no pre-selected item when first opened, showing only placeholder text. Matches the action select dropdown behavior.
- Affix management interface: the tool type dropdown also starts with no pre-selected item when first opened.
- Clicking "← 返回" from blank affix state now navigates back to blank gear upgrade state (instead of doing nothing).

## 2026-06-23

- Added `/idlevillage-ranking` slash command. Displays each tool type's top-3 distinct gear levels and all players at those levels. Players at gear level 0 are excluded. Same-level players are all listed; levels are sorted descending with a stable secondary sort by user ID. Output uses Ephemeral content (plain text, not embed). Truncates at 1900 characters with a notice if the output is unusually long.

## 2026-06-16

- Personal info AP line now shows when the next AP will recover: `⚡ AP：{n} / 24（下次：<t:unix:R>）`. The timestamp uses Discord relative format. Hidden when AP is already at cap.

## 2026-06-07

- Gear upgrade interface can now be opened even when AP is 0; the 🎲 強化工具 button inside remains disabled when AP is insufficient.
- Unified gear action button labels to `{icon}+四字` format: `🎲 強化工具`, `🩸 獻祭素材`, `✨ 抽取詞條`, `🗑️ 清除詞條`.
- Replaced per-slot "清除槽 N" buttons with a single `🗑️ 清除詞條` button. Clicking it re-renders the interface with a dropdown listing current affixes; selecting one executes the clear.

## 2026-05-31

- Added "🩸 獻祭素材" button to the gear upgrade sub-menu. Players select a gear type (which determines the material type consumed), then enter a quantity via a Discord Modal. Each material sacrificed increases `risky_failed_levels` by 1 (+0.01% permanent success rate bonus). No AP is consumed, no public announcement is made — only the player's gear embed updates to reflect the result. Insufficient materials or invalid input shows an error message in the embed.
- Risky mode upgrade success now rolls +1/+2/+3 at 50/35/15% (previously always +1). The random gain is unconditional — pity state does not affect the probability. Research institute level cap is still precondition-only and does not truncate multi-level results.
- Gear upgrade success notifications now show the actual new level reached (e.g. Lv5 → Lv8 on a +3 roll), instead of always showing the attempted target (Lv5 → Lv6).

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

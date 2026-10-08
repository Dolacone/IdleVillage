---
title: "移除 ＡＰ退還 與 素材減免 詞條"
status: Reviewed
created: 2026-10-08
doc_type: change
last_reviewed: 2026-10-08
source_paths:
  - docs/README.md
  - docs/changelogs/2026-10-08-remove-upgrade-affixes.md
  - docs/db-schema.md
  - docs/discord/notification.md
  - docs/discord/ui-renderer.md
  - docs/managers/affix-manager.md
  - docs/managers/gear-manager.md
  - src/cogs/ui_renderer.py
  - src/database/schema.py
  - src/managers/affix_manager.py
  - src/managers/gear_manager.py
  - src/managers/player_manager.py
  - tests/test_affix_manager.py
  - tests/test_discord_commands.py
  - tests/test_discord_notifications.py
  - tests/test_gear_manager.py
  - tests/test_v2_schema_initialization.py
scope: "Tracks this change from design through review."
---

## Problem Statement

詞條抽選池有 7 種，其中 `upgrade_ap_refund`（ＡＰ退還）與 `upgrade_cost_reduce`（素材減免）要從遊戲中移除。2026-10-07 20:59 快照（`bak/village.db.26100720`）共 3 格使用這兩種詞條：

| 玩家 | 工具 | 槽號 | 詞條 | 數值 |
| :--- | :--- | :--- | :--- | :--- |
| FFF | 採集 | 0 | `upgrade_ap_refund` | 3 |
| FFF | 戰鬥 | 1 | `upgrade_cost_reduce` | 4 |
| bilio | 戰鬥 | 0 | `upgrade_ap_refund` | 5 |

這些現存詞條改為 `material_drop`（素材掉落），槽號與數值不變。

## Recommended Direction

移除兩種詞條的定義、抽選資格、強化效果與顯示名稱。bot 啟動時以可重複執行的 UPDATE 把現存的兩種詞條改為 `material_drop`。

替代方向：

- 一次性手動腳本：deploy 前後由操作者對正式 DB 執行。不採用，原因是使用者選擇啟動時自動遷移。程式不再認得舊類型，手動漏跑會讓讀取詞條加成時出錯。
- 只停止抽出、保留既有效果：舊詞條繼續生效，新抽選不再出現。不採用，原因是使用者要求從遊戲中移除，現存詞條改成素材掉落。

選擇啟動遷移的原因：deploy 後自動套用，遷移與程式版本綁在一起，不需人工操作 Fly.io volume。

## Clarifications

- Q: 既有詞條用什麼方式轉換？ / A: bot 啟動時自動遷移。
- Q: 受影響玩家要通知嗎？ / A: 不通知。
- Q: 移除後抽選機率？ / A: 剩 5 種，等機率，各 20%。
- Q: Jira ticket？ / A: 沒有。
- Q: 數值怎麼轉？ / A: 維持相同 %，槽號不變，類型改為 `material_drop`。

## MVP Scope / Not Doing

MVP Scope:

- 抽選池（含單次抽取與自動抽取）移除兩種詞條，剩 5 種等機率。
- 自動抽取「特定效果」選單只列 5 種。
- 強化流程移除 AP 退還與素材消耗減免效果。
- 詞條名稱對照表移除兩種詞條。
- 啟動遷移把現存兩種詞條改為 `material_drop`。
- 更新 affix-manager、gear-manager、ui-renderer、notification、db-schema 文件。

Not Doing:

- 通知受影響玩家。
- `素材退還`（`upgrade_material_refund`）維持不變。
- 舊互動元件（已開啟的畫面帶舊類型的 custom_id）不另做相容處理，沿用現有驗證視為不合法輸入。
- 修改 `bak/` 內的備份檔與歷史 change document。

## Key Assumptions

- 移除兩種強化詞條不會明顯改變強化經濟；兩者全服只有 3 格，素材掉落已有 10 人使用。
- 等機率的 5 種抽選讓其他詞條出現率由 1/7 升為 1/5，上線後需觀察週期縮短與素材掉落的持有量是否進一步集中。

## Architecture Decisions

- 遷移放在 `src/database/schema.py`，由 `init_db()` 在 `_migrate_v2_columns` 之後、`commit` 之前呼叫新函式 `_migrate_removed_affix_types(db)`。SQL 為 `UPDATE gear_affixes SET affix_type='material_drop' WHERE affix_type IN ('upgrade_ap_refund','upgrade_cost_reduce')`。主鍵是 `(user_id, gear_type, slot_index)`，只改 `affix_type` 不會撞主鍵。沒有符合的列時是 no-op，可重複執行。
- 遷移在 bot 開始處理互動之前完成。`get_affix_bonuses` 以 `AFFIX_TYPES` 建字典，遇到未知類型會 `KeyError`，因此不另加執行期容錯。
- `affix_manager.AFFIX_TYPES` 是抽選池與合法類型的唯一來源。`random.choice(AFFIX_TYPES)` 維持等機率；`actions._VALID_AFFIX_TYPES` 與 `settlement` 的加成字典從它衍生，不需修改。
- 帶舊類型的舊 custom_id（`affix_slot_select`、`affix_clear`、`auto_affix_*`、`auto_affix_run`）沿用 `_VALID_AFFIX_TYPES` 的既有驗證，視為不合法輸入。
- `gear_manager._material_cost` 移除 `upgrade_cost_reduce_pct` 參數；`attempt_upgrade` 移除 AP 退還分支與回傳鍵 `ap_refunded`。`ap_refunded` 只有測試讀取。
- `player_manager.refund_ap` 只被 AP 退還分支呼叫，隨之刪除。
- 5 種類型乘 1-5 數值最多 25 組，等於 Discord 下拉上限，`ui_renderer` 的 25 組截斷對合法資料不再觸發。截斷程式與 `docs/discord/ui-renderer.md` 的截斷規則保留為防線，不在本次移除。
- `ui_renderer.AFFIX_TYPE_LABELS` 移除兩種類型。通知用 `.get(affix_type, affix_type)` 查名稱，`src/core/notification.py` 不需修改。

## Tasks

Dependency graph:

```
Task 1 (schema migration)        independent
Task 2 (gear/player effects)  -> Task 3 (AFFIX_TYPES) -> Task 4 (labels)
```

Parallel groups: Task 1 can run in parallel with the Task 2 -> 3 -> 4 chain. Task 3 and Task 4 both edit `tests/test_discord_commands.py`, so Task 4 runs after Task 3. Implementation order: 1, 2, 3, 4.

- [x] Task 1: Startup migration in `src/database/schema.py`. Add `_migrate_removed_affix_types(db)` and call it from `init_db()`. Tests in `tests/test_v2_schema_initialization.py`.
  - AC1: An existing DB with `upgrade_ap_refund` value 3 at slot 0 and `upgrade_cost_reduce` value 4 at slot 1 reads back as `material_drop` value 3 at slot 0 and `material_drop` value 4 at slot 1 after `init_db()`.
  - AC2: Rows of other affix types are unchanged after `init_db()`.
  - AC3: Calling `init_db()` twice does not raise and leaves the same rows.
- [x] Task 2: Remove upgrade effects in `src/managers/gear_manager.py` and `src/managers/player_manager.py`. Tests in `tests/test_gear_manager.py`. `refund_ap` has no tests, so no player-manager test file changes.
  - AC1: `_material_cost` has no reduction parameter; `get_upgrade_info` and `attempt_upgrade` costs equal the base mode cost.
  - AC2: `attempt_upgrade` never refunds AP and its result has no `ap_refunded` key.
  - AC3: `upgrade_material_refund` and `upgrade_success` behave as before.
  - AC4: `player_manager.refund_ap` no longer exists.
  - AC5: No test in `tests/test_gear_manager.py` inserts `upgrade_cost_reduce` or `upgrade_ap_refund`. The slot-0 fixture in `test_refund_not_triggered_on_failure` uses a remaining type.
- [x] Task 3: Shrink the draw pool in `src/managers/affix_manager.py`. Tests in `tests/test_affix_manager.py` and `tests/test_discord_commands.py`.
  - AC1: `AFFIX_TYPES` equals `("efficiency", "material_drop", "upgrade_success", "upgrade_material_refund", "cycle_time_reduce")`.
  - AC2: `extract_affix` and `auto_extract_affix` draw only from these 5 types.
  - AC3: `auto_extract_affix` with `target_affix_type="upgrade_ap_refund"` or `"upgrade_cost_reduce"` raises `ValueError`.
  - AC4: `get_affix_bonuses` returns exactly the 5 keys.
  - AC5: An `affix_clear` custom_id carrying a removed type clears nothing.
  - AC6: The `random.choice` mock in `tests/test_affix_manager.py` returns only remaining types (for example `cycle_time_reduce` in place of `upgrade_cost_reduce`).
- [x] Task 4: Remove labels in `src/cogs/ui_renderer.py`. Tests in `tests/test_discord_commands.py` and `tests/test_discord_notifications.py`.
  - AC1: `AFFIX_TYPE_LABELS` has exactly the 5 remaining types in the order 行動效率, 素材掉落, 強化成功, 素材退還, 週期縮短.
  - AC2: The auto-extract specific-effect dropdown lists exactly those 5 options.
  - AC3: Tests that used `upgrade_cost_reduce` or `upgrade_ap_refund` as sample data use a remaining type and still check the positive-sign rule.
  - AC4: The group-truncation test in `tests/test_discord_commands.py` builds 30 groups from the 5 remaining types with values 1-6, and its docstring states value 6 is out of range and exists only to exercise the guard. It asserts the 25 value 1-5 groups are kept, the 5 value-6 groups are excluded, and the placeholder ends with `另有 5 組未列出`. The excluded list contains no removed type.

## Plan Review Issues

- [x] Task 2 hides an ordering dependency on Task 3. `tests/test_gear_manager.py:814`, `:835`, and `:875` insert `upgrade_cost_reduce` / `upgrade_ap_refund` rows. `:875` (`test_refund_not_triggered_on_failure`) also checks `upgrade_material_refund`, so a worker can keep that insert and only drop the `ap_refunded` assertion. That passes after Task 2 and then raises `KeyError` in `get_affix_bonuses` (`src/managers/affix_manager.py:51-54`) once Task 3 shrinks `AFFIX_TYPES`. Add to Task 2: no test in `tests/test_gear_manager.py` inserts a removed type; replace the slot-0 fixture at `:875` with a remaining type.
- [x] Task 4 misses a test that breaks when labels shrink to 5. `tests/test_discord_commands.py:1494-1514` builds `len(AFFIX_TYPE_LABELS) x 4 + 2` groups (7 types give 30) and asserts 25 options after truncation. With 5 labels it builds 22 groups, so `assertEqual(len(values), 25)` fails. The excluded list at `:1508` also contains `"upgrade_ap_refund:4"`. Add a Task 4 AC: rebuild the fixture from the 5 types with more than 25 groups, keep the lowest-25 assertion, and drop the removed type from the excluded list.
- [x] Task 3 leaves stale removed-type test data. `tests/test_affix_manager.py:233` patches `random.choice` to return `"upgrade_cost_reduce"`. The test still passes after Task 3 because the choice is mocked, so the removed type stays in the suite. Add to Task 3: replace it with a remaining non-target type (for example `cycle_time_reduce`).
- [x] The dependency graph lets Task 3 and Task 4 edit `tests/test_discord_commands.py` at the same time. Task 3 AC5 adds an `affix_clear` test there. Task 4 edits `:1333-1359`, `:1475-1514`, and `:1632-1640` in the same file. Task 4 sits in the parallel group with Task 2, and Task 3 starts after Task 2, so the two can overlap. Add a `Task 3 -> Task 4` edge, or move Task 4 out of the first parallel group.
- [x] Task 2's test location is conditional ("the player-manager test file if `refund_ap` has tests"). `grep -rn refund_ap tests/` returns no hits, so no player-manager test file needs changes. State this directly. Then the worker does not search for a file or create one.
- [x] Task 4 AC4 (`:114`) cannot be met with legal data, so the earlier truncation issue is not resolved. Groups are `(affix_type, value)` pairs (`src/cogs/ui_renderer.py:517-523`). Values are 1-5 (`src/managers/affix_manager.py:28-29`, `src/cogs/actions.py:43`). Five types give at most 25 groups, so "more than 25 groups from the 5 remaining types" needs out-of-range values like 6. The truncation in `src/cogs/ui_renderer.py:825` and `docs/discord/ui-renderer.md:284` becomes unreachable for real data. Pick one and state it in the plan: (a) keep truncation as a guard and let the test use values above 5, saying so in AC4; or (b) replace the test with 5x5=25 groups that all appear with no `另有 n 組未列出` suffix, and mark `docs/discord/ui-renderer.md:284` as unreachable or remove it. AC4 must also say how to update the placeholder assertion at `tests/test_discord_commands.py:1516` (`另有 5 組未列出`).

## Review Issues

- [ ] [Minor] Task 2 AC2 and AC4 have no direct assertion. `tests/test_gear_manager.py:870-880` (`test_refund_not_triggered_on_failure`) only drops `assertFalse(result["ap_refunded"])`, and no test asserts `"ap_refunded" not in result` or `not hasattr(player_manager, "refund_ap")`. The refund branch itself is covered indirectly: `bonuses["upgrade_ap_refund"]` would raise `KeyError` from the 5-key dict (`src/managers/affix_manager.py:49`). Re-adding `"ap_refunded": False` to the return dict at `src/managers/gear_manager.py:285-293` passes the suite.

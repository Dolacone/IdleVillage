---
title: "工具詞條抽取機制"
status: Done
created: 2026-05-21
doc_type: change
last_reviewed: 2026-05-22
source_paths:
  - src/managers/affix_manager.py
  - src/database/schema.py
  - src/core/config.py
  - src/core/formula.py
  - src/core/settlement.py
  - src/managers/player_manager.py
  - src/managers/gear_manager.py
  - src/cogs/actions.py
  - src/cogs/ui_renderer.py
  - .env.example
  - docs/README.md
  - docs/discord/command-handler.md
  - docs/engine/cycle-engine.md
  - docs/engine/formula.md
  - docs/managers/affix-manager.md
  - docs/managers/gear-manager.md
  - tests/support.py
  - tests/test_affix_manager.py
  - tests/test_discord_commands.py
  - tests/test_engine_formula.py
  - tests/test_engine_settlement.py
  - tests/test_gear_manager.py
  - tests/test_v2_schema_initialization.py
scope: "為四種工具加入詞條系統：玩家可消耗素材抽取詞條，詞條在指定範圍內提供隨機加成，強化炸裂時清除。"
---

## Problem Statement

目前工具強化只有等級與保底兩個維度，缺乏橫向差異化。玩家在達到等級上限後沒有新的成長目標，也沒有可以驅動持續素材消耗的機制。

## Recommended Direction

在四種工具上加入詞條槽系統：
- 每 5 個工具等級解鎖 1 個槽位（Lv5/10/15/…）
- 抽取：消耗 1 個對應素材，從詞條池隨機抽一條（值 1–5% 均勻分布整數），填入第一個空槽
- 清除：消耗 3 個對應素材，清除指定槽的詞條
- 槽位全滿時，抽取按鈕鎖定，需先清除才能抽新的
- 鐵齒模式炸裂（等級歸零）時，該工具所有詞條全清

詞條類型（7 種，值均為 1–5% 整數）：

| 代碼 | 效果 |
| :--- | :--- |
| `efficiency` | 對應行動 output +X% |
| `material_drop` | 對應素材掉落率 +X%（相加後 min 1.0） |
| `upgrade_success` | 該工具強化成功率 +X% |
| `upgrade_cost_reduce` | 該工具強化素材消耗 -X%（floor 後不低於 1） |
| `upgrade_ap_refund` | 該工具強化成功時 X% 機率退還 1 AP |
| `upgrade_material_refund` | 該工具強化成功時 X% 機率退還消耗素材 |
| `cycle_time_reduce` | 行動週期縮短 X%（floor to seconds，套用在 ACTION_CYCLE_MINUTES） |

不採用方向 B（隨機值範圍 + 可覆蓋特定槽）原因：需要更複雜的 UI 顯示每槽具體數值與槽選擇邏輯，超出 MVP 範圍。
不採用方向 C（稀有度分層）原因：引入稀有度系統與現有平衡參數不相容。

## Clarifications

Q: 詞條抽取的觸發方式？
A: 獨立動作，消耗素材（無 AP 成本）。

Q: 每把工具可以有幾條詞條？
A: 根據工具等級解鎖槽位，每 5 級解鎖 1 槽。

Q: 詞條效果範疇？
A: 效率加成、素材掉落加成、強化成功率加成、強化 AP 退還機率、強化素材退還機率、強化素材成本降低、週期縮短。

Q: 槽位都填滿後，再次抽取的行為？
A: 需先清除才能抽新的，滿槽時抽取鎖定。

Q: 詞條數值是固定還是隨機範圍？
A: 隨機範圍，每個效果值為 1–5% 整數，均勻分布。

Q: 槽位解鎖門檻？
A: 每 5 級解鎖 1 槽（Lv5/10/15/…）。

Q: 單次抽取成本？
A: 抽詞條 = 1 個對應素材；清除詞條 = 3 個對應素材；均不消耗 AP。

Q: 鐵齒模式炸裂（等級歸零）後詞條如何處理？
A: 所有詞條全部清除。

## MVP Scope / Not Doing

MVP（本次）：
- 四種工具的詞條槽系統
- 抽取與清除 UI（整合至現有工具強化子選單）
- 詞條套用至 formula output、素材掉落、強化流程、週期引擎
- 鐵齒炸裂時清除詞條
- 管理員介面不納入（本次不實作 mgr_edit_affix）

Not Doing：
- 詞條稀有度分層
- 詞條跨工具繼承或移轉
- 詞條交易
- 管理員直接編輯詞條
- 詞條顯示於公告/通知頻道
- 主介面效率數字顯示 affix efficiency 加成（顯示 base gear+facility 效率，follow-up 處理）
- 管理員降低工具等級後強制清除超出槽位的詞條

## Architecture Decisions

### DB：新增 `gear_affixes` 表

```sql
CREATE TABLE IF NOT EXISTS gear_affixes (
    user_id    TEXT NOT NULL,
    gear_type  TEXT NOT NULL,   -- gathering / building / combat / research
    slot_index INTEGER NOT NULL, -- 0-based
    affix_type TEXT NOT NULL,
    value      INTEGER NOT NULL, -- 1–5
    PRIMARY KEY (user_id, gear_type, slot_index)
)
```

理由：affixes 是獨立行，新增/刪除不影響 players 資料列，查詢按 (user_id, gear_type) 索引即可。不在 players 表加欄位，避免 4 種工具 × N 槽 × 2 欄（type/value）炸列。

### 新增 `affix_manager.py`

所有詞條 CRUD 集中在此模組，其他模組透過 `get_affix_bonuses()` 取得彙總加成，不直接查表。

`get_affix_bonuses(db, user_id, gear_type) -> dict[str, int]`：
回傳 `{"efficiency": 0, "material_drop": 0, "upgrade_success": 0, "upgrade_cost_reduce": 0, "upgrade_ap_refund": 0, "upgrade_material_refund": 0, "cycle_time_reduce": 0}`，各欄位為所有同類型詞條 value 之和（同類可疊加）。

### 環境變數

| 變數 | 預設值 | 說明 |
| :--- | :--- | :--- |
| `AFFIX_SLOT_INTERVAL` | 5 | 每 N 工具等級解鎖 1 槽 |
| `AFFIX_EXTRACT_COST` | 1 | 抽取消耗對應素材數量 |
| `AFFIX_CLEAR_COST` | 3 | 清除消耗對應素材數量 |

### formula.compute_output 整合 efficiency 詞條

在 gear_bonus 計算後再疊加 affix efficiency：
```
bonus = ... + gear_level * gear_bonus_per + affix_efficiency/100.0
```
`compute_output` 簽名加入 `affix_efficiency_pct: int = 0` 參數；呼叫方（settlement `_run_one_cycle`）以 `get_affix_bonuses(db, user_id, action)["efficiency"]` 取值後傳入。

理由：formula 不做 DB 查詢，保持純計算函式，易於測試。詞條效果只對 player 當前 action 對應工具生效——查詢以 `action` 為 `gear_type`，切換行動後自動套用新工具的詞條。

### settlement 整合 material_drop 與 cycle_time

所有詞條查詢都以玩家當前 `action` 作為 `gear_type`，例如 `action == "gathering"` 時只查採集工具的詞條，其他工具的詞條不生效。

- `_effective_material_drop_rate`：加入 `affix_material_drop_pct` 參數，疊加 `affix_material_drop_pct/100.0`（min 1.0）。呼叫方從 `get_affix_bonuses(db, user_id, player["action"])` 取 `material_drop`。
- `cycle_time_reduce` 作用範圍：有效週期秒 = `floor(ACTION_CYCLE_MINUTES * 60 * (1 - cycle_time_reduce/100))`，最低 60 秒。此函式抽取為 `_effective_cycle_seconds(cycle_time_reduce_pct)` 並用於：
  1. `change_action` 設定 completion_time（用新行動的工具 affixes）
  2. `settle_complete_cycles` 補算每次推進 completion_time（用玩家當前 action 的 affixes）
  3. partial ratio 計算（`elapsed / effective_cycle_seconds`，同上）
  全部統一呼叫 `get_affix_bonuses(db, user_id, player["action"])` 取 `cycle_time_reduce`。

### gear_manager 整合升級詞條

在 `attempt_upgrade` 中：
1. 讀取 affix bonuses。
2. `material_cost` 先 `_material_cost()` 後乘以 `(1 - upgrade_cost_reduce/100)`，floor，最低 1。
3. `_compute_rate()` 的結果再加 `upgrade_success/100.0`，min 1.0。
4. 強化成功後：`random() < upgrade_ap_refund/100` 則退還 1 AP（呼叫 `player_manager.refund_ap(db, user_id, 1, now)`）；`random() < upgrade_material_refund/100` 則退還已消耗素材（呼叫 `player_manager.add_material()`）。
5. risky 失敗後：呼叫 `affix_manager.clear_all_affixes(db, user_id, gear_type, now)`。

AP refund 透過 `player_manager.refund_ap(db, user_id, amount, now)` 實作（Task 4 同步在 `player_manager.py` 新增此函式）：`ap_full_time = max(ap_full_time - amount * AP_RECOVERY_MINUTES, now)`。此函式屬 player_manager 負責，Task 4 涉及 gear_manager + player_manager 兩個 source files，符合 2-file 限制。

`get_upgrade_info` 同步回傳詞條調整後的 cost 與 rate，供 UI 顯示。

### UI 整合

在現有工具強化子選單（`open_gear_upgrade` 觸發）下方新增詞條區塊：
- 顯示所有已解鎖槽位與當前詞條（或「空槽」）。
- 「抽取詞條」按鈕：`extract_affix:{gear_type}`，滿槽時 disabled。
- 「清除」按鈕：`clear_affix:{gear_type}:{slot_index}`，空槽時 hidden（不渲染）。

互動路由新增至 `actions.py`。`_render_gear` 查詢 `affix_manager.get_affixes()` 與 `affix_manager.slot_count()` 後傳入 renderer，renderer 只負責純渲染。

主介面（`build_main_embed`）不顯示 affix efficiency 加成數字（顯示 base gear+facility 效率）——納入 Not Doing，follow-up 再處理。

## Tasks

- [x] Task 1: DB schema + env vars — 新增 `gear_affixes` 表至 `_create_v2_tables`；新增 `AFFIX_SLOT_INTERVAL`, `AFFIX_EXTRACT_COST`, `AFFIX_CLEAR_COST` 至 `config.py` 與 `.env.example`；更新 `docs/engine/formula.md` 環境變數清單；測試：`test_v2_schema_initialization.py` 驗證表存在、`test_v2_config_validation.py` 驗證三個新 key
- [x] Task 2: `affix_manager.py` — 實作 `slot_count`, `get_affixes`, `get_affix_bonuses`, `extract_affix`, `clear_affix`, `clear_all_affixes`；邊界驗證：gear_level < AFFIX_SLOT_INTERVAL 時 extract 拒絕、slot_index 超出已解鎖範圍時 clear 拒絕、slot 未填時 clear 拒絕、素材不足拒絕、滿槽拒絕；affix_type/value/gear_type 驗證在 manager 層；測試：`tests/test_affix_manager.py`（上述所有邊界 + bonuses 彙總）
- [x] Task 3: formula + settlement 整合 — `compute_output` 加入 `affix_efficiency_pct: int = 0` 參數；settlement `_run_one_cycle` 呼叫前查 affix_manager 傳入；`_effective_material_drop_rate` 加入 `affix_material_drop_pct`；抽取 `_effective_cycle_seconds(cycle_time_reduce_pct)` 並套用至 `change_action`、`settle_complete_cycles` 補算每次推進、partial ratio 三處；cycle-engine SSOT 已在 plan 階段更新，code 階段驗證實作一致即可；測試：更新 `test_engine_formula.py`、`test_engine_settlement.py`（含 cycle_time affix 一致性測試）
- [x] Task 4: gear_manager + player_manager 整合 — `player_manager.py` 新增 `refund_ap(db, user_id, amount, now)`；`attempt_upgrade` 套用 upgrade_cost_reduce/upgrade_success/upgrade_ap_refund/upgrade_material_refund；risky 失敗後呼叫 `clear_all_affixes`；`get_upgrade_info` 回傳詞條調整後的 cost/rate；測試：更新 `test_gear_manager.py`（各 affix 效果、refund 機率 mock、risky 失敗後詞條清除）
- [x] Task 5: UI — `actions.py` 的 `_render_gear` 呼叫 `affix_manager.get_affixes()` 與 `slot_count()` 並傳入 renderer；`ui_renderer.py` 新增詞條槽顯示與 extract/clear 元件（滿槽 extract disabled、空槽 clear hidden）；`actions.py` 新增 `extract_affix:{gear_type}` 與 `clear_affix:{gear_type}:{slot_index}` 路由；更新 `docs/discord/command-handler.md`；測試：更新 `test_discord_commands.py`（路由驗證、滿槽/空槽邊界）

## Key Assumptions

- 同類型詞條可疊加（多條 efficiency 加成直接相加）；上限由槽位數量自然限制。
- `cycle_time_reduce` 影響所有週期計算（change_action、補算、partial ratio），透過 `_effective_cycle_seconds` 統一實作。
- 管理員直接降低工具等級後，已超出解鎖槽位的詞條繼續生效（管理員操作邊界，不做強制清除）。
- affix bonuses 不對 burst 的三次結算做特殊處理（cycle time 不影響 burst，efficiency/material_drop 正常套用）。
- 主介面效率數字不顯示 affix efficiency 加成（Not Doing）。

## Review Issues

- [x] [Major] `settle_burst` 未套用目前行動工具的詞條。修正：`settle_burst` 現在在迴圈前查 `affix_manager.get_affix_bonuses(db, user_id, player["action"])` 並傳入 `_run_one_cycle`。
- [x] [Major] `source_paths` 與實際 change diff 不一致。修正：已更新 source_paths 移除 `test_v2_config_validation.py`，補入 `.env.example`、`docs/README.md`、`docs/discord/command-handler.md`、`docs/engine/cycle-engine.md`、`docs/engine/formula.md`、`docs/managers/affix-manager.md`、`docs/managers/gear-manager.md`。

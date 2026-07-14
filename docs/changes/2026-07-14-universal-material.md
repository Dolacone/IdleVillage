---
title: "新素材：萬能素材"
status: Draft
created: 2026-07-14
doc_type: change
last_reviewed: 2026-07-14
source_paths: []
scope: "Tracks introduction of the universal material (萬能素材) placeholder and its use as a shortfall fallback during gear upgrade."
---

## Problem Statement

新增第 5 種素材「萬能素材」：目前無法透過任何管道獲得（僅作為未來機制的佔位），但規則已生效：可作為任意工具類型的素材使用。玩家在強化工具時，若原本工具類型的素材不足，優先扣除該類型素材，不足的差額由萬能素材補足；若加上萬能素材仍舊不足，則無法進行該次強化。

## Recommended Direction

新增 `materials_universal` 欄位（`players` 表）。`player-manager` 既有的 `addMaterial`/`spendMaterial`/`setMaterial`/`getMaterial` 皆以 `ACTION_MATERIAL_COL`（`gathering`/`building`/`combat`/`research` 四種行動類型）為 key 查表；萬能素材不對應任何行動類型，若讓 `type` 參數多收一個 `"universal"` 值，會與 `formula.py` 中同結構的 `ACTION_GEAR_COL`/`ACTION_FACILITY_BUILDING`（過去 offering 行動移除時已證實此類共用字典誤加非行動 key 會造成 `KeyError`）產生同樣的耦合風險。因此改為新增四個獨立介面：`getUniversalMaterial`/`addUniversalMaterial`/`spendUniversalMaterial`/`setUniversalMaterial`，直接操作 `materials_universal` 欄位，不經過 `ACTION_MATERIAL_COL`。強化流程（`gear-manager.attempt_upgrade` / `get_upgrade_info`）的素材檢查與扣除邏輯改為：

```
shortfall = max(0, material_cost - materials[gear_type])
若 materials_universal < shortfall → 素材不足，無法強化（同現有行為，不扣除任何資源）
否則：
  materials[gear_type] -= min(material_cost, materials[gear_type])
  materials_universal -= shortfall
```

範圍僅限強化工具（三種模式：標準/墊檔/鐵齒）的素材消耗；獻祭素材（`sacrifice_material`）與詞條抽取/清除（`affix-manager`）維持現有素材規則，不吃萬能素材（使用者需求明確指向「強化」，其餘消耗行為不在範圍內，避免未經確認的規則擴張）。

素材掉落（`player-manager.md` 素材系統）與獲取管道維持不變，萬能素材不加入任何掉落表；目前僅能透過管理員介面（`/idlevillage-manager` 編輯素材）設定，做為佔位驗證用途。

### 排除的替代方案

- 萬能素材套用到所有素材消耗行為（強化、獻祭、詞條抽取/清除）：使用者需求明確僅提及「強化」，擴大範圍屬未確認假設，且會使獻祭/詞條的素材語意複雜化，故排除。
- 提供玩家手動「兌換」萬能素材為指定類型的操作（而非強化時自動補差額）：使用者描述的是強化時「自動使用」以補差額，而非手動兌換介面；手動兌換是額外未要求的互動流程，故排除。

## Clarifications

<!-- Q: 萬能素材是否套用到獻祭素材與詞條抽取/清除的素材消耗？ / A: 不套用，僅限強化工具（標準/墊檔/鐵齒）三種模式。 — resolved during refine stage -->
<!-- Q: 萬能素材目前如何取得？ / A: 目前無任何掉落或產出管道，僅能由管理員透過 /idlevillage-manager 編輯素材數量設定，作為佔位驗證用途。 — resolved during refine stage -->

## MVP Scope / Not Doing

- 範圍內：
  - `players` 表新增 `materials_universal` 欄位（DB schema）。
  - `player-manager` 新增 `getUniversalMaterial`/`addUniversalMaterial`/`spendUniversalMaterial`/`setUniversalMaterial` 四個獨立介面。
  - `gear-manager.attempt_upgrade` 與 `get_upgrade_info` 的素材檢查/扣除邏輯改為「本類型優先、差額用萬能素材補足」。
  - `/idlevillage` 主介面與工具強化子選單 Embed 顯示萬能素材持有量。
  - `/idlevillage-manager` 玩家管理員介面新增萬能素材的顯示與編輯欄位。
  - 對應文件更新：`docs/db-schema.md`、`docs/managers/player-manager.md`、`docs/managers/gear-manager.md`、`docs/discord/ui-renderer.md`、`docs/discord/command-handler.md`。
- 範圍外：
  - 萬能素材的任何獲取/掉落管道（保持「目前無法獲得」的佔位狀態）。
  - 獻祭素材、詞條抽取/清除套用萬能素材。
  - 玩家自助的素材兌換介面。

## Key Assumptions

- 「強化」僅指 `gear-manager` 的 `attempt_upgrade`（標準/墊檔/鐵齒三種模式），不含 `sacrifice_material`。
- 萬能素材佔位期間僅能由管理員透過既有 `setMaterial` 管理介面寫入，不需要額外的獲取管道設計。
- 素材不足時「無法進行動作」沿用現有行為：不消耗任何 AP 或素材，維持前置檢查即拒絕的模式。

## Architecture Decisions

1. 萬能素材不併入 `ACTION_MATERIAL_COL`（及同結構的 `ACTION_GEAR_COL`/`ACTION_FACILITY_BUILDING`）。這些字典的 key 集合等於四種行動類型，`gear-manager`/`player-manager`/`affix-manager`/`cogs/actions.py` 多處直接以 `[gear_type]` 查表；曾在 offering 行動移除時因這類共用字典殘留非行動 key 導致 `KeyError`（見 `docs/changes/2026-07-14-remove-offering-system.md` Review Issues）。萬能素材改用獨立的 `getUniversalMaterial`/`addUniversalMaterial`/`spendUniversalMaterial`/`setUniversalMaterial` 介面，直接操作 `materials_universal` 欄位，避免同類風險。
2. `attempt_upgrade`/`get_upgrade_info` 的扣除順序固定「本類型優先，差額用萬能素材」，不提供玩家選擇扣除來源的選項——使用者描述的是「不足時才用萬能素材補」，非可選策略，維持單一、可預期的行為。
3. `upgrade_material_refund` 詞條觸發時，退還的素材固定計入該類型本身（不追蹤本次消耗中来自萬能素材的比例並按比例退還）。追蹤來源比例需要在 `attempt_upgrade` 回傳值與呼叫端之間傳遞額外欄位，且僅影響一個機率性、每次至多 1 個素材差距的邊角情況，複雜度不成比例，故不做。
4. 依賴順序：schema → player-manager 介面 → gear-manager 消耗邏輯 → UI 顯示 → 管理員 Modal。UI 與管理員介面依賴 gear-manager 回傳的 `universal_materials` 欄位，故排在其後。

## Tasks

- [ ] Task 1: DB schema — 新增 `materials_universal` 欄位
  - Files: `src/database/schema.py`
  - Tests: 既有 `tests/test_v2_schema_initialization.py` 等 schema 測試套件需維持通過（新欄位有 DEFAULT 0，不需額外 fixture 變更）
  - Depends on: 無
  - Acceptance: `players` 建表 SQL 含 `materials_universal INTEGER NOT NULL DEFAULT 0`；既有測試套件全數通過

- [ ] Task 2: player-manager 萬能素材介面
  - Files: `src/managers/player_manager.py`
  - Tests: 於 `tests/test_gear_manager.py`（現有 player_manager 素材相關測試所在檔案）新增涵蓋 `get_universal_material`/`add_universal_material`/`spend_universal_material`（餘額不足時回傳 False，不扣除）/`set_universal_material` 的測試案例
  - Depends on: Task 1
  - Acceptance: 四個函式皆直接操作 `materials_universal` 欄位，不經過 `ACTION_MATERIAL_COL`；`spend_universal_material` 餘額不足時回傳 False 且不扣除；測試通過

- [ ] Task 3: gear-manager 強化素材檢查/扣除邏輯改為萬能素材補足
  - Files: `src/managers/gear_manager.py`
  - Tests: 於 `tests/test_gear_manager.py` 新增測試涵蓋：(a) 本類型素材足夠時不動用萬能素材、(b) 本類型不足但萬能素材補足後可強化且兩者正確扣除、(c) 兩者相加仍不足時 `can_attempt=False` 且 `attempt_upgrade` raise ValueError、不扣除任何資源、(d) `get_upgrade_info` 回傳 `universal_materials` 欄位
  - Depends on: Task 2
  - Acceptance: `attempt_upgrade` 與 `get_upgrade_info` 的前置檢查與扣除順序符合 Architecture Decision #2；`upgrade_material_refund` 退還邏輯不變（固定退還至本類型）；既有標準/墊檔/鐵齒測試不受影響且全數通過

- [ ] Task 4: UI 顯示萬能素材（主介面 + 工具強化子選單）
  - Files: `src/cogs/ui_renderer.py`
  - Tests: 於 `tests/test_discord_commands.py`（現有 UI embed 渲染測試所在檔案）新增涵蓋個人資訊素材列包含萬能素材數量、工具強化子選單持有素材列包含萬能素材數量的測試案例
  - Depends on: Task 3
  - Acceptance: `build_main_embed` 輸出的素材列格式為 `🌾 {n} | 🔨 {n} | ⚔️ {n} | 🔬 {n} | 🌟 {n}`；`build_gear_embed` 持有素材列格式為 `持有素材：{n} 個 ｜ 🌟 萬能素材：{n} 個`；既有 UI 測試不受影響且全數通過

- [ ] Task 5: 管理員介面新增萬能素材編輯欄位
  - Files: `src/cogs/player_manager_cog.py`, `src/cogs/ui_renderer.py`
  - Tests: 於 `tests/test_player_manager_cog.py` 更新/新增測試，涵蓋 `_fetch_player_data` 含 `materials_universal`、`mgr_modal_material` 提交含萬能素材欄位時正確呼叫 `set_universal_material`、`build_manager_embed` 素材數量欄位含萬能素材
  - Depends on: Task 2, Task 4
  - Acceptance: 「編輯素材數量」Modal 為 5 個欄位（採集/建設/戰鬥/研究/萬能）；`mgr_modal_material` 驗證通過後呼叫 `set_material()` × 4 + `set_universal_material()` × 1；`build_manager_embed` 素材數量欄位格式為 `採集 {n} ｜ 建設 {n} ｜ 戰鬥 {n} ｜ 研究 {n} ｜ 萬能 {n}`；既有管理員介面測試不受影響且全數通過

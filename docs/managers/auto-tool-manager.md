---
title: "Module: auto-tool-manager"
doc_type: module
last_reviewed: 2026-07-20
source_paths:
  - src/managers/auto_tool_manager.py
---

# Module: auto-tool-manager

管理「自動工具」：玩家在手動行動之外，可對閒置工具掛載背景行動流。四種工具（採集/建設/戰鬥/研究）每一種在任一時刻只處於三態之一：手動行動、自動工具、閒置。運行中的自動工具由 `engine/cycle-engine.md` 的 Watcher 與開介面補算流程結算，效果完全等同手動行動（見 `engine/action-resolver.md`）。

## 狀態表 `player_auto_tools`

一列代表一個運行中的自動工具，主鍵 `(user_id, tool_type)`（天然保證同一工具不會有兩個自動工具）。欄位見 `db-schema.md`。

| 欄位 | 說明 |
| :--- | :--- |
| `tool_type` | 工具類型（`gathering`/`building`/`combat`/`research`） |
| `action_target` | 建設目標建築（僅 `building`）；研究固定 `research_lab`；採集/戰鬥為 null |
| `completion_time` | 下次產出結算時間（產出時鐘） |
| `last_update_time` | 上次產出結算時間 |
| `expires_at` | 停止時間（玩家自訂剩餘時間；超過即結束並釋放工具） |
| `started_at` | 啟動時間 |
| `next_material_time` | 下次扣素材時間（素材時鐘）；nullable，NULL 代表舊預付列（見結算歸屬） |

## 隨用隨扣素材與時間調整

素材採「隨用隨扣（pay-as-you-go）」，與剩餘時間脫鉤：

- 啟動即扣 1 個「該工具專屬素材」（涵蓋第一個小時，t=0），之後每經過 `AUTO_TOOL_SECONDS_PER_MATERIAL` 秒（預設 1 小時）由結算再扣 1 個（`next_material_time` 時鐘）。不可用萬能素材替代。
- 某個素材 tick 要扣時手上沒有該素材 → 立即停止並釋放工具（進行中的未完成產出週期丟棄，不做 partial）。
- 剩餘運行時間（`expires_at`）由玩家自訂，與素材無關，上限固定 `AUTO_TOOL_MAX_HOURS`（預設 24 小時）。加/減時間完全不扣也不退素材。實際續航 = min(剩餘時間, 手上素材可撐的整點數)。
- 可加時數 `max_add = floor((cap_seconds − remaining_seconds) / seconds_per_material)`，`remaining_seconds = max(0, expires_at − now)`；`cap_seconds = AUTO_TOOL_MAX_HOURS × per`。首次啟動 `remaining = 0` → `max_add = AUTO_TOOL_MAX_HOURS`（1~24）。
  - 例：剩餘 23:01 → `max_add = 0`（不可再加）；剩餘 0:01 → `max_add = 23`（最多加到 23:01）。
- 可減時數以 1 小時為單位；`max_subtract = ceil(remaining_seconds / per)`，最大的那一階會把剩餘時間清空 → 停止工具（減到底即停）。例：剩餘 01:01 → `max_subtract = 2`（減 1 到 00:01；減 2 即停止）。

## 互斥（雙向）

- 啟動自動工具 T：T ≠ 玩家當前 `players.action` 且 T 不在 `player_auto_tools`。
- 設定手動行動 T（`core/settlement.change_action`）：T 不在 `player_auto_tools`（守衛在 `change_action`，非 `player_manager`）。
- 序列化：`start`/`add_time`/`subtract_time` 在守衛讀取前先發 `BEGIN IMMEDIATE` 取寫鎖，`start` 以條件式 `INSERT ... WHERE NOT EXISTS(...) AND (players.action IS NOT ?)` 寫入，`change_action` 以條件式 `UPDATE ... WHERE NOT EXISTS(...)` 寫入。條件在取得寫鎖後對已提交狀態求值，故並發的手動/自動指派不會同時成功。

## 操作介面

- `start(db, user_id, tool_type, hours, action_target, now)` — 啟動；驗證閒置、`1 <= hours <= AUTO_TOOL_MAX_HOURS`、手上該素材 ≥ 1（只扣 1，t=0）；寫 `expires_at = now + hours×per`、`next_material_time = now + per`、`completion_time = now + effective_cycle_seconds`；不滿足 raise `ValueError`。
- `add_time(db, user_id, tool_type, hours, now)` — 加時間；`1 <= hours <= max_add_hours`；只調 `expires_at`，不碰素材。
- `subtract_time(db, user_id, tool_type, hours, now)` — 減時間；`hours >= 1`；`hours×per >= remaining` 則 `end()`（減到底即停），否則縮短 `expires_at`；不碰素材。
- `list_active(db, user_id)` / `get(db, user_id, tool_type)` / `get_active_tool_types(db, user_id)` / `is_active(db, user_id, tool_type)`。
- `get_idle_tools(db, user_id)` — 既非手動行動也非自動工具的工具清單。
- `max_add_hours(expires_at_str, now)` — 可加時數（`None` 表示新啟動 → `AUTO_TOOL_MAX_HOURS`）。
- `max_subtract_hours(expires_at_str, now)` — 可減時數 `ceil(remaining / per)`（最大階即停止）。
- `advance_cycle(db, user_id, tool_type, cycle_end_time, next_completion)` — 由結算推進產出時鐘。
- `advance_material_tick(db, user_id, tool_type, next_material_time)` — 由結算推進素材時鐘。
- `end(db, user_id, tool_type)` — 結束、釋放工具（刪列）。

不 import `core.settlement`（`settlement` 反向 import 本模組）；週期秒數取自 `core.formula.effective_cycle_seconds`。

## 結算歸屬

結算由 `core/settlement.settle_auto_tool_cycles` 執行，於 `BEGIN IMMEDIATE` 內把兩條獨立時鐘依時間先後交錯處理：

- 產出時鐘（`completion_time`，步進 `effective_cycle_seconds`）：每完整週期複用 action-resolver（見 `engine/action-resolver.md`）——扣村莊資源（資源不足 ×0.5 同規則）、產出分配、素材掉落（落在該工具素材）、關卡進度、村莊試煉貢獻（歸於該 `user_id`）、建築升級判定、通知。有效條件 `completion_time <= min(now, expires_at)`，受 `MAX_CYCLES_PER_SETTLEMENT` 限制。
- 素材時鐘（`next_material_time`，步進 `per`）：每個 tick 以條件式 UPDATE 扣 1 該工具素材；扣不到即 `end()` 停止（進行中週期丟棄，不做 partial）。有效條件 `next_material_time <= now` 且 `next_material_time < expires_at`（嚴格小於到期，避免到期整點多扣一個不會運行的小時）。
- 交錯規則：每輪取最早的有效事件；平手（同時刻）素材 tick 先（該小時素材先付、供該小時產出使用），故產出週期掉落的素材可即時支付緊接著的 tick（正回饋）。當最早事件是已達 cap 的產出週期時停止，留 backlog 給下次 sweep（不越過未結算產出去扣素材）。
- 舊列遷移：`next_material_time` 為 NULL 的舊預付列，剩餘時數視為已付清，回填為該列 `expires_at` 使素材 tick 永不觸發（不二次扣、不提早結束）。
- 收尾：未因扣不到素材而停止時，`now >= expires_at` 且已追平（無產出 backlog、無待處理素材 tick）才 `end`。不消耗 AP。

Watcher 掃描條件為 `completion_time <= now OR next_material_time <= now OR expires_at <= now`（見 `engine/cycle-engine.md`），確保素材 tick 與到期在背景也能及時觸發。

## 環境變數

| 變數 | 預設 | 說明 |
| :--- | :--- | :--- |
| `AUTO_TOOL_SECONDS_PER_MATERIAL` | 3600 | 每 1 素材涵蓋的運行秒數（＝素材 tick 間隔） |
| `AUTO_TOOL_MAX_HOURS` | 24 | 剩餘運行時間上限（小時） |

## Changelog

- 2026-07-20: 改為隨用隨扣：`start` 只扣 1 素材、新增 `next_material_time` 素材時鐘、每小時扣 1、扣不到即停；`refuel` 拆為 `add_time`/`subtract_time`（純調時間、不碰素材）；`max_add_materials`→`max_add_hours` 且新增 `max_subtract_hours`；結算改雙時鐘時間序合併；env `AUTO_TOOL_MAX_MATERIALS`→`AUTO_TOOL_MAX_HOURS`（6→24）。
- 2026-07-17: 新增模組。

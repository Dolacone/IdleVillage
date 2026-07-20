---
title: "Module: auto-tool-manager"
doc_type: module
last_reviewed: 2026-07-17
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
| `completion_time` | 下次結算時間 |
| `last_update_time` | 上次結算時間 |
| `expires_at` | 到期時間（超過即結束並釋放工具） |
| `started_at` | 啟動時間 |

## 啟動與延長

- 每 1 個「該工具專屬素材」= `AUTO_TOOL_SECONDS_PER_MATERIAL` 秒運行（預設 1 小時）。不可用萬能素材替代。
- 剩餘運行時間上限固定 `AUTO_TOOL_MAX_MATERIALS × AUTO_TOOL_SECONDS_PER_MATERIAL`（預設 6 小時）。
- 可補充素材數 `max_add = floor((cap_seconds − remaining_seconds) / seconds_per_material)`，`remaining_seconds = max(0, expires_at − now)`；`max_add >= 1` 才可補充/啟動。
  - 首次啟動 `remaining = 0` → `max_add = AUTO_TOOL_MAX_MATERIALS`（1~6）。
  - 例：剩餘 5:01 → `max_add = 0`（不可補充）；剩餘 0:01 → `max_add = 5`（最多補到 5:01）。投入 X 後 `expires_at += X × per`，因 `X <= max_add` 故必不超過上限。

## 互斥（雙向）

- 啟動自動工具 T：T ≠ 玩家當前 `players.action` 且 T 不在 `player_auto_tools`。
- 設定手動行動 T（`core/settlement.change_action`）：T 不在 `player_auto_tools`（守衛在 `change_action`，非 `player_manager`）。
- 序列化：`start` 以條件式 `INSERT ... WHERE NOT EXISTS(...) AND (players.action IS NOT ?)` 寫入，`change_action` 以條件式 `UPDATE ... WHERE NOT EXISTS(...)` 寫入。條件在取得寫鎖後對已提交狀態求值，故並發的手動/自動指派不會同時成功。

## 操作介面

- `start(db, user_id, tool_type, count, action_target, now)` — 啟動；驗證閒置、素材足夠（只扣自身素材）、`count <= max_add`；不滿足 raise `ValueError`。
- `refuel(db, user_id, tool_type, count, now)` — 延長；`count <= max_add`；只扣自身素材；不滿足 raise `ValueError`。
- `list_active(db, user_id)` / `get(db, user_id, tool_type)` / `get_active_tool_types(db, user_id)` / `is_active(db, user_id, tool_type)`。
- `get_idle_tools(db, user_id)` — 既非手動行動也非自動工具的工具清單。
- `max_add_materials(expires_at_str, now)` — 可補充素材數（`None` 表示新啟動）。
- `advance_cycle(db, user_id, tool_type, cycle_end_time, next_completion)` — 由結算推進計時。
- `end(db, user_id, tool_type)` — 到期結束、釋放工具（刪列）。

不 import `core.settlement`（`settlement` 反向 import 本模組）；週期秒數取自 `core.formula.effective_cycle_seconds`。

## 結算歸屬

自動工具每完整週期複用 action-resolver（見 `engine/action-resolver.md`）：扣村莊資源（資源不足 ×0.5 同規則）、產出分配、素材掉落（落在該工具素材）、關卡進度、村莊試煉貢獻（歸於該 `user_id`）、建築升級判定、通知。到期只結算 `completion_time <= min(now, expires_at)` 的完整週期，進行中的未完成週期不做 partial。不消耗 AP。

## 環境變數

| 變數 | 預設 | 說明 |
| :--- | :--- | :--- |
| `AUTO_TOOL_SECONDS_PER_MATERIAL` | 3600 | 每 1 素材換算的運行秒數 |
| `AUTO_TOOL_MAX_MATERIALS` | 6 | 剩餘運行時間上限（以素材/小時計） |

## Changelog

- 2026-07-17: 新增模組。

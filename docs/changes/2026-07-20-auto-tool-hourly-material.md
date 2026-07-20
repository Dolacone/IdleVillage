---
title: "自動工具改版：隨用隨扣素材與可調剩餘時間"
status: Draft
created: 2026-07-20
doc_type: change
last_reviewed: 2026-07-20
source_paths:
  - src/managers/auto_tool_manager.py
  - src/core/settlement.py
  - src/core/engine.py
  - src/core/config.py
  - src/cogs/ui_renderer.py
  - src/cogs/actions.py
  - src/database/schema.py
scope: "Tracks the auto-tool revamp: material is spent hourly (pay-as-you-go) instead of prepaid, remaining time is player-set and adjustable, and the cap rises from 6h to 24h."
---

## Problem Statement

現有自動工具（見 `docs/managers/auto-tool-manager.md`）採「預付」模型：啟動時一次扣 1~6 個該工具素材，素材數 = 運行時數，`expires_at = now + count×1h`，上限 6h。缺點：玩家必須一次押上全部素材，無法途中調整運行時間，且上限偏低。

需求把資源模型改為「隨用隨扣」：

- 最長運行時間由 6h 提高到 24h。
- 啟動時不再一次預扣全部素材；改為每 1 小時扣 1 個該工具素材。
- 某個小時要扣素材時手上沒有該素材 → 自動中斷、釋放工具。
- 玩家可隨時增加或減少剩餘時間（以 1 小時為單位），上限 24h；減到底即停止。

## Recommended Direction

方向 A（採用）：延伸現有 auto-tool 子系統，改為雙時鐘。

- 保留 `expires_at` 語意為「工具停止時間」，但改為玩家自訂、與素材脫鉤（加/減時間只改 `expires_at`，不碰素材）。
- 新增獨立的「素材扣除時鐘」欄位 `next_material_time`：下次扣素材時間，序列為 `started_at + N × SECONDS_PER_MATERIAL`（N=0,1,2...），即 t=0 啟動瞬間扣第一個。
- `start` 不再預扣全部，只在 t=0 扣第一個素材（並要求手上 ≥ 1）。
- `refuel` 拆為「加時間」與「減時間」兩路，純調 `expires_at`；減到 remaining ≤ 0 即 `end`。
- 結算時 auto-tool 掃描除了推進產出週期，也在 `next_material_time <= now` 時扣 1 素材；扣不到 → `end`。產出週期與素材 tick 為兩條獨立時鐘，於結算時依時間先後交錯處理（見架構決策，plan 階段補完）。

理由：與現有 auto-tool 子系統、cycle-engine 掃描流程、`BEGIN IMMEDIATE` 序列化與固定結算順序（原架構決策 #7/#8）一致，不動產出週期模型，變更面可控。

### 排除的替代方案

- 方向 B：把素材扣除綁進產出週期（每個產出週期扣素材）。否決：產出週期 `effective_cycle_seconds` 可遠短於 1h，且受 `cycle_time_reduce` 影響會漂移，與「每小時扣一個」不符。
- 方向 C：用單一 `completion_time` 同時當產出與素材時鐘（把週期設成 1h）。否決：破壞既有 `effective_cycle_seconds` 產出模型，牽動全域，違反最小變更。

## Clarifications

<!-- Q: 調整剩餘時間（加/減）是否涉及素材扣除或退還？ / A: 完全不涉及素材；素材只在每小時 tick 扣。加/減只改 expires_at。 -->
<!-- Q: 第一次扣素材時機、啟動是否需要素材門檻？ / A: 啟動瞬間即開始計時，計時瞬間扣第一次素材（實質 = 啟動即扣 1）；start 檢查手上 ≥ 1 素材才可啟動。 -->
<!-- Q: 每小時素材 tick 的時鐘如何計算？ / A: 從 started_at 起算每 SECONDS_PER_MATERIAL(1h) 一次，t=0 起。與產出結算週期為獨立雙時鐘。 -->
<!-- Q: 如何停止？素材耗盡/主動停止時進行中半週期怎麼處理？ / A: 減時間到底即停，不設獨立停止鈕；素材耗盡自動中斷。進行中未完成的產出週期一律丟棄，不做 partial。 -->

## MVP Scope / Not Doing

範圍內：
- `player_auto_tools` 新增 `next_material_time` 欄位（素材扣除時鐘）。
- `auto_tool_manager`：`start` 改為 t=0 扣 1（要求 ≥1）、設 `expires_at = now + hours×per`、設 `next_material_time = started_at + per`；`refuel` 拆為加/減時間（只調 `expires_at`）；新增/調整 `max_add`（上限 24h）與減時間邊界計算；素材 tick 扣除與耗盡 `end`。
- `settlement`：auto-tool 結算改為依時間先後交錯處理「產出週期」與「素材 tick」，素材 tick 扣不到即 `end`（進行中週期丟棄）。
- `config`：`AUTO_TOOL_MAX_MATERIALS`（6）語意/命名調整為「上限小時數」= 24（命名是否改為 `AUTO_TOOL_MAX_HOURS` 於 plan 決定）。
- UI：start 子介面由「選素材數 1~6」改為「選初始運行時數 1~24」；運行中列顯示剩餘到期 + 手上素材可撐時數；加時間 / 減時間下拉。
- 文件更新：`auto-tool-manager.md`、`db-schema.md`、`cycle-engine.md`、`formula.md`（env）、`ui-renderer.md`、`command-handler.md`。

範圍外：
- 不改互斥（雙向）、`BEGIN IMMEDIATE` 序列化、固定結算順序等既有架構決策的核心邏輯（沿用）。
- 不改產出週期 / `effective_cycle_seconds` / action-resolver 產出模型。
- 不新增公開通知類型；中斷不做 partial 半週期。
- 萬能素材仍不可替代（沿用）。

## Architecture Decisions
<!-- plan 階段補完（雙時鐘交錯結算演算法、schema 欄位新增方式、env 命名、UI 邊界計算、序列化沿用） -->

## Key Assumptions

- 「每小時扣素材」的「小時」= `SECONDS_PER_MATERIAL`（預設 3600），與產出週期無關；沿用同一常數。
- 素材扣除與產出週期於結算時依時間先後交錯：某產出週期若在素材 tick 之前完成並掉落該工具素材，可用於支付緊接著的素材 tick（正回饋，沿用既有「素材掉落可延長」為預期行為）。
- 素材耗盡或減時間到底而停止時，`now >= 停止時間` 才 `end`；進行中未完成的產出週期一律丟棄，不做 partial（比照現有到期行為）。
- start 需手上 ≥ 1 素材，t=0 扣掉它；`next_material_time` 起始為 `started_at + per`。
- 加/減時間以 1 小時為單位；加時間上限使 `remaining ≤ 24h`；減時間使 `remaining ≤ 0` 時即停止工具。

## Tasks
<!-- plan 階段補完 -->
- [ ] Task 1: ...

## Review Issues
- [ ] Issue 1: ...

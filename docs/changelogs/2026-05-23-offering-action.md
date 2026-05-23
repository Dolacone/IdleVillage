---
title: "奉獻行動（Offering Action）"
status: Ready-to-implement
created: 2026-05-23
doc_type: change
last_reviewed: 2026-05-23
source_paths: []
scope: "新增第 5 種行動類型「奉獻」，消耗村莊資源換取全村集體素材獎勵。"
---

## Problem Statement

現有 4 種行動（採集/建設/戰鬥/研究）均為個人產出導向，缺乏社群合作互動感。玩家沒有動機協調行動或為集體利益犧牲個人收益。

## Recommended Direction

新增第 5 種行動類型「奉獻」（stored value: `offering`）。玩家選擇此行動時同時選定消耗資源類型（食物/木頭/研究點）。每個結算週期自動消耗村莊資源池中指定資源，消耗量等於玩家四種行動類型的產出合計。全村累積消耗達到閾值（`OFFERING_THRESHOLD_PER_PLAYER × 總玩家數`）後，所有玩家的四種素材各 +1，累積值歸零重新計算。

選擇方向 A（新行動類型）而非 B（AP 消耗即時行動），因為行動類型模型已成熟，讓奉獻佔用行動槽位能產生「犧牲產出換集體利益」的真實張力。方向 B 不佔槽位，機制張力較弱。

## Clarifications

Q: 參考數據（食物 61k、木頭 330k、研究點 106k）是村莊餘額還是歷史累積產出？
A: 假設為現有村莊餘額（用於驗證數值合理性）。

Q: 玩家可以每次自由選擇消耗哪種物資嗎？
A: 是，每次設定行動時選擇，儲存於 `action_target`。

Q: 達標後累積值清空還是繼續往下一倍數推進？
A: 清空歸零，下輪重新累積。

Q: 活躍玩家數量？
A: 目前 12 位活躍玩家。

Q: 基準值如何設定？
A: `OFFERING_THRESHOLD_PER_PLAYER = 1000`，12 人閾值 = 12,000。以平均 4 人參與估算（每人每週期貢獻 ~95），約 31 cycles（≈5 小時）觸發一次。

## MVP Scope / Not Doing

做：
- 奉獻行動結算（消耗資源、更新 accumulator）
- 閾值觸發（全員素材 +1、歸零）
- Dashboard 顯示累積進度
- 玩家主介面新增奉獻選項 + 資源選擇 dropdown
- 觸發時發送 Public 通知

不做：
- 奉獻行動的素材掉落（同現有邏輯：無產出行動不掉落素材）
- 玩家個人奉獻貢獻記錄（本版不追蹤）
- 奉獻量依資源類型有不同係數（統一用 sum-of-4-outputs）

## Architecture Decisions

1. **Accumulator 儲存位置**：在 `village_state` 加一欄 `offering_accumulator INTEGER NOT NULL DEFAULT 0`。全局單值，與現有全局狀態管理模式一致，不需新表。

2. **消耗量計算**：`offering_cost = Σ floor(output_type)` for 4 action types，每型別使用各自的 gear/facility bonus。消耗量隨玩家成長自然擴大，高等玩家貢獻更多。

3. **資源選擇儲存**：reuse `action_target` field（值：`food` / `wood` / `knowledge`）。與 building 的 `action_target` 用途類似，互斥於 action 類型，不需新欄位。

4. **觸發時機**：每次奉獻結算後立即檢查。與現有關卡通關、建築升級觸發模式一致（結算瞬間判斷）。

5. **Shortage 處理**：若選定資源不足，以實際可扣除量計入 accumulator（`actual = min(balance, offering_cost)`）。奉獻無產出，shortage_flag 不影響任何 output。基礎 FOOD_COST 仍照常扣除（不計入 accumulator）。

6. **全員素材獎勵**：直接以 SQL `UPDATE players SET materials_* = materials_* + 1` 一次完成，不逐一呼叫 player_manager。

7. **閾值分母**：取 DB `players` 表的總行數（所有已注冊玩家），而非活躍玩家數，避免被刷人數操縱。

## Tasks

- [x] Task 1: DB schema + env var — 在 `village_state` 加 `offering_accumulator`，`.env.example` 加 `OFFERING_THRESHOLD_PER_PLAYER=1000`，更新 `docs/db-schema.md`、`docs/engine/formula.md`
  - Files: `src/database/schema.py`, `.env.example`
  - Acceptance: schema.py 建立 offering_accumulator 欄位；.env.example 包含新 key；兩份 docs 已更新

- [x] Task 2: Settlement — 奉獻行動結算邏輯 — 在 `src/core/settlement.py` 處理 `action='offering'`：計算 offering_cost、扣除 FOOD_COST + 選定資源、更新 accumulator、觸發檢查（全員素材 +1 + 歸零）；更新 `docs/engine/action-resolver.md`、`docs/engine/formula.md`（stored value 表加入 `offering`；`action_target` 說明加入 offering 的 `food`/`wood`/`knowledge` 值；action-to-field mapping table 加入 offering 行）
  - Files: `src/core/settlement.py`, `docs/engine/action-resolver.md`
  - Depends on: Task 1
  - Acceptance: offering 結算正確扣除資源；accumulator 遞增；觸發後全員 +1 且歸零；shortage 時以實際扣除量計入；formula.md 三處已更新

- [ ] Task 3: Notification — 奉獻達標 Public 通知 — 在 `src/core/notification.py` 加入奉獻達標事件；更新 `docs/discord/notification.md`
  - Files: `src/core/notification.py`, `docs/discord/notification.md`
  - Depends on: Task 2
  - Acceptance: 觸發時發送公開通知，包含累積量、閾值、全員獲得素材資訊；`notification.md` 的「同一 settlement 內的通知順序」區段已加入奉獻達標事件並定位順序

- [ ] Task 4: UI — 奉獻加入 action_select + 資源選擇 dropdown + Dashboard accumulator 進度顯示 — 更新 `src/cogs/actions.py`（新增 offering + offering_resource_select 互動路由）、`src/cogs/ui_renderer.py`（Dashboard 累積進度行、主介面行動列表、奉獻 emoji 🎁）；更新 `docs/discord/command-handler.md`、`docs/discord/ui-renderer.md`
  - Files: `src/cogs/actions.py`, `src/cogs/ui_renderer.py`
  - Depends on: Task 1, Task 2
  - Acceptance: action_select 含奉獻選項；選奉獻後出現資源 dropdown；Dashboard 顯示 accumulator 進度；村民行動區區別奉獻（食物）/奉獻（木頭）/奉獻（研究點）

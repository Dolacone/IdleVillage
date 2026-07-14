---
title: "移除奉獻系統"
status: Issues-confirmed
created: 2026-07-14
doc_type: change
last_reviewed: 2026-07-14
source_paths:
  - docs/db-schema.md
  - docs/engine/formula.md
  - docs/engine/action-resolver.md
  - docs/discord/ui-renderer.md
  - docs/discord/command-handler.md
  - docs/discord/notification.md
  - src/database/schema.py
  - src/core/config.py
  - src/core/formula.py
  - src/core/settlement.py
  - src/core/notification.py
  - src/cogs/actions.py
  - src/cogs/ui_renderer.py
  - .env.example
  - tests/support.py
  - tests/test_engine_formula.py
  - tests/test_engine_settlement.py
scope: "Tracks removal of the offering (奉獻) player action system from design through review."
---

## Problem Statement

奉獻系統（2026-05-23 引入，見 `docs/changelogs/2026-05-23-offering-action.md`）是第 5 種玩家行動：消耗食物/木頭/研究點其中一種資源，累積至全村門檻後，讓所有玩家素材各 +1。目前決定移除此系統，回歸原本四種行動（採集/建設/戰鬥/研究）。

## Recommended Direction

完全移除：刪除所有奉獻相關程式碼、DB 欄位 `village_state.offering_accumulator`、UI 下拉選單與第二層資源選單、公告樣板、env var `OFFERING_THRESHOLD_PER_PLAYER`，並同步更新所有涉及的文件。

### 排除的替代方案

- 軟關閉（保留程式碼與 schema，僅在 UI 隱藏並停用結算邏輯）：會留下死程式碼與未使用欄位，增加維護負擔，且用戶已明確選擇完全移除。
- 移除功能但保留歷史資料遷移：需額外撰寫一次性遷移腳本供人工查閱，非目前需求範圍。

## Clarifications

<!-- Q: 移除範圍要用哪種方向？ / A: 完全移除，包含程式碼、DB 欄位、UI、通知、env var，並更新所有相關文件。 — resolved during refine stage -->

## MVP Scope / Not Doing

- 範圍內：移除奉獻行動的資料庫欄位、結算邏輯、UI 下拉選單/按鈕、公告樣板、env var，以及 `docs/db-schema.md`、`docs/engine/formula.md`、`docs/engine/action-resolver.md`、`docs/discord/ui-renderer.md`、`docs/discord/command-handler.md`、`docs/discord/notification.md` 等文件更新。
- 範圍外：不保留任何歷史 `offering_accumulator` 資料遷移或匯出；不新增 feature flag。

## Architecture Decisions

1. 依賴順序：schema/config → formula/settlement → notification → UI/command routing。UI 移除放最後，避免中間狀態下 UI 仍引用已刪除的結算邏輯。
2. 文件已於 plan 階段同步移除奉獻相關內容（`db-schema.md`、`formula.md`、`action-resolver.md`、`ui-renderer.md`、`command-handler.md`、`notification.md`），implement 階段只需同步刪除對應程式碼與測試。
3. 歷史變更文件 `docs/changelogs/2026-05-23-offering-action.md` 為過去變更的歷史紀錄，維持不動；不建立新的遷移腳本處理現有 `offering_accumulator` 資料或 `action='offering'` 的殘留玩家狀態（依 Key Assumptions，已於 v2 fresh-restart 慣例下視為可接受風險）。

## Key Assumptions

- 移除 `village_state.offering_accumulator` 欄位屬安全操作，不影響其他系統的資料完整性（該欄位為奉獻系統獨有，未被其他功能引用）。
- `players.action_target` 欄位可繼續沿用於建設行動，不受移除奉獻影響。
- 現有正在進行中的奉獻行動（若有玩家 `action = 'offering'`）不建立遷移腳本清理殘留狀態；依 Architecture Decisions #3，v2 fresh-restart 慣例下視為可接受風險，部署後由該玩家下次設定新行動時自然覆蓋。

## Tasks

- [x] Task 1: DB schema + config 清理 — 移除 `village_state.offering_accumulator` 欄位與 `OFFERING_THRESHOLD_PER_PLAYER` 環境變數
  - Files: `src/database/schema.py`, `src/core/config.py`（另需同步 `.env.example` 移除該 key，非 source/logic 檔不計入限制）
  - Tests: 更新 `tests/support.py` 中若有引用 offering_accumulator/該 env var 的 fixture
  - Depends on: 無
  - Acceptance: schema.py 建表 SQL 不再包含 `offering_accumulator`；config.py 不再讀取 `OFFERING_THRESHOLD_PER_PLAYER`；`.env.example` 不再列出該 key；全套測試通過

- [x] Task 2: Formula + settlement 奉獻結算移除 — 移除 `compute_offering_cost`（或等效函式）與 `settlement.py` 中 `action == 'offering'` 分支
  - Files: `src/core/formula.py`, `src/core/settlement.py`
  - Tests: 移除/更新 `tests/test_engine_formula.py`、`tests/test_engine_settlement.py` 中奉獻相關測試案例，確保其餘四種行動測試不受影響
  - Depends on: Task 1
  - Acceptance: formula.py 不再匯出奉獻消耗計算函式；settlement.py 不再處理 `offering` action；其餘四種行動結算邏輯與測試不變且全數通過

- [x] Task 3: 奉獻達標公開通知移除
  - Files: `src/core/notification.py`
  - Depends on: Task 2
  - Acceptance: notification.py 不再發送奉獻達標通知；既有通知（關卡通關/升級關/建築升級/工具強化/詞條）行為與順序不受影響；相關測試（若有）通過

- [x] Task 4: UI + 互動路由移除 — 行動下拉選單移除奉獻選項、移除 `offering_resource_select` 路由、Dashboard 移除奉獻進度行、村民行動列表移除奉獻變體
  - Files: `src/cogs/actions.py`, `src/cogs/ui_renderer.py`
  - Depends on: Task 2, Task 3
  - Acceptance: `/idlevillage` 行動下拉選單僅剩採集/建設/戰鬥/研究；不再出現奉獻資源選擇 Dropdown；Dashboard embed 不含 🎁 奉獻進度行；村民行動列表不含奉獻相關項目；相關測試通過

## Plan Review Issues

- [x] Task 4 的 `Depends on: Task 2` 與 Architecture Decisions #1 所述依賴順序（schema/config → formula/settlement → notification → UI/command routing）不一致：該決策明確要求 UI 移除排在 notification 之後，但 Task 4 未宣告依賴 Task 3，導致實作時可能與 Task 3 並行或提前執行，UI 完成時 notification.py 的奉獻達標通知仍未移除。請將 Task 4 的 Depends on 改為「Task 2, Task 3」，或修改 Architecture Decisions #1 說明實際不需要此順序。
- [x] Key Assumptions 第三點「現有正在進行中的奉獻行動...需於 plan 階段確認是否需要遷移腳本清理殘留狀態」仍以待確認的問句語氣呈現，但文件狀態已是 `Ready-to-implement`，且 Architecture Decisions #3 已將此議題定案為「不建立遷移腳本」。建議將 Key Assumptions 第三點改寫為確定性陳述（呼應 Architecture Decisions #3 的結論），避免與文件目前狀態矛盾。

## Review Issues

- [ ] [Major] `src/core/formula.py:64,71` (`compute_output`) indexes `ACTION_GEAR_COL[action]` / `ACTION_FACILITY_BUILDING[action]` with plain dict lookups, and both entries for `"offering"` were removed. If a player still has `action='offering'` in the DB at deploy time (the risk explicitly accepted in Key Assumptions / Architecture Decision #3), `settle_complete_cycles` (`src/core/settlement.py:100`, calling `compute_output` after the offering branch was deleted) and `change_action`'s partial-cycle path (`src/core/settlement.py:327`, now unconditionally calling `compute_output(db, user_id, old_action, ...)` for any `old_action` including `"offering"`) will raise an unhandled `KeyError` instead of the "natural override on next action change" behavior the change document promises (`docs/changes/2026-07-14-remove-offering-system.md` Key Assumptions: "部署後由該玩家下次設定新行動時自然覆蓋"). This contradicts the documented assumption: the player cannot change action either, since `change_action` itself crashes before reaching the "write new action" step — there is no code path that lets an affected player recover without a manual DB fix.
- [ ] [Minor] Root `CHANGELOG.md` was not updated with an entry for this removal, even though the original addition (2026-05-23 offering action) has a CHANGELOG entry (`CHANGELOG.md:31`) and the repo's recent commit history shows a pattern of adding changelog entries for change-document-tracked work (e.g. commit `9d6362e chore: add changelog entry and mark change document Done`).

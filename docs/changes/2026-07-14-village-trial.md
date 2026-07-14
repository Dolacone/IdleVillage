---
title: "新指令：村莊試煉"
status: Draft
created: 2026-07-14
doc_type: change
last_reviewed: 2026-07-14
source_paths: []
scope: "Tracks the village trial (試煉) feature from design through review: a global, resource-funded, timed community goal that rewards participants with universal material by contribution."
---

## Problem Statement

新增一個全服單一的「試煉」系統：任一玩家可透過新指令花費 X 個指定資源（食物/木頭/知識三選一）開啟一個目標值為 X 的試煉。試煉開始後與現有關卡系統並行運作，所有玩家的四種行動產出（不分類型，比照升級關規則）都計入同一個試煉進度。試煉開始後 24 小時內若達標，依每位玩家的貢獻度比例分配共 X/100 個萬能素材（無條件進位）；24 小時內未達標則試煉失敗，資源不予退還，且失敗或達成後 12 小時內不能開啟新試煉。

## Recommended Direction

新增獨立的「試煉」子系統，架構上比照 stage-manager 的全域單一狀態模式，但完全獨立運作（不修改 stage-manager 既有邏輯，兩者並行）：

- 新增 `trial_state`（全域單例，比照 `stage_state`）與 `trial_contributions`（每位玩家在當前試煉中的累積貢獻）兩張資料表。
- 新增 `trial_manager` 模組，職責：
  - `start_trial(resource_type, target, user_id, now)` — 檢查前置條件（無進行中試煉、冷卻已過、村莊資源足夠）、扣除資源、寫入試煉狀態、清空 `trial_contributions`、觸發開始通知。
  - `add_progress(output, user_id, now)` — 由 action-resolver 在每次結算後呼叫（比照升級關「所有行動都算進度」規則），累加至 `trial_state.progress` 與該玩家的 `trial_contributions`；若達標則觸發達成流程（依貢獻度分配萬能素材、關閉試煉、觸發達成通知）。
  - `check_timeout(now)` — 由 cycle-engine 的 Watcher tick 呼叫，偵測 `now - started_at > TRIAL_DURATION_HOURS`；若進行中試煉逾時則觸發失敗流程（不退還資源、關閉試煉、觸發失敗通知）。
  - `get_trial_info()` — 供 UI 呼叫，回傳目前試煉狀態（供 Dashboard 與 `/idlevillage` 顯示）。
- action-resolver 於每次完整週期結算（含 partial cycle、burst）後，若試煉進行中，呼叫 `trial_manager.add_progress()`；使用**資源不足懲罰前**的 output，比照 stage-manager 對關卡進度的既有規則，維持計分基準一致。
- cycle-engine 的 Watcher tick 中新增一次 `trial_manager.check_timeout(now)` 呼叫，確保沒有任何玩家觸發結算時仍能在 `TRIAL_DURATION_HOURS` 後偵測逾時（懶惰偵測依附既有 Watcher heartbeat，不新增獨立計時器，比照 stage-manager 逾時偵測風格但改掛在固定週期的 Watcher tick 上，因為試煉逾時不像關卡逾時依附於個別玩家的結算時機）。
- 新增 Discord Slash Command `/idlevillage-trial`，選項：`resource`（Choice：食物/木頭/知識）與 `target`（整數，必須為 `TRIAL_TARGET_STEP` 的整數倍）。驗證失敗（非整數倍、試煉進行中、冷卻未過、資源不足）時回覆 Ephemeral 錯誤訊息並說明原因；成功時回覆 Ephemeral 確認並觸發 Public 開始通知。
- 村莊 Dashboard 與 `/idlevillage` 個人主介面新增試煉進度顯示行（僅試煉進行中時顯示），比照現有關卡進度/建築進度呈現風格。
- 新增 Public 通知：試煉開始、試煉達成（含各參與者貢獻與獲得數量列表，比照 `/idlevillage-ranking` 的截斷規則）、試煉失敗（逾時）。
- 新增環境變數（比照專案「平衡數值一律讀環境變數」慣例，見 `engine/formula.md`）：`TRIAL_DURATION_HOURS`（預設 24）、`TRIAL_COOLDOWN_HOURS`（預設 12）、`TRIAL_TARGET_STEP`（預設 1000）、`TRIAL_REWARD_DIVISOR`（預設 100）。
- 獎勵計算：`reward_i = ceil(contribution_i / total_contribution × (target / TRIAL_REWARD_DIVISOR))`，逐一呼叫 `player-manager.addUniversalMaterial()`。依使用者決策採無條件進位，總發放量可能略高於 `target / TRIAL_REWARD_DIVISOR`（多人各自進位所致），此為使用者確認接受的行為，非 bug。

### 排除的替代方案

- 將試煉塞進既有 stage-manager 的五關循環，當作「第 6 種關卡類型」與其他關卡並行：stage-manager 的核心模型是單一序列狀態機（同時只有一個 active 關卡），且完全沒有逐玩家貢獻度追蹤機制。硬塞一個「並行、獨立於序列」的事件會破壞其單一 active 關卡的核心不變量，且仍需另外建置貢獻度追蹤，等於重工。獨立建置乾淨子系統風險更低、耦合更少。
- 試煉狀態僅存於記憶體（不落地 DB）：Watcher/cycle-engine 的所有既有狀態（`completion_time`、`stage_state` 等）都是 DB-backed 以撐過 process 重啟；試煉持續 24 小時且涉及玩家實際資源花費，記憶體儲存在任何重啟/部署後會靜默遺失進行中的試煉與已花費資源，不可接受。

## Clarifications

<!-- Q: 開啟試煉花費的 X 資源是哪一種？ / A: 玩家於指令選項三選一（食物/木頭/知識），比照現有村莊資源池扣除。 — resolved during refine stage -->
<!-- Q: 試煉是否為全服單一事件？ / A: 是，全服單一狀態，比照關卡系統的全域單一狀態模式。 — resolved during refine stage -->
<!-- Q: 獎勵無法整除時的餘數如何處理？ / A: 每位參與者的分配額各自無條件進位（ceil），總發放量可能略高於 X/100，此行為為使用者確認接受。 — resolved during refine stage -->
<!-- Q: 試煉進度與事件是否要比照現有 Dashboard / 通知呈現？ / A: 是，完整比照現有關卡通關、建築升級等事件的呈現風格（Dashboard 進度列 + Public 通知）。 — resolved during refine stage -->

## MVP Scope / Not Doing

- 範圍內：
  - `trial_state`、`trial_contributions` 兩張新資料表。
  - `trial_manager` 模組：開啟、進度累加、逾時偵測、獎勵分配、狀態查詢。
  - action-resolver 掛載試煉進度累加（含 partial cycle、burst）。
  - cycle-engine Watcher tick 掛載試煉逾時偵測。
  - 新指令 `/idlevillage-trial`（選擇資源類型 + 輸入目標值）。
  - Dashboard 與 `/idlevillage` 主介面新增試煉進度顯示。
  - Public 通知：試煉開始、達成、失敗（逾時）。
  - 新增環境變數：`TRIAL_DURATION_HOURS`、`TRIAL_COOLDOWN_HOURS`、`TRIAL_TARGET_STEP`、`TRIAL_REWARD_DIVISOR`，並更新 `.env.example`。
  - 對應文件更新：新增 `docs/managers/trial-manager.md`（新模組 SSOT），更新 `docs/README.md`（SSOT map）、`docs/db-schema.md`、`docs/engine/action-resolver.md`、`docs/engine/cycle-engine.md`、`docs/engine/formula.md`、`docs/discord/command-handler.md`、`docs/discord/ui-renderer.md`、`docs/discord/notification.md`。
- 範圍外：
  - 每位玩家各自開啟獨立試煉（已確認為全服單一）。
  - 試煉歷史紀錄查詢指令（例如「過去試煉列表」）。
  - 資源類型以外的試煉花費方式（例如素材、AP）。
  - 試煉目標值上限（僅受限於村莊當下資源存量，不另設硬上限）。
  - 獎勵餘數的其他分配策略（僅實作無條件進位）。

## Key Assumptions

- 試煉進度採用「資源不足懲罰前的 output」計分，比照 stage-manager 對關卡進度的既有規則（`關卡進度使用資源不足懲罰前的 output`），維持與現有計分基準一致；此為根據現有系統慣例的推論，非使用者逐字指定，上線後應驗證此假設符合預期平衡。
- Partial cycle（換行動時的比例產出）與 Burst（爆發執行）的產出比照 stage-manager 既有規則同樣計入試煉進度，因為兩者本來就會計入關卡進度，試煉「運作邏輯類似於升級關」故採相同基準。
- 試煉逾時偵測掛載於 cycle-engine 的 Watcher heartbeat tick（每次 `WATCHER_HEARTBEAT_SECONDS` 執行一次，與個別玩家是否有到期行動無關），而非比照關卡逾時的「懶惰偵測、依附個別玩家結算」模式，因為試煉逾時不應該在無人行動時被無限期延後判定。
- 試煉達成的萬能素材獎勵於達標當下立即發放（呼叫 `addUniversalMaterial`），不需要玩家額外操作或查詢介面。
- `/idlevillage-trial` 指令對所有玩家開放（無需管理員權限），與其他玩家指令一致的 guild 檢查即可。

## Architecture Decisions
<!-- Key technical choices and rationale — added during plan stage -->

## Tasks
- [ ] Task 1: ...

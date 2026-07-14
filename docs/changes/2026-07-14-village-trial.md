---
title: "新指令：村莊試煉"
status: Done
created: 2026-07-14
doc_type: change
last_reviewed: 2026-07-14
source_paths:
  - src/database/schema.py
  - src/core/config.py
  - .env.example
  - src/managers/trial_manager.py
  - src/cogs/ui_renderer.py
  - src/core/settlement.py
  - src/core/engine.py
  - src/core/notification.py
  - src/cogs/actions.py
  - src/cogs/general.py
  - src/cogs/trial_cog.py
  - src/main.py
  - docs/README.md
  - docs/db-schema.md
  - docs/discord/command-handler.md
  - docs/discord/notification.md
  - docs/discord/ui-renderer.md
  - docs/engine/action-resolver.md
  - docs/engine/cycle-engine.md
  - docs/engine/formula.md
  - docs/managers/trial-manager.md
  - tests/support.py
  - tests/test_discord_commands.py
  - tests/test_discord_notifications.py
  - tests/test_engine_settlement.py
  - tests/test_trial_cog.py
  - tests/test_trial_manager.py
  - tests/test_v2_schema_initialization.py
  - tests/test_startup_shell.py
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
  - `check_timeout(now)` — 由 cycle-engine 的 Watcher tick 呼叫，偵測 `now - started_at > TRIAL_DURATION_SECONDS`；若進行中試煉逾時則觸發失敗流程（不退還資源、關閉試煉、觸發失敗通知）。
  - `get_trial_info()` — 供 UI 呼叫，回傳目前試煉狀態（供 Dashboard 與 `/idlevillage` 顯示）。
- action-resolver 於每次完整週期結算（含 partial cycle、burst）後，若試煉進行中，呼叫 `trial_manager.add_progress()`；使用**資源不足懲罰前**的 output，比照 stage-manager 對關卡進度的既有規則，維持計分基準一致。
- cycle-engine 的 Watcher tick 中新增一次 `trial_manager.check_timeout(now)` 呼叫，確保沒有任何玩家觸發結算時仍能在 `TRIAL_DURATION_SECONDS` 後偵測逾時（懶惰偵測依附既有 Watcher heartbeat，不新增獨立計時器，比照 stage-manager 逾時偵測風格但改掛在固定週期的 Watcher tick 上，因為試煉逾時不像關卡逾時依附於個別玩家的結算時機）。
- 新增 Discord Slash Command `/idlevillage-trial`，選項：`resource`（Choice：食物/木頭/知識）與 `target`（整數，必須為 `TRIAL_TARGET_STEP` 的整數倍）。驗證失敗（非整數倍、試煉進行中、冷卻未過、資源不足）時回覆 Ephemeral 錯誤訊息並說明原因；成功時回覆 Ephemeral 確認並觸發 Public 開始通知。
- 村莊 Dashboard 與 `/idlevillage` 個人主介面新增試煉進度顯示行（僅試煉進行中時顯示），比照現有關卡進度/建築進度呈現風格。`ui_renderer.py` 的 `trial_data` 參數採可選（預設 `None`，內部視為無進行中試煉），使 Task 3 單獨完成後既有呼叫端（尚未傳入 `trial_data`）仍維持原本行為（不顯示試煉列），Task 6/7 再串接真實資料，避免任務之間出現簽章不符的中間壞狀態。
- Dashboard／主介面的資料擷取層（`notification.py._fetch_village_dashboard_data`、`actions.py._fetch_all_data`、`general.py._fetch_village_data`）直接以 `SELECT * FROM trial_state WHERE id=1` 查詢，不透過 `trial_manager.get_trial_info()`。這與這三個函式現有查詢 `stage_state`／`buildings`／`village_resources` 的方式一致（皆為直接 SQL，未呼叫對應 manager 的 getter），屬既有慣例，非新增的不一致。`trial_manager.get_trial_info()`/`get_contribution()` 供沒有既有 fetch-helper 模式的呼叫端使用（例如 `trial_cog.py` 指令驗證邏輯、`trial_manager` 內部）。
- 新增 Public 通知：試煉開始、試煉達成（含各參與者貢獻與獲得數量列表，比照 `/idlevillage-ranking` 的截斷規則）、試煉失敗（逾時）。
- 新增環境變數（比照專案「平衡數值一律讀環境變數」慣例，見 `engine/formula.md`）：`TRIAL_DURATION_SECONDS`（預設 86400，即 24 小時）、`TRIAL_COOLDOWN_SECONDS`（預設 43200，即 12 小時）、`TRIAL_TARGET_STEP`（預設 1000）、`TRIAL_REWARD_DIVISOR`（預設 100）。命名採用 `_SECONDS` 後綴而非 `_HOURS`，比照專案既有大時長環境變數慣例（如 `STAGE_OVERTIME_SECONDS=86400`），非逐字沿用需求描述的「小時」措辭。
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
  - 新增環境變數：`TRIAL_DURATION_SECONDS`、`TRIAL_COOLDOWN_SECONDS`、`TRIAL_TARGET_STEP`、`TRIAL_REWARD_DIVISOR`，並更新 `.env.example`。
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

1. **不擴充 `stage_state`/`stage-manager`，改建獨立子系統**：`trial_state`、`trial_contributions` 為全新資料表，`trial_manager.py` 為全新模組，兩者與 `stage_manager.py` 完全不共用程式碼路徑，僅在 `action-resolver`（settlement.py）與 `cycle-engine`（engine.py）中並列呼叫。理由見 Recommended Direction 排除的替代方案。
2. **事件由 `trial_manager` 直接組裝，而非由呼叫端組裝**：`trial_manager.add_progress()` 與 `check_timeout()` 直接回傳形如 `{"type": "trial_success"/"trial_fail", ...}` 的完整事件 dict（或 `None`），呼叫端（settlement.py／engine.py）只需 `if event: events.append(event)`。這與 `stage_manager.add_progress()`（只回傳 `new_stages_cleared` 原始值，由 settlement.py 組裝事件）不同，但與 `gear_manager.attempt_upgrade()`（回傳豐富結果 dict，直接供呼叫端組裝通知）一致 —— 因為試煉的達成事件需要獎勵分配明細（各參與者貢獻與獲得數量），這些資料本來就只有 trial_manager 算得出來，若要求呼叫端重新組裝等於重複運算或額外傳遞大量中間資料，不划算。
3. **試煉通知一律使用 Discord mention（`<@{user_id}>`），不解析 display name**：`trial_success`/`trial_fail` 事件在 settlement.py／engine.py 中產生時沒有 `bot`/guild 物件可用（無法呼叫 `guild.fetch_member()`），且參與者人數不固定，一一解析成本高。改用 `<@{user_id}>` mention 語法，Discord 客戶端會自動渲染成當前顯示名稱，不需要額外 API 呼叫。`trial_start` 事件雖然在有 `inter.user` 可用的指令 handler 中組裝，為求同一組事件呈現風格一致，同樣改用 mention 而非 `user_display_name`（與既有 `gear_success` 等事件的 `user_display_name` 風格不同，但屬新事件類型，允許採用更簡單一致的做法）。
4. **試煉逾時判定同時掛在「結算路徑」與「Watcher tick」兩處，共用同一段失敗處理邏輯**：`add_progress()` 在累加前先用呼叫端傳入的 `effective_time`（settlement 的結算時間戳）判斷是否已逾時，若是則不計入本次 output、直接觸發失敗；`check_timeout()` 則用 Watcher tick 當下的 `now` 判斷，作為「完全無人行動」時的後備偵測。兩處共用一個內部 `_fail_trial()` helper（清空 `trial_contributions`、寫入 `is_active=0, ended_at`、組裝 `trial_fail` 事件），避免邏輯分岔。
5. **`trial_state` 不儲存 `started_by`（發起者）欄位**：目前唯一需要發起者資訊的地方是「試煉開始」公告，而該公告在指令 handler 內組裝時已直接拿得到 `inter.user.id`，不需要從 DB 讀回。沒有其他功能（無歷史查詢指令、Dashboard 不顯示發起者）需要持久化這個欄位，故不新增，避免死欄位。
6. **`.env.example` 與 `config.py` 的 `REQUIRED_KEYS` 更新歸在 Task 1（implement 階段），而非現在的 plan 階段文件更新**：比照 `docs/changes/2026-07-14-remove-offering-system.md` 與 `docs/changes/2026-07-14-universal-material.md` 的既有慣例（`.env.example` 視為與程式碼綁定的設定檔，跟 schema/config 程式碼在同一個 implement commit 異動，不算是 plan 階段的「文件」）。
7. **依賴順序**：schema/config → trial_manager → {ui_renderer 顯示、settlement.py 進度累加、engine.py 逾時偵測} → notification.py（依賴 trial_manager 事件格式與 ui_renderer 的 Dashboard 函式簽章）→ {actions.py/general.py 串接顯示、trial_cog.py 新指令}。UI 顯示與新指令都需要 trial_manager 定義好的 `trial_data`/事件格式，故排在其後。

## Tasks

- [x] Task 1: DB schema + config — 新增 `trial_state`、`trial_contributions` 兩張資料表；新增四個環境變數
  - Files: `src/database/schema.py`, `src/core/config.py`（另需同步更新 `.env.example` 新增四個 key，非 source/logic 檔不計入限制）
  - Tests: 更新 `tests/test_v2_schema_initialization.py`（新表存在性、初始列）；更新 `tests/test_v2_config_validation.py`（新 REQUIRED_KEYS 通過驗證）
  - Depends on: 無
  - Acceptance: `trial_state`（單例，`id=1` 初始列 `is_active=0`）與 `trial_contributions`（空表）皆以 `CREATE TABLE IF NOT EXISTS` 建立；`config.REQUIRED_KEYS` 新增 `TRIAL_DURATION_SECONDS`/`TRIAL_COOLDOWN_SECONDS`/`TRIAL_TARGET_STEP`/`TRIAL_REWARD_DIVISOR`；`.env.example` 列出四個 key 並附預設值（86400/43200/1000/100）；既有測試套件全數通過

- [x] Task 2: trial_manager 模組 — 開啟、進度累加、逾時偵測、獎勵分配、狀態/貢獻查詢
  - Files: `src/managers/trial_manager.py`（新檔）
  - Tests: 新增 `tests/test_trial_manager.py`，涵蓋：(a) `start_trial` 前置條件各項失敗案例（resource_type 無效、target 非整數倍、已有進行中試煉、冷卻未過、資源不足）皆 raise ValueError 且不扣除資源；(b) `start_trial` 成功扣除資源、清空 `trial_contributions`、寫入正確狀態；(c) `add_progress` 無試煉時 no-op 回傳 None；(d) `add_progress` 累加進度與個人貢獻，未達標回傳 None；(e) `add_progress` 達標時正確依 ceil 公式分配獎勵給所有貢獻者、呼叫 `addUniversalMaterial`、關閉試煉、清空 `trial_contributions`、回傳含 `participants` 明細的 `trial_success` 事件；(f) `add_progress` 傳入的 `effective_time` 已超過 `TRIAL_DURATION_SECONDS` 時觸發失敗而非計入進度；(g) `check_timeout` 未逾時回傳 None、逾時時觸發失敗並回傳 `trial_fail` 事件、清空 `trial_contributions`
  - Depends on: Task 1
  - Acceptance: 所有前置條件、進度累加、逾時（兩種觸發路徑共用同一失敗邏輯）、獎勵分配（ceil 無條件進位、可能總額略高於 target/divisor）行為與 `docs/managers/trial-manager.md` 一致；測試通過

- [x] Task 3: ui_renderer.py — Dashboard 與個人主介面新增試煉顯示
  - Files: `src/cogs/ui_renderer.py`
  - Tests: 更新 `tests/test_discord_commands.py`，涵蓋：(a) 試煉進行中時村莊區塊出現試煉進度列（含資源圖示/名稱、進度、期限）；(b) 試煉未進行時村莊區塊不出現試煉列；(c) 個人資訊區塊試煉進行中時出現「試煉貢獻」列；(d) 試煉未進行時不出現該列；(e) 呼叫端未傳入 `trial_data`（沿用預設值）時行為與試煉未進行時相同，確保既有呼叫端在 Task 6/7 串接前不會出錯
  - Depends on: Task 2（`trial_data`/貢獻值資料形狀）
  - Acceptance: `_build_village_section`/`build_village_embed`/`build_main_embed` 新增**可選**關鍵字參數 `trial_data=None`（內部以 `trial_data or {}` 正規化，`{}`／`is_active` 為假值時視為無進行中試煉），`build_main_embed` 另外新增可選的玩家個人貢獻值參數（預設 0）；顯示格式符合 `docs/discord/ui-renderer.md`；試煉未啟用或參數未提供時兩處顯示皆完整省略；既有呼叫端（`notification.py`/`actions.py`/`general.py`，尚未於本任務更新）在不傳入新參數的情況下行為不變；既有 UI 測試不受影響且全數通過

- [x] Task 4: settlement.py — 掛載試煉進度累加
  - Files: `src/core/settlement.py`
  - Tests: 更新 `tests/test_engine_settlement.py`，涵蓋：(a) 完整週期結算時試煉進行中會呼叫 `trial_manager.add_progress` 並將回傳的 `trial_success` 事件加入 events；(b) partial cycle（`change_action`）同樣計入試煉進度；(c) burst 3 次結算各自獨立計入試煉進度；(d) 試煉未啟用時不影響現有結算行為
  - Depends on: Task 2
  - Acceptance: `_run_one_cycle` 與 `change_action` 的 partial cycle 區塊皆在對應的 stage-manager 呼叫之後，以資源不足懲罰前的 output 呼叫 `trial_manager.add_progress`；回傳事件正確併入該次呼叫的 `events` 列表；既有結算測試不受影響且全數通過

- [x] Task 5: engine.py — Watcher tick 掛載試煉逾時偵測
  - Files: `src/core/engine.py`
  - Tests: 於 `tests/test_v2_schema_initialization.py`（`WatcherIsV2Safe` 類別已直接呼叫 `Engine.process_watcher()`，為既有 Watcher 測試所在檔案）新增測試，涵蓋：(a) 試煉逾時時 Watcher tick 產生 `trial_fail` 事件並隨其他事件一併 dispatch；(b) 試煉未逾時或無進行中試煉時不產生額外事件
  - Depends on: Task 2
  - Acceptance: `Engine._process_watcher_v2` 在處理完到期玩家後呼叫一次 `trial_manager.check_timeout(now)`，回傳事件併入 `all_events` 後才 dispatch；測試通過

- [x] Task 6: notification.py — 試煉事件格式化與 Dashboard 資料串接
  - Files: `src/core/notification.py`
  - Tests: 更新 `tests/test_discord_notifications.py`，涵蓋：(a) `trial_start`/`trial_success`/`trial_fail` 三種事件的 `_format_event` 輸出符合範本；(b) `trial_success` 參與者列表超長時正確截斷並附加省略提示；(c) `update_dashboard` 正確將試煉資料傳入 `build_village_embed`
  - Depends on: Task 2, Task 3
  - Acceptance: 三種事件格式化輸出符合 `docs/discord/notification.md` 範本；`_fetch_village_dashboard_data` 新增試煉資料查詢；既有通知測試不受影響且全數通過

- [x] Task 7: actions.py + general.py — 現有指令串接試煉顯示資料
  - Files: `src/cogs/actions.py`, `src/cogs/general.py`
  - Tests: 更新 `tests/test_discord_commands.py`（或對應現有測試檔），涵蓋 `/idlevillage` 主介面在試煉進行中正確顯示村莊試煉列與個人貢獻列；`/idlevillage-announcement` 建立的 Dashboard embed 同樣正確顯示試煉列
  - Depends on: Task 1, Task 3
  - Acceptance: `actions.py._fetch_all_data` 與 `general.py._fetch_village_data` 皆查詢 `trial_state`（與 `actions.py` 額外查詢當前玩家的 `trial_contributions`），並傳入 `build_main_embed`/`build_village_embed`；既有指令測試不受影響且全數通過

- [x] Task 8: 新指令 `/idlevillage-trial`
  - Files: `src/cogs/trial_cog.py`（新檔）, `src/main.py`（將 `"cogs.trial_cog"` 加入既有 `initial_extensions` 列表，非新增獨立的 `bot.load_extension()` 呼叫；非核心邏輯變更，仍在 2 檔限制內）
  - Tests: 新增 `tests/test_trial_cog.py`，涵蓋：(a) 非指定 Guild 時拒絕執行；(b) `target` 非 `TRIAL_TARGET_STEP` 整數倍時回覆 Ephemeral 錯誤且不呼叫 `start_trial`；(c) 已有進行中試煉、冷卻未過、資源不足三種前置條件失敗時分別回覆對應錯誤訊息；(d) 成功開啟時呼叫 `trial_manager.start_trial`、回覆 Ephemeral 確認、並 dispatch 一則 `trial_start` Public 通知
  - Depends on: Task 2, Task 6
  - Acceptance: Slash command `resource` 選項為 Choice（食物/木頭/知識對應 food/wood/knowledge）、`target` 為整數選項；所有前置條件失敗情境皆有對應 Ephemeral 錯誤訊息且不扣除資源；成功時觸發的 `trial_start` 事件格式符合 `docs/discord/notification.md`；`main.py` 正確載入新 cog；測試通過

### 平行任務標記（僅供未來參考，目前循序執行）

- Task 1 完成後，Task 2 可先開始；Task 2 完成後，Task 3／Task 4／Task 5 三者可平行進行（各自獨立檔案、無交集）。
- Task 6 需等待 Task 2 與 Task 3 皆完成。
- Task 7 需等待 Task 1 與 Task 3 完成，可與 Task 4／Task 5／Task 6 平行進行（檔案無交集）。
- Task 8 需等待 Task 2 與 Task 6 完成。

## Plan Review Issues

- [x] Issue 1 (dependency chain gap, intermediate broken state): Task 3 (`docs/changes/2026-07-14-village-trial.md:96-100`) changes `_build_village_section`/`build_village_embed`/`build_main_embed` signatures to require `trial_data` as a mandatory new parameter, but the existing call sites in `src/core/notification.py` (`_fetch_village_dashboard_data`/`update_dashboard`), `src/cogs/general.py` (`_fetch_village_data`/`announcement`), and `src/cogs/actions.py` (`_fetch_all_data`/`_render_main`) are not updated until Task 6/Task 7 — which per the stated sequential execution order (`docs/changes/2026-07-14-village-trial.md:132-137`) run strictly after Task 3. This leaves the codebase in a broken state (call sites passing wrong arity) between completion of Task 3 and completion of Task 6/7. Either make `trial_data` an optional/defaulted parameter in Task 3, or fold the call-site updates into the same task as the signature change.
- [x] Issue 2 (Architecture Decisions / trial-manager.md inconsistency): The Recommended Direction and `docs/managers/trial-manager.md:91-92` define `get_trial_info(db)` and `get_contribution(db, user_id)` as the manager's query API for UI consumption, but Task 6 and Task 7 acceptance criteria (`docs/changes/2026-07-14-village-trial.md:118` and `:124`) specify that `notification.py._fetch_village_dashboard_data`, `actions.py._fetch_all_data`, and `general.py._fetch_village_data` query `trial_state`/`trial_contributions` directly via raw SQL rather than calling the manager's query functions. This bypasses the documented manager API and duplicates query logic across three call sites. Either update Task 6/7 to call `trial_manager.get_trial_info()`/`get_contribution()`, or update the Recommended Direction and trial-manager.md to explicitly permit direct DB queries from UI-adjacent fetch helpers (matching the existing pattern where these helpers already query other tables like `stage_state` directly).
- [x] Issue 3 (inaccurate call-site description): Task 8's file-scope note for `src/main.py` (`docs/changes/2026-07-14-village-trial.md:127`) says to add "一行 `bot.load_extension(\"cogs.trial_cog\")`", but the actual code (`src/main.py:59-69`) loads extensions by iterating over an `initial_extensions` list, not via a standalone `load_extension` call. The correct change is to append `"cogs.trial_cog"` to that list, not insert a separate `bot.load_extension(...)` line.

## Review Issues

- [x] Issue 1 (`[Minor]`): `docs/changes/2026-07-14-village-trial.md` frontmatter `source_paths` lists only source code files (`src/database/schema.py`, `src/core/config.py`, `.env.example`, `src/managers/trial_manager.py`, `src/cogs/ui_renderer.py`, `src/core/settlement.py`, `src/core/engine.py`, `src/core/notification.py`, `src/cogs/actions.py`, `src/cogs/general.py`, `src/cogs/trial_cog.py`, `src/main.py`). It omits every doc file the change touched (`docs/README.md`, `docs/db-schema.md`, `docs/discord/command-handler.md`, `docs/discord/notification.md`, `docs/discord/ui-renderer.md`, `docs/engine/action-resolver.md`, `docs/engine/cycle-engine.md`, `docs/engine/formula.md`, `docs/managers/trial-manager.md`) and every test file created/modified (`tests/support.py`, `tests/test_discord_commands.py`, `tests/test_discord_notifications.py`, `tests/test_engine_settlement.py`, `tests/test_trial_cog.py`, `tests/test_trial_manager.py`, `tests/test_v2_schema_initialization.py`, `tests/test_startup_shell.py`), per `git diff main...HEAD --stat`. This is inconsistent with the convention set by `docs/changes/2026-07-14-remove-offering-system.md`, whose `source_paths` includes both docs and tests. No functional impact — bookkeeping only.
- [x] Issue 2 (`[Minor]`): `src/cogs/trial_cog.py` builds the `trial_start` event's `reward_pool` field with integer floor division (`target // divisor`), while the documented reward formula (`docs/managers/trial-manager.md` "達成與獎勵分配" section, and the actual `_succeed_trial` implementation in `src/managers/trial_manager.py`) uses true division (`info["target"] / divisor`). For default env values (`TRIAL_TARGET_STEP=1000`, `TRIAL_REWARD_DIVISOR=100`) `target` is always an exact multiple of the divisor so the two forms agree, but if an operator configures a non-default `TRIAL_TARGET_STEP`/`TRIAL_REWARD_DIVISOR` pair where `target` is not evenly divisible, the `trial_start` announcement's displayed reward pool would understate the actual pool used in the real ceil-based payout, causing a cosmetic display mismatch (no effect on actual reward computation/payout, which is computed independently and correctly in `_succeed_trial`).

**Verification notes:**
- Test suite: `uv run python -m pytest -q` → 475 passed, 3 subtests passed. No failures.
- Migration check confirmed: `trial_state`/`trial_contributions` use `CREATE TABLE IF NOT EXISTS` (`src/database/schema.py`), consistent with "new tables need no migration path" — no `ALTER TABLE` required since these tables did not exist before.
- Reward-exploit check confirmed: `_succeed_trial` (`src/managers/trial_manager.py`) computes `total_contribution` from actual `trial_contributions` rows via `SELECT user_id, contribution FROM trial_contributions`, not from `info["target"]`. No `deposit` call exists anywhere in `trial_manager.py` — resources withdrawn via `resource_manager.withdraw` in `start_trial` are never refunded on `_fail_trial`.
- Dual timeout-detection paths (`add_progress` inline check vs `check_timeout` Watcher backstop) both correctly route through the shared `_fail_trial` helper; `add_progress` skips crediting output when `effective_time` is past the deadline (checked before the progress/contribution UPDATE statements run).
- `settlement.py` both call sites (`_run_one_cycle` line ~204, `change_action` partial-cycle block line ~354) pass the pre-shortage-penalty `output`/`partial_output` to `trial_manager.add_progress`, matching the adjacent `stage_manager.add_progress` calls' basis.
- `engine.py`'s Watcher tick calls `trial_manager.check_timeout` unconditionally every heartbeat, not gated behind `due_players`, confirmed by code and by `tests/test_v2_schema_initialization.py::test_watcher_tick_fails_expired_trial_with_no_due_players`.
- `ui_renderer.py`'s `trial_data` parameter defaults to `None` and is normalized via `trial_data or {}` in `_build_village_section`/`build_main_embed`'s contribution-line check; `build_village_embed`/`build_main_embed` pass through the default correctly.
- `trial_cog.py`'s command performs all precondition checks (guild, target-step, is_active, cooldown, resource sufficiency) before calling `trial_manager.start_trial`, and `db.commit()` is only called after `start_trial` succeeds — the `except ValueError` fallback path cannot follow a partial commit since `start_trial` itself raises before any `withdraw`/state write.
- No scope creep: `git diff main...HEAD --stat` confirms `sacrifice_material`, `affix_manager.py`, and `stage_manager.py` are untouched.
- All Tasks 1-8 verified against the diff (not just document claims); all touched docs have `last_reviewed: 2026-07-14`; `status` is `Ready-to-review` prior to this review pass.

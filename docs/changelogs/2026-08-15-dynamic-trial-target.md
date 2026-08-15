---
title: "村莊試煉動態目標"
status: In-Progress
created: 2026-08-15
doc_type: change
last_reviewed: 2026-08-15
source_paths:
  - .env.example
  - src/core/config.py
  - src/database/schema.py
  - src/managers/trial_manager.py
  - src/managers/resource_manager.py
  - src/cogs/actions.py
  - src/cogs/ui_renderer.py
  - src/core/notification.py
  - tests/support.py
  - tests/test_v2_config_validation.py
  - tests/test_trial_manager.py
  - tests/test_discord_commands.py
  - tests/test_discord_notifications.py
  - docs/README.md
  - docs/changes/2026-07-14-village-trial.md
  - docs/changes/2026-07-15-trial-dashboard-status.md
  - docs/deployment.md
  - docs/engine/formula.md
  - docs/managers/trial-manager.md
  - docs/discord/command-handler.md
  - docs/discord/ui-renderer.md
  - docs/discord/notification.md
scope: "Tracks player-selected village trial targets, reserved resources, pagination, atomic start validation, review, and refactoring."
---

## Problem Statement

現行 `open_trial_start` 會立即開啟固定 `50000` 目標的試煉。玩家無法依村莊資源選擇試煉規模。扣款也未保留每種資源的最低存量。

本變更讓玩家從 `25000` 級距中選擇目標。系統必須保留被扣資源至少 `10000`。選取目標後立即開啟，不增加第二次確認。

## Recommended Direction

選用 Ephemeral 分頁 Dropdown。`open_trial_start` 先顯示合法目標。玩家選取後，系統重新驗證並立即開啟試煉。

此方向讓玩家看見合法級距。分頁也避開 Discord 每個 String Select 最多 25 個選項的限制。

排除自由輸入 Modal。自由輸入會讓玩家提交無效級距，也需要額外錯誤處理。

排除先選資源。需求指定由系統均勻隨機選擇可支付資源。

排除建立完整目標陣列。村莊資源沒有上限，完整陣列會隨存量成長。

## Clarifications

<!-- Q: 試煉目標級距是多少？ / A: 每 25000 為一個級距。 -->
<!-- Q: 每種資源必須保留多少？ / A: 扣款後至少保留 10000。 -->
<!-- Q: 選取目標後是否需要第二個確認？ / A: 不需要，選取後立即開啟。 -->
<!-- Q: 玩家是否選擇扣款資源？ / A: 不選擇。系統從可支付資源中均勻隨機選擇。 -->
<!-- Q: UI 是否公開？ / A: 目標選單與翻頁維持 Ephemeral。開始通知維持 Public。 -->
<!-- Q: 期限與冷卻是否變更？ / A: 兩者都維持 43200 秒。 -->
<!-- Q: 計畫與程式審查由誰負責？ / A: Copilot 審查計畫。Sol 先審程式，Copilot 再審。 -->
<!-- Q: 是否保留 refactor 階段？ / A: 保留。重構由 Sol 決策，Luna 編輯，之後重跑兩層審查。 -->

## MVP Scope / Not Doing

範圍內：

- 將固定目標改為玩家選擇的 `25000` 倍數。
- 每種資源保留 `10000`。
- 依最新資源計算最大合法目標。
- 使用每頁最多 25 個選項的 Ephemeral 選單。
- 提交時重新驗證 active、cooldown、target 與 resources。
- 將試煉開啟流程包在 `BEGIN IMMEDIATE` 交易。
- 沿用既有開始、達成與失敗通知。

範圍外：

- 不讓玩家指定扣款資源。
- 不增加第二個確認按鈕。
- 不修改資料庫 schema。
- 不修改貢獻、獎勵、成功或失敗規則。
- 不修改 12 小時期限與 12 小時冷卻。
- 不為 `TRIAL_TARGET_AMOUNT` 提供相容 fallback。

## Key Assumptions

- 村莊資源可持續成長，因此選項數量沒有固定上限。
- Discord String Select 每頁最多容納 25 個目標。
- SQLite 寫入鎖可序列化同時開啟試煉的請求。
- `src/core/notification.py` 已使用事件內的動態 `target`，預計不需修改。
- 部署環境會在上線前完成新環境變數切換。
- 上線後需觀察玩家常選級距與資源保留量是否合理。
- doc-audit baseline 已有舊路徑與 `bak` 警告。Task 5 只阻擋本變更新增的問題。

## Architecture Decisions

### 設定契約

將 `TRIAL_TARGET_AMOUNT` 改名為 `TRIAL_TARGET_STEP`。預設值為 `25000`。新增 `TRIAL_RESOURCE_RESERVE`，預設值為 `10000`。

`TRIAL_TARGET_STEP` 必須為正整數。`TRIAL_RESOURCE_RESERVE` 必須為非負整數。舊 key 不提供 fallback。

### 目標公式

```text
step = 25000
reserve = 10000
available(resource) = max(balance(resource) - reserve, 0)
max_target = floor(max(available(food), available(wood), available(knowledge)) / step) * step
```

合法目標為 `step, step * 2, ... max_target`。`max_target == 0` 時不能開啟選單。

例如 `food=51000`、`wood=310000`、`knowledge=220000`。可用量分別為 `41000`、`300000`、`210000`。最大目標為 `300000`。

選取 `200000` 時，只有 wood 與 knowledge 可支付。系統只會從兩者中均勻隨機選擇。

### 計算與呈現邊界

`trial_manager.get_max_trial_target(resources)` 是最大目標的唯一公式入口。manager 與 renderer 的整合測試必須防止公式漂移。

renderer 只建立當頁選項。第 `page` 頁的級距索引為 `page * 25 + 1` 到 `min((page + 1) * 25, max_target / step)`。

頁碼採 0-based。資源變動後，超出範圍的頁碼夾限到最後一頁。

### 原子開啟交易

`start_trial(db, now, target)` 先執行 `BEGIN IMMEDIATE`。取得寫入鎖後，依序重新讀取試煉狀態與三種資源。

manager 在鎖內驗證 active、cooldown、正數級距與最新可支付資源。符合條件後，才呼叫 `random.choice(eligible)`。

扣款、清空舊貢獻與更新 `trial_state` 都在同一交易內。成功時由既有呼叫端 commit。任何例外都由 manager rollback 後再拋出。

manager 用可識別的失敗原因區分 `active`、`cooldown`、`invalid_target` 與 `stale_target`。`invalid_target` 代表非正數或非 step 倍數。`stale_target` 代表合法級距超過最新 `max_target`。

target 通過最新 `max_target` 驗證後，eligible 在數學上必不為空。manager 不保留獨立的 `insufficient_resources` 分支。

### Discord 互動

`open_trial_start` 不再扣款。它重新讀取 active、cooldown 與三種資源，再計算 `max_target`。

如果 active、cooldown 或 `max_target == 0`，handler 返回主介面並顯示對應訊息。這些路徑不得建立空 Select。

目標選單使用 `trial_target_select`。翻頁按鈕使用 `trial_target_page:{page}`，其中 page 是目的頁。翻頁會重新讀取試煉狀態與資源，再重算頁數。

選取值是十進位 target。handler 將其解析為整數，再交給 manager 驗證。成功後沿用現有 `trial_start` Public 通知。

如果翻頁時 active、cooldown 或已無合法目標，handler 返回主介面並顯示對應訊息。不同玩家各自使用 Ephemeral 訊息，頁面狀態不共享。

### 相容性

`trial_state.target` 已是整數欄位，因此不需 schema migration。期限、冷卻、進度與獎勵公式都讀取該欄位，能沿用動態目標。

`src/core/notification.py` 已從事件讀取 `target`。實作階段只補動態目標回歸測試，除非測試揭露缺口。

source path 標記：`docs/README.md`、兩份既有試煉 change doc、`src/database/schema.py`、`src/managers/resource_manager.py` 與 `src/core/notification.py` 為檢視限定。其餘 metadata 路徑都是預計修改或驗證範圍。

### 依賴圖

```text
Task 1 設定契約
├── Task 2 目標規則與原子交易
│   └── Task 4 互動路由與通知
└── Task 3 目標選單與分頁
    └── Task 4 互動路由與通知

Task 5 SSOT 與完整驗證
└── depends on Task 1-4
```

Task 2 與 Task 3 可在 Task 1 完成後平行。Task 4 必須等待兩者完成。

## Tasks

- [x] Task 1: 更新試煉設定契約
  - Source/logic files: `src/core/config.py`, `.env.example`
  - Tests: `tests/support.py`, `tests/test_v2_config_validation.py`
  - Depends on: 無
  - Acceptance criteria:
    - `TRIAL_TARGET_STEP=25000` 與 `TRIAL_RESOURCE_RESERVE=10000` 成為必要設定。
    - `TRIAL_TARGET_AMOUNT` 不再屬於必要設定，也沒有 fallback。
    - 新 key 在環境與 `.env.example` 預設都缺少時，設定驗證失敗。
    - step 為 0、負數或非整數時，設定驗證失敗。
    - reserve 為負數或非整數時，設定驗證失敗。
    - 期限與冷卻維持 `43200`。

- [x] Task 2: 實作目標規則與原子開啟交易
  - Source/logic files: `src/managers/trial_manager.py`
  - Tests: `tests/test_trial_manager.py`
  - Depends on: Task 1
  - Parallel: 可與 Task 3 平行
  - Acceptance criteria:
    - 範例資源計算出 `max_target=300000`。
    - 三種資源都是 `35000` 時，最大目標為 `25000`。
    - 最大可用量低於 `25000` 時，最大目標為 `0`。
    - `get_eligible_resource_types(db, 200000)` 只回傳 wood 與 knowledge。
    - `0`、負數、非 `25000` 倍數與超過最新上限的 target 都失敗。
    - 非正數或非 step 倍數回傳 `invalid_target`。
    - 合法級距超過最新上限時回傳 `stale_target`。
    - target 通過最新上限驗證後，eligible 必不為空。
    - manager 不保留獨立的 `insufficient_resources` 失敗分支。
    - 成功扣款後，被選資源至少保留 `10000`。
    - 單一可支付資源時，只扣除該資源。
    - 多種可支付資源時，只把合格清單傳給 `random.choice`。
    - `trial_state.target` 保存玩家選取值。
    - 驗證或寫入失敗時，資源與試煉狀態都不變。
    - 兩個不同連線同時啟動時，只能有一個成功。
    - 並發失敗不會重複扣款。
    - 動態 `150000` 目標沿用既有獎勵公式。
    - 試煉期限仍為 12 小時。

- [x] Task 3: 建立目標選單與分頁
  - Source/logic files: `src/cogs/ui_renderer.py`
  - Tests: `tests/test_discord_commands.py`
  - Depends on: Task 1
  - Parallel: 可與 Task 2 平行
  - Acceptance criteria:
    - 範例資源顯示 `25000` 到 `300000` 共 12 個選項。
    - 每頁最多建立 25 個選項，不建立完整選項陣列。
    - `max_target=625000` 時只有一頁。
    - `max_target=650000` 時提供下一頁。
    - 第一頁停用上一頁，最後一頁停用下一頁。
    - label 與 value 都使用相同 target。
    - 頁碼採 0-based，超界時夾限到最後一頁。
    - 沒有合法目標時，主介面按鈕維持 disabled。
    - manager 與 renderer 對最大目標的資料契約有回歸測試。

- [x] Task 4: 串接選取、翻頁與開始通知
  - Source/logic files: `src/cogs/actions.py`
  - Tests: `tests/test_discord_commands.py`, `tests/test_discord_notifications.py`
  - Depends on: Task 2, Task 3
  - Acceptance criteria:
    - 點擊 `open_trial_start` 重讀 active、cooldown 與三種資源，再計算 `max_target`。
    - active 時返回主介面並顯示進行中訊息，不建立 Select。
    - cooldown 時返回主介面並顯示冷卻訊息，不建立 Select。
    - `max_target == 0` 時返回主介面並顯示資源不足，不建立空 Select。
    - 只有通過開啟檢查時，才顯示第 0 頁且不扣款。
    - 翻頁重讀相同狀態與最新資源，不扣款。
    - 選取 `trial_target_select` 後才呼叫 `start_trial`。
    - 選取時 manager 重新驗證，不信任 UI 選項。
    - 成功事件包含動態 target 與實際扣除資源。
    - 成功後刷新主介面，再發送一次 Public 開始通知。
    - active、cooldown、invalid target 與 stale target 會顯示對應失敗訊息。
    - 所有失敗都不發送 `trial_start` 通知。
    - 資源失效或頁面失效時，返回可恢復的主介面。

- [ ] Task 5: 核對 SSOT 並執行完整驗證
  - Source/logic files: 無
  - Docs: `docs/deployment.md`, `docs/engine/formula.md`, `docs/managers/trial-manager.md`, `docs/discord/command-handler.md`, `docs/discord/ui-renderer.md`, `docs/discord/notification.md`
  - Tests: 完整 pytest 與 doc-audit
  - Depends on: Task 1-4
  - Acceptance criteria:
    - 六份 SSOT 文件與實作使用相同公式、設定名稱及 custom ID。
    - 每份修改文件的 `last_reviewed` 為 `2026-08-15`。
    - 五份模組文件的 `## Changelog` 記錄本變更。
    - `docs/deployment.md` 在既有 `## Production Deploy` 記錄環境切換要求。
    - 文件不再描述固定 `50000` 目標或點擊後立即開啟。
    - `uv run python -m pytest` 全數通過。
    - doc-audit 不回報本變更新增的缺漏或斷鏈。

## Review Issues

- [x] Issue 1: [Major] Claude plan review 指出 `open_trial_start` 的前置檢查與 manager 失敗分類不一致。修正為開啟及翻頁都重讀 active、cooldown、三種資源與 `max_target`。失敗時返回主介面，不建立空 Select。manager 使用 `stale_target` 表示合法級距超過最新上限，不保留不可達的 `insufficient_resources` 分支。
- [x] Issue 2: [Minor] Claude plan review 要求明確把 `.env.example` 計入 configuration/runtime 範圍。Task 1 維持 `src/core/config.py` 與 `.env.example` 兩個 source/logic 檔案，符合上限。

Claude re-review 於 2026-08-15 通過。Verdict: Approved。無必要修正。

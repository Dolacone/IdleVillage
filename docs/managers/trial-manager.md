---
title: "Module: trial-manager"
doc_type: module
last_reviewed: 2026-07-14
source_paths:
  - src/managers/trial_manager.py
---

# Module: trial-manager

管理全服單一的「村莊試煉」：玩家一鍵開啟一個固定目標的限時挑戰，開啟時系統自動從村莊資源池扣除固定數量的某一種資源，所有玩家的行動產出（不分類型）計入同一進度，達標依貢獻度分配萬能素材。與 `stage-manager` 的五關循環系統完全獨立、並行運作，兩者互不影響。

## 全域單例狀態

| 欄位 | 型別 | 初始值 | 說明 |
| :--- | :--- | :--- | :--- |
| `is_active` | bool (0/1) | 0 | 是否有進行中的試煉 |
| `resource_type` | text / null | null | 開啟試煉時系統自動選中並花費的資源類型（`food`/`wood`/`knowledge`） |
| `target` | int | 0 | 試煉目標值，固定等於 `TRIAL_TARGET_AMOUNT` |
| `progress` | int | 0 | 目前累積進度 |
| `started_at` | timestamp / null | null | 試煉開始時間 |
| `ended_at` | timestamp / null | null | 上一次試煉結束時間（成功或失敗皆更新），用於冷卻判定 |

同時維護一張 `trial_contributions` 表，記錄「當前試煉」每位玩家的累積貢獻（`user_id` 唯一鍵）。開啟新試煉時清空此表；試煉結束（成功或失敗）後也清空。

## 開啟試煉

`start_trial(db, now)`：玩家不需輸入任何資訊，資源類型與目標值皆由系統自動決定。

前置條件（不滿足則 raise ValueError，不扣除任何資源）：
- 目前沒有進行中的試煉（`is_active == 0`）
- 冷卻已過：`ended_at is null` 或 `now - ended_at >= TRIAL_COOLDOWN_SECONDS`
- 村莊三種資源（`food`/`wood`/`knowledge`）中至少一種 `>= TRIAL_TARGET_AMOUNT`

成立後：
1. 計算 `eligible = [r for r in (food, wood, knowledge) if 該資源池 >= TRIAL_TARGET_AMOUNT]`，並從中**均勻隨機**選出一種作為 `resource_type`（`get_eligible_resource_types(db)` 可單獨呼叫取得此列表）。
2. 從村莊資源池扣除 `TRIAL_TARGET_AMOUNT` 個 `resource_type`（呼叫 `resource-manager.withdraw`，不退還機制）。
3. 清空 `trial_contributions`。
4. 寫入 `trial_state`：`is_active=1, resource_type, target=TRIAL_TARGET_AMOUNT, progress=0, started_at=now`（`ended_at` 不變）。

## 進度累加

`add_progress(db, output, user_id, effective_time)` — 由 action-resolver 在**每次完整週期結算（含 partial cycle、burst）**後呼叫，使用**資源不足懲罰前的 output**（比照 stage-manager 對關卡進度的既有規則），不分行動類型（比照升級關「所有項目都算進度」）。

```
若 is_active == 0 → 不做任何事，回傳 None

若 effective_time - started_at > TRIAL_DURATION_SECONDS：
  → 視為已逾時，觸發失敗流程（見下方「失敗（逾時）」），回傳 trial_fail 事件，
    本次 output 不計入進度（試煉已逾時，不應繼續累加）

否則：
  trial_state.progress += output
  trial_contributions[user_id] += output（不存在則建立，初始值 0）

  若 progress >= target：
    → 觸發達成流程（見下方「達成與獎勵分配」），回傳 trial_success 事件
  否則：
    → 回傳 None
```

## 達成與獎勵分配

達標時，讀取 `trial_contributions` 全部列（`total_contribution` = 所有貢獻總和 = 觸發當下的 `progress`），對每位參與者：

```
reward_i = ceil(contribution_i / total_contribution × (target / TRIAL_REWARD_DIVISOR))
```

呼叫 `player-manager.addUniversalMaterial(user_id, reward_i)` 逐一發放。採**無條件進位**：每位參與者各自對自己的分配額 ceil，因此總發放量可能略高於 `target / TRIAL_REWARD_DIVISOR`（多人各自進位所致），此為預期行為，非 bug。

發放完成後：`is_active=0, ended_at=now`，清空 `trial_contributions`。回傳的 `trial_success` 事件包含 `target`、`resource_type`、`total_awarded`（實際發放總量）與 `participants`（`[{user_id, contribution, reward}, ...]`，依 contribution 降冪排序）。

## 失敗（逾時）

`check_timeout(db, now)` — 由 cycle-engine 的 Watcher tick（每次心跳，與個別玩家是否有到期行動無關）呼叫，作為「無人觸發結算時仍需偵測逾時」的後備機制：

```
若 is_active == 0 → 不做任何事，回傳 None
若 now - started_at > TRIAL_DURATION_SECONDS → 觸發失敗流程，回傳 trial_fail 事件
否則 → 回傳 None
```

失敗流程：`is_active=0, ended_at=now`，清空 `trial_contributions`。**資源不退還**。回傳的 `trial_fail` 事件包含 `target`、`resource_type`、`progress`（逾時當下的進度，供公告顯示）。

`add_progress` 內的逾時判定與 `check_timeout` 共用同一段失敗處理邏輯，確保無論由何種觸發來源偵測到逾時，行為一致。

## 操作介面（供其他模組呼叫）

- `get_trial_info(db)` — 回傳 `trial_state` 完整 dict。供沒有既有 fetch-helper 模式的呼叫端使用（例如 `actions.py` 的 `open_trial_start` 按鈕前置條件驗證、`trial_manager` 內部）。Dashboard／`/idlevillage` 主介面的資料擷取層（`notification.py`／`actions.py`／`general.py`）比照其查詢 `stage_state`／`buildings`／`village_resources` 的既有慣例，直接以 `SELECT * FROM trial_state WHERE id=1` 查詢，不透過此函式。
- `get_contribution(db, user_id)` — 回傳指定玩家在當前試煉的累積貢獻（無進行中試煉或無貢獻則回傳 0）。同上，`actions.py` 的主介面資料擷取層可直接查詢 `trial_contributions` 表。
- `get_eligible_resource_types(db)` — 回傳村莊當下可負擔 `TRIAL_TARGET_AMOUNT` 的資源類型列表（`[]` 表示三種都不足）。UI 用此判斷「開啟試煉」按鈕是否該 disabled。
- `start_trial(db, now)` — 開啟試煉，資源類型由系統自動隨機選定；不滿足前置條件時 raise `ValueError`。
- `add_progress(db, output, user_id, effective_time)` — 累加進度；回傳 `None`、`{"type": "trial_success", ...}` 或 `{"type": "trial_fail", ...}`。
- `check_timeout(db, now)` — 逾時後備偵測；回傳 `None` 或 `{"type": "trial_fail", ...}`。

## 環境變數

| 變數 | 預設 | 說明 |
| :--- | :--- | :--- |
| `TRIAL_DURATION_SECONDS` | 43200（12 小時） | 試煉開始後的達標期限 |
| `TRIAL_COOLDOWN_SECONDS` | 43200（12 小時） | 試煉結束（成功或失敗）後，多久才能開啟新試煉 |
| `TRIAL_TARGET_AMOUNT` | 50000 | 試煉固定目標值，同時也是開啟時扣除的資源數量（不再由玩家輸入） |
| `TRIAL_REWARD_DIVISOR` | 100 | 獎勵池計算除數：`reward_pool = target / TRIAL_REWARD_DIVISOR` |

## 與現有系統的關係

- 與 `stage-manager` 完全獨立：試煉進度與關卡進度是兩個分開的計數器，互不影響彼此的通關/逾時判定。
- 試煉花費的資源來自村莊共用資源池（`resource-manager`），與行動結算的資源消耗使用同一個池子，但試煉扣除是一次性開啟成本，不是週期性消耗。
- 試煉獎勵（萬能素材）透過 `player-manager.addUniversalMaterial()` 發放，是 `materials_universal` 目前唯一的實際獲取管道（此前僅能由管理員設定，見 `managers/player-manager.md`）。
- 獻祭素材、詞條抽取/清除、工具強化的萬能素材使用規則不受影響（詳見 `managers/gear-manager.md`、`managers/player-manager.md`）。

## Changelog

- 2026-07-14: 試煉改為完全自動化：`start_trial()` 不再接受 `resource_type`/`target`/`user_id` 參數，目標值固定為 `TRIAL_TARGET_AMOUNT`（取代 `TRIAL_TARGET_STEP`），資源類型由系統在「可負擔 `TRIAL_TARGET_AMOUNT` 的資源類型」中均勻隨機選定（新增 `get_eligible_resource_types()`）。`TRIAL_DURATION_SECONDS` 預設由 86400（24h）改為 43200（12h）。移除 `get_invalid_target_step()`（不再需要驗證玩家輸入的目標值）。
- 2026-07-14: 開啟試煉的呼叫端由獨立的 `trial_cog.py` slash command 改為 `actions.py` 的主介面按鈕（`open_trial_start`）+ Modal（`modal_start_trial`）流程；`get_invalid_target_step()`/`is_cooldown_active()`/`get_cooldown_deadline_unix()` 三個共用前置條件 helper 的呼叫端隨之改變，函式本身行為不變。
- 2026-07-14: 新增模組。

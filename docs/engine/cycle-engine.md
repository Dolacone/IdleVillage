---
title: "Module: cycle-engine"
doc_type: module
last_reviewed: 2026-07-20
source_paths:
  - src/core/engine.py
---

# Module: cycle-engine

管理每位玩家的個人週期計時，並在正確時機觸發行動結算。

## 核心模型：個人獨立週期

每位玩家有自己的 `completion_time`，彼此完全獨立。
- 玩家設定行動後：`completion_time = now + _effective_cycle_seconds(cycle_time_reduce_pct)`
- 第一次設定行動時若 `last_update_time = null`，不做 partial settlement，直接設定 `last_update_time = now` 與新的 `completion_time`
- 任何時刻 `completion_time <= now` → 立即觸發該玩家的結算
- 若玩家長時間未互動導致多個週期積壓，以 while-loop 逐週期補算，不得跳過
- 單次觸發最多補算 `MAX_CYCLES_PER_SETTLEMENT` 個完整週期；若仍有積壓，留待下一次 Watcher / Refresh / 開啟介面繼續補算

## 觸發來源

| 觸發方式 | 結算類型 | 說明 |
| :--- | :--- | :--- |
| **Watcher（背景輪詢）** | 完整週期 | 掃描 `completion_time <= now` 的玩家，逐週期補算 |
| **更換行動** | 比例產出 | 切換前先結算當前週期已經過時間的**比例產出**，再啟動新行動 |
| **AP 爆發執行** | 3 次完整週期 | 立即結算 3 次完整週期，不改變 `completion_time` |
| **開啟介面 / Refresh** | 完整週期補算 | 先檢查 `completion_time`，若已到期則補算完整週期，再渲染 Dashboard |

> Watcher heartbeat 間隔由 `WATCHER_HEARTBEAT_SECONDS` 定義。

Watcher 每次心跳，除了逐一補算到期玩家的週期外，也會呼叫一次 `trial-manager.check_timeout()`
檢查村莊試煉是否逾時（與個別玩家是否有到期行動無關，確保無人行動時試煉仍能在期限後被判定失敗）。
詳見 `managers/trial-manager.md`。

### 自動工具並行結算

除玩家手動行動外，Watcher 也掃描 `player_auto_tools`（見 `managers/auto-tool-manager.md`）中 `completion_time <= now OR next_material_time <= now OR expires_at <= now` 的列，對每列呼叫 `settlement.settle_auto_tool_cycles(user_id, tool_type, now)`。結算為雙時鐘時間序合併：產出時鐘（`completion_time`，受 `MAX_CYCLES_PER_SETTLEMENT` 限制）與素材時鐘（`next_material_time`，每 `AUTO_TOOL_SECONDS_PER_MATERIAL` 扣 1 該工具素材）依時間先後交錯；素材扣不到即停止並釋放，到期（`now >= expires_at` 且已追平）即結束並釋放工具。掃描條件同時看素材與到期時鐘（不僅 `completion_time`），因 `effective_cycle_seconds` 不保證 ≤ 1h，確保素材 tick 與到期在背景也能及時觸發。開介面 / Refresh 時也對該玩家的到期自動工具補算。自動工具的 `cycle_time_reduce` 以該工具自身詞條計算，與手動行動及其他自動工具獨立。

結算順序（固定、可預期，非等效保證）：一次 sweep 內先處理到期玩家手動行動（`players` 掃描加 `ORDER BY user_id`）、再處理到期自動工具（`ORDER BY user_id, tool_type`）、最後 trial timeout。因完整週期會改動共用村莊資源池、關卡/試煉進度與建築等級，順序會影響結果，故明確固定而非宣稱等效。

## 完整週期結算流程

```
1. 呼叫 action-resolver（傳入玩家行動設定）→ 取得 output
2. last_update_time = cycle_end_time
3. effective_secs = _effective_cycle_seconds(affix cycle_time_reduce_pct)
   completion_time += effective_secs（timedelta(seconds=effective_secs)）
4. 呼叫 stage-manager.addProgress(output, actionType)
5. 呼叫 building-manager.checkUpgrade()
6. 呼叫 notification（若有事件）
7. 若新的 completion_time 仍 <= now 且尚未達 `MAX_CYCLES_PER_SETTLEMENT`，重複步驟 1–6（while-loop 補算）
8. 若達到 `MAX_CYCLES_PER_SETTLEMENT` 後仍有積壓，提交本次結果，等待下一次觸發繼續補算
```

> 每次單次結算（含爆發執行的每次）都執行 stage progress、building upgrade check 與通知判定。

## 介面開啟 / Refresh

```
1. 檢查玩家 completion_time
2. 若 completion_time <= now：
   以完整週期 while-loop 補算，直到 completion_time > now 或達到 MAX_CYCLES_PER_SETTLEMENT
3. 更新 Dashboard / 主介面
```

開啟介面與 Refresh 不做 partial cycle；partial cycle 只在更換行動時發生。

## 爆發執行流程

```
消耗 1 AP（呼叫 player-manager.spendAP()）

重複 3 次：
  1. 呼叫 action-resolver → 取得 output
  2. 呼叫 stage-manager.addProgress(output, actionType)  // 每次立即判定通關
  3. 呼叫 building-manager.checkUpgrade()                // 每次立即判定建築升級
  4. 呼叫 notification（若有事件）

completion_time 不變（爆發不影響自動週期計時）
last_update_time 不變
```

> 爆發的 3 次 settlement 視為 3 次完整週期，每次各自依 player-manager 的有效素材掉落率判定素材掉落。第 1 次若觸發通關，第 2、3 次在新關卡繼續累積並使用當下關卡類型計算掉落率。

## 更換行動（比例產出結算）

```
若 completion_time <= now：
  先以完整週期 while-loop 補算，直到 completion_time > now

elapsed        = now - last_update_time
effective_secs = _effective_cycle_seconds(affix cycle_time_reduce_pct)
ratio          = elapsed / effective_secs（0 ~ 1）

若 `last_update_time = null`：
  1. 不做 partial settlement
  2. 寫入新行動類型與目標
  3. completion_time = now + effective_secs（_effective_cycle_seconds 以新行動的 affix 計算）
  4. last_update_time = now

否則：
  1. 以 ratio 計算比例成本與比例產出（floor）
  2. 將比例產出計入資源 / building XP
  3. 將比例產出計入 stage-manager，若關卡逾時則只對 stage progress 套用逾時倍率
  4. partial cycle 不掉落素材
  5. 寫入新行動類型與目標
  6. completion_time = now + effective_secs（_effective_cycle_seconds 以新行動的 affix 計算）
  7. last_update_time = now
```

## player 欄位（週期相關）

| 欄位 | 說明 |
| :--- | :--- |
| `completion_time` | 當前週期結束時間 |
| `last_update_time` | action timeline marker；完整週期補算時設為 cycle_end_time，更換行動時設為 now |

## 週期設定

- **週期長度**：`ACTION_CYCLE_MINUTES`（基礎值；玩家工具詞條 `cycle_time_reduce` 可縮短）
- **有效週期秒**：`floor(ACTION_CYCLE_MINUTES * 60 * (1 - cycle_time_reduce_pct/100))`，最低 60 秒。抽取為 `_effective_cycle_seconds(cycle_time_reduce_pct)` 並統一用於：
  - 玩家設定行動時計算 completion_time
  - 補算每次推進 completion_time
  - partial ratio 計算（`elapsed / effective_cycle_seconds`）
- `cycle_time_reduce_pct` 從 `affix_manager.get_affix_bonuses(db, user_id, action)["cycle_time_reduce"]` 取得（以玩家當前 action 對應工具的詞條為準）
- **Watcher heartbeat**：`WATCHER_HEARTBEAT_SECONDS`
- **單次補算週期上限**：`MAX_CYCLES_PER_SETTLEMENT`
- **AP 回復**：由 `ap_full_time` 倒推，見 `managers/player-manager.md`

## Changelog

- 2026-07-20: Auto-tool settlement is now dual-clock (production + hourly material tick); the auto-tool watcher scan triggers on `completion_time`, `next_material_time`, or `expires_at`. Running out of material stops the tool. See `managers/auto-tool-manager.md`.
- 2026-07-17: Watcher and open-interface catch-up now also settle due auto-tools (`settlement.settle_auto_tool_cycles`), independent per tool. Both due-scan queries are ordered (`players` by user_id, `player_auto_tools` by user_id+tool_type) for a fixed settlement order. See `managers/auto-tool-manager.md`.
- 2026-07-14: Watcher tick now also calls `trial-manager.check_timeout()` once per heartbeat, independent of any player's `completion_time`.
- 2026-05-22: Updated cycle timing to use `_effective_cycle_seconds(cycle_time_reduce_pct)` at all three calculation points (change_action, catch-up advance, partial ratio). `cycle_time_reduce` affix scoped to player's current action tool.
- 2026.05.08.00: Burst material rolls now use the effective drop rate for the current stage at each settlement.

---
title: "Module: cycle-engine"
doc_type: module
last_reviewed: 2026-05-01
source_paths:
  - src/core/engine.py
---

# Module: cycle-engine

管理每位玩家的個人週期計時，並在正確時機觸發行動結算。

## 核心模型：個人獨立週期

每位玩家有自己的 `completion_time`，彼此完全獨立。
- 玩家設定行動後：`completion_time = now + ACTION_CYCLE_MINUTES`
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

## 完整週期結算流程

```
1. 呼叫 action-resolver（傳入玩家行動設定）→ 取得 output
2. last_update_time = cycle_end_time
3. completion_time += ACTION_CYCLE_MINUTES
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

> 爆發的 3 次 settlement 視為 3 次完整週期，每次各自以 MATERIAL_DROP_RATE 判定素材掉落。第 1 次若觸發通關，第 2、3 次在新關卡繼續累積。

## 更換行動（比例產出結算）

```
若 completion_time <= now：
  先以完整週期 while-loop 補算，直到 completion_time > now

elapsed = now - last_update_time
ratio   = elapsed / ACTION_CYCLE_SECONDS（0 ~ 1）

若 `last_update_time = null`：
  1. 不做 partial settlement
  2. 寫入新行動類型與目標
  3. completion_time = now + ACTION_CYCLE_MINUTES
  4. last_update_time = now

否則：
  1. 以 ratio 計算比例成本與比例產出（floor）
  2. 將比例產出計入資源 / building XP
  3. 將比例產出計入 stage-manager，若關卡逾時則只對 stage progress 套用逾時倍率
  4. partial cycle 不掉落素材
  5. 寫入新行動類型與目標
  6. completion_time = now + ACTION_CYCLE_MINUTES
  7. last_update_time = now
```

## player 欄位（週期相關）

| 欄位 | 說明 |
| :--- | :--- |
| `completion_time` | 當前週期結束時間 |
| `last_update_time` | action timeline marker；完整週期補算時設為 cycle_end_time，更換行動時設為 now |

## 週期設定

- **週期長度**：`ACTION_CYCLE_MINUTES`
- **Watcher heartbeat**：`WATCHER_HEARTBEAT_SECONDS`
- **單次補算週期上限**：`MAX_CYCLES_PER_SETTLEMENT`
- **AP 回復**：由 `ap_full_time` 倒推，見 `managers/player-manager.md`

# Core: Engine (Trigger and Settlement)

定義系統如何實作延遲計算與狀態同步, 確保不同 AI Session 之間的實作邏輯一致.

### 1. 觸發層級 (Trigger Levels)

#### A. 個體主動觸發 (Player-Active Trigger)
- 指令: `/idlevillage`, 行動切換與提交.
- 邏輯:
  1. 若需要, 先對村莊執行損耗結算.
  2. 對該玩家執行 [標準結算流程].
  3. 若玩家提交新的非 `idle` 行動, 先結算目前進度, 再嘗試啟動新的 1 小時循環.
  4. UI 刷新會保留未完成循環的 `completion_time`, 並將已完成的進度同步到資料庫.


#### B. 集體虛擬觸發 (Village-Collective Trigger)
- 指令: `/idlevillage` 開啟村莊介面.
- 邏輯: 
  1. 結算建築 XP 損耗 (更新 `last_tick_time`).
  2. 結算該玩家截至目前邊界時間的進度並同步狀態.
  3. 回傳村莊資源、建築 XP、玩家狀態與預計完成時間.

#### C. 被動自動觸發 (The Watcher Trigger)
- 頻率: 每 300 秒.
- 對象: completion_time <= Now 的玩家.
- 邏輯:
  1. 清理過期或已耗盡的資源節點.
  2. 對 `completion_time <= Now` 的玩家強制執行 [標準結算流程].
  3. 對所有村莊執行建築損耗結算.

### 2. 標準結算流程 (Settlement Steps)

所有的結算必須精確到秒, 並遵循以下順序:
1. 計算邊界: TargetTime = min(Now, completion_time).
2. 重算玩家素質: 依 `player_actions_log` 的 150 小時滑動窗口更新 `player_stats`.
3. 計算 Delta: 時差 = TargetTime - last_update_time.
4. 紀錄行動片段:
   - 若 `delta > 0` 且玩家不是 `missing`, 寫入一筆 `player_actions_log`.
   - `gathering` 會依節點類型寫為 `gathering_food`, `gathering_wood`, `gathering_stone`.
5. 資源 / XP 結算:
   - `idle`: 依 PER + KNO 產出村莊糧食.
   - `gathering`: 依節點類型與玩家素質結算食物或木石產出, 並扣除節點儲量.
   - `building`: 依 KNO + END 增加目標建築 XP.
   - `exploring`: 依 AGI + PER 取得分鐘預算, 並依探索權重與成本新增資源節點.
   - 村莊資源入庫時, 受 `Storage Capacity` 與 `Resource Yield` 建築效果影響.
6. 資料更新:
   - 檢查玩家是否符合 `missing` 條件 (7 天未發言且 7 天未完成循環).
   - 若玩家主動中斷, 狀態改為 `idle`.
   - 若完整循環結束且資源足夠, 嘗試自動啟動下一個 1 小時循環; 否則改為 `idle`.
   - 若循環尚未結束, 保留原本的 `completion_time`.
   - 更新 `status`, `target_id`, `last_update_time`, `completion_time`.
7. 狀態轉移: 
   - 系統不再使用 satiety、travel、moving 或 return-trip 狀態.
   - 有效狀態以 `idle`, `gathering`, `building`, `exploring`, `missing` 為主.

### 3. 1 小時租約啟動 (Lease Start)

- 任何非 `idle` 行動在啟動時先執行資源預扣.
- `gathering` / `exploring`: 扣除 1 糧食.
- `building`: 扣除 1 糧食, 10 木材, 5 石材.
- 若目標無效、節點過期、節點儲量不足或村莊資源不足, 啟動失敗且不變更玩家狀態.
- 成功啟動後:
  - 更新 `status`, `target_id`, `last_update_time`.
  - 設定 `completion_time = now + (1.0 + FoodEfficiencyLevel * 0.2) hours`.

## Changelog
- 2026.04.07.00: Updated to reflect the 1-hour lease engine, settlement flow, and removal of satiety/travel logic. See [2026.04.07.00.md](../../changelogs/2026.04.07.00.md)

# Core: Engine (Trigger and Settlement)

定義系統如何實作延遲計算、公告同步與狀態同步, 確保不同 AI Session 之間的實作邏輯一致.

### 1. 觸發層級 (Trigger Levels)

#### A. 個體主動觸發 (Player-Active Trigger)
- 指令: `/idlevillage`, 行動切換與提交, Refresh Status.
- 邏輯:
  1. 若需要, 先對村莊執行損耗結算.
  2. 對該玩家執行標準結算流程.
  3. 若玩家提交新的非 `idle` 行動, 先結算目前進度, 再嘗試啟動新的 Action Cycle.
  4. 嘗試依節流規則更新 Village Announcement.

#### B. 集體虛擬觸發 (Village-Collective Trigger)
- 指令: `/idlevillage` 開啟村莊介面, `/idlevillage-announcement` 建立或刷新公告面板.
- 邏輯:
  1. 結算建築 XP 損耗 (更新 `last_tick_time`).
  2. 結算該玩家截至目前邊界時間的進度並同步狀態.
  3. 回傳村莊資源、建築 XP、玩家狀態與預計完成時間.
  4. 若公告頻道已設定, 嘗試更新公開儀表板.

#### C. 被動自動觸發 (The Watcher Trigger)
- 頻率: 每 300 秒.
- 對象: `completion_time <= Now` 的玩家.
- 邏輯:
  1. 清理過期或已耗盡的資源節點.
  2. 先執行全域 inactivity scan, 將 7 天未發言且 7 天未執行 `/idlevillage` 的玩家標記為 `missing`.
  3. 對 `completion_time <= Now` 的玩家強制執行標準結算流程.
  4. 對所有村莊執行建築損耗結算.

### 2. 標準結算流程 (Settlement Steps)

所有的結算必須精確到秒, 並遵循以下順序:
1. 若玩家存在已逾期的完整循環, 必須以 while-loop 逐個循環回補, 不可直接跳到 `Now`.
2. 每個循環切片都先重算玩家素質: 依 `player_actions_log` 最新 150 筆紀錄更新 `player_stats`.
3. 計算 Delta: `SliceEnd - SliceStart`.
4. 紀錄行動片段:
   - 若 `delta > 0` 且玩家不是 `missing`, 依 `ACTION_CYCLE_MINUTES` 切割片段並寫入 `player_actions_log`.
   - `gathering` 會依節點類型寫為 `gathering_food`, `gathering_wood`, `gathering_stone`.
5. 資源 / XP 結算:
   - `idle`: 依 PER + KNO 產出村莊糧食, 品質固定 50%.
   - `gathering`: 依節點類型與玩家素質結算食物或木石產出, 並扣除節點儲量.
   - `building`: 依 KNO + END 增加目標建築 XP.
   - `exploring`: 依目前活躍節點數做 Inverse-Square 成功判定, 成功時建立高斯品質的新節點.
   - 村莊資源入庫時, 受 `Storage Capacity` 與 `Resource Yield` 建築效果影響.
6. 資料更新:
   - 檢查玩家是否符合 `missing` 條件 (7 天未發言且 7 天未執行 `/idlevillage`).
   - 若玩家主動中斷, 狀態改為 `idle`.
   - 若完整循環結束且資源足夠, 以該循環結束時間作為下一個 Lease 的起點, 嘗試自動啟動下一個 Action Cycle; 否則改為 `idle`.
   - 若循環尚未結束, 保留原本的 `completion_time`.
   - 更新 `status`, `target_id`, `last_update_time`, `completion_time`.

### 3. Action Cycle 啟動 (Lease Start)

- 任何非 `idle` 行動在啟動時先執行資源預扣.
- `gathering` / `exploring`: 扣除 `max(1, 10 - FoodEfficiencyLevel)` 糧食.
- `building`: 扣除 `max(1, 10 - FoodEfficiencyLevel)` 糧食, `10` 木材, `5` 石材.
- 若目標無效、節點過期、節點儲量不足或村莊資源不足, 啟動失敗且不變更玩家狀態.
- 成功啟動後:
  - 更新 `status`, `target_id`, `last_update_time`.
  - 設定 `completion_time = now + ACTION_CYCLE_MINUTES`.

### 4. 公告同步與發現通知 (Announcement Sync)

- 村莊公告資料保存在 `villages.announcement_channel_id`, `villages.announcement_message_id`, `villages.last_announcement_updated`.
- `/idlevillage-announcement` 會在觸發頻道建立或刷新單一公開儀表板訊息.
- 若公告訊息遺失, 下次更新時需要清除舊的 `announcement_message_id` 並重建.
- 任一探索新節點發現成功時, 系統會額外發送一則 discovery 訊息到已設定的公告頻道.

### 5. 日誌格式 (Structured Logging)

- 所有命令、結算與 Watcher 掃描輸出至 `stdout`.
- 格式固定為 `[REQ_ID] [USER_ID/SYSTEM] {TYPE}: {MESSAGE}`.
- 常用類別: `CMD`, `RESP`, `COST`, `SETTLE`, `STATUS`, `ERROR`.

## Changelog
- 2026.04.07.00: Updated to reflect the 1-hour lease engine, settlement flow, and removal of satiety/travel logic. See [2026.04.07.00.md](../../changelogs/2026.04.07.00.md)
- 2026.04.08.00: Updated to configurable Action Cycles, 150-entry stat recalculation, structured logging, and public announcement sync behavior. See [2026.04.08.00.md](../../changelogs/2026.04.08.00.md)

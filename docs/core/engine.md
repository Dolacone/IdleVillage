# Core: Engine (Trigger and Settlement)

定義系統如何實作延遲計算與狀態同步, 確保不同 AI Session 之間的實作邏輯一致.

### 1. 觸發層級 (Trigger Levels)

#### A. 個體主動觸發 (Player-Active Trigger)
- 指令: `/idlevillage`, `/me`, 取消行動.
- 邏輯: 必須先對該玩家執行 [標準結算流程] 後才回傳資訊或更改狀態.


#### B. 集體虛擬觸發 (Village-Collective Trigger)
- 指令: 查看村莊總資源, 建築狀態.
- 邏輯: 
  1. 結算建築 XP 損耗 (更新 last_tick_time).
  2. 暫時計算所有正在工作者的預期產出 (但不寫回 DB), 僅供顯示最新的資源估算.

#### C. 被動自動觸發 (The Watcher Trigger)
- 頻率: 每 300 秒.
- 對象: completion_time <= Now 的玩家.
- 邏輯: 強制執行 [標準結算流程], 並根據 auto_restart 標籤處理狀態轉換.

### 2. 標準結算流程 (Settlement Steps)

所有的結算必須精確到秒, 並遵循以下順序:
1. 計算邊界: TargetTime = min(Now, completion_time).
2. 計算 Delta: 時差 = TargetTime - last_update_time.
3. 資源結算: 
   - 產出量 = Delta * 基礎速率 * 效率係數 * 建築加成 * 節點品質.
   - 飽食度處理: 
     - 若為 Active 狀態: satiety_deadline 保持不變 (剩餘時間減少).
     - 若為 Idle 狀態: 將 satiety_deadline 加上 Delta (剩餘時間不變).
     - 若玩家在村莊中進入 Idle 狀態, 或由 Idle 狀態準備離開開始新行動, 需檢查是否觸發村莊自動補給.
4. 資料更新:
   - 更新村莊資源庫存與建築 XP.
   - 更新玩家 satiety_deadline 與 weight.
   - 將 last_update_time 設為 TargetTime.
   - 若本次結算造成玩家狀態切換, 寫入一筆 player_actions_log (action_type=剛結束的狀態, start=前次更新, end=TargetTime).
5. 狀態轉移: 
   - 若 Now >= completion_time, 根據完成原因 (完成工作, 負重已滿, 或 Now >= satiety_deadline) 啟動回程或重啟邏輯.
   - 若是因為 Now >= satiety_deadline 觸發, 玩家強制轉為移動回村狀態.

### 3. 移動與回程邏輯 (Travel Logic)

- 出發 (En-route): 狀態標記為 moving, 位置為 en_route.
- 取消/失敗: 若在此階段終止, 返程所需時間 = (Now - start_time).
- 抵達 (Arrival): 狀態改為 working, 位置為 at_node.
- 消耗: 前往目標消耗飽食度, 回程返回村莊則免.

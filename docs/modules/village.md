# Module: Village

定義村莊與 Discord 伺服器的綁定關係, 共用倉庫管理以及混合式結算邏輯.

### 1. 伺服器綁定 (Guild Binding)
- 一個 Discord 伺服器 (Guild ID) 對應一個唯一的村莊資料實例.
- 需透過指令 `/idlevillage-initial` 進行初始化綁定.

### 2. 共用倉庫基礎邏輯 (Repository Logic)
- 資源入庫: 玩家抵達村莊時, 將身上的資源 (Wood, Stone, Food) 累加至村莊表, 並歸零個人負重.
- 自動補給 (Satiety Refill):
  - 當玩家位於村莊且 (satiety_deadline - Now) < 95 小時 (95%) 時自動觸發.
  - 消耗村莊糧食以恢復飽食度:
    - 所需小時數 = 100 - 剩餘小時數.
    - 消耗糧食量 = 所需小時數 / Food Efficiency.
    - 更新 satiety_deadline = Now + 100 小時.
  - 恢復效率受 Food Efficiency 建築加成.


### 3. 混合式損耗演算法 (Hybrid Decay)
為了確保離線期間建築仍會損壞, 採用延遲結算模型:
- 觸發時機: 任何涉及村莊狀態的指令或 Watcher 掃描 (300s).
- 演算法:
  1. 時差 (Delta): 現在時間 - last_tick_time.
  2. 總損耗: (Delta/3600) * (10 + 活躍玩家數).
  3. 套用: 將 villages 表中所有 XP 欄位減去總損耗 (最小為 0).
  4. 更新: last_tick_time = 現在時間.

### 4. 平衡性參數 (Balance Numbers)
- 初始糧食: 100.
- 初始木材/石材: 0.
- 損耗基礎值: 10/小時.

### 5. 初始值 (Initial Village State)
- 糧食: 100.
- 木材/石材: 0.
- 所有建築 XP: 0 (等級 0).
- 上次結算時間: 創立時間 (Now).

# Module: Village

定義村莊與 Discord 伺服器的綁定關係, 共用倉庫管理以及混合式結算邏輯.

### 1. 伺服器綁定 (Guild Binding)
- 一個 Discord 伺服器 (Guild ID) 對應一個唯一的村莊資料實例.
- 需透過指令 `/idlevillage-initial` 進行初始化綁定.
- `/idlevillage-initial` 僅能在尚未建立村莊的伺服器上使用, 不提供重置既有村莊的功能.

### 2. 共用倉庫基礎邏輯 (Repository Logic)
- 資源預扣 (Pre-deduction): 
  - 任何非 `idle` 行動在 1 小時循環開始時, 立即扣除村莊倉庫所需資源 (糧食、木材、石材).
  - 資源扣除採先結算者優先 (First-come, first-served).
  - 資源一經扣除概不退還 (Non-refundable).
- 自動續期判定 (Auto-restart Check):
  - 1 小時循環結束後, 系統檢查村莊倉庫資源.
  - 若資源不足以支付下一個 1 小時循環, 玩家狀態將自動變更為 `idle`.
- 資源入庫 (Settlement):
  - 行動週期正常結束後, 產出的資源直接累加至村莊表.
  - 若玩家在週期結束前主動切換行動, 系統會先結算目前已經完成的部分進度, 再開始新的行動週期.
- 溢出處理: 
  - 若存入資源後超過 `Storage Capacity` 建築提供的上限, 溢出的資源將直接被捨棄 (Discarded).
- 歸零: 轉移完成後, 玩家個人的暫存數據歸零.

### 3. 混合式損耗演算法 (Hybrid Decay)
為了確保離線期間建築仍會損壞, 採用延遲結算模型:
- 觸發時機: 任何涉及村莊狀態的指令或 Watcher 掃描 (300s).
- 演算法:
  1. 時差 (Delta): 現在時間 - last_tick_time.
  2. 總損耗: (Delta/3600) * (10 + 活躍玩家數).
  3. 套用: 將 villages 表中所有 XP 欄位減去總損耗 (最小為 0).
  4. 更新: last_tick_time = 現在時間.

### 4. 建築效果調整 (Building Effects)
- 糧食效率 (Food Efficiency): 提升單位糧食的可支撐時長.
  - 公式: 1 單位糧食可供行動小時數 = 1.0 + (Level * 0.2).
- 儲存容量 (Storage Capacity): 
  - 總容量 = 1000 * (2 ^ Level).

### 5. 平衡性參數 (Balance Numbers)
- 初始糧食: 0.
- 初始木材/石材: 0.
- 損耗基礎值: 10/小時.

### 6. 初始值 (Initial Village State)
- 糧食: 0.
- 木材/石材: 0.
- 所有建築 XP: 0 (等級 0).
- 上次結算時間: 創立時間 (Now).

## Changelog
- 2026.04.07.00: Replaced satiety refill with 1-hour lease logic. Updated building effects. See [2026.04.07.00.md](../../changelogs/2026.04.07.00.md)

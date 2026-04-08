# Module: Village

定義村莊與 Discord 伺服器的綁定關係, 共用倉庫管理以及行動週期 (Action Cycle) 租賃模型.

### 1. 伺服器綁定 (Guild Binding)
- 一個 Discord 伺服器 (Guild ID) 對應一個唯一的村莊資料實例.
- 需透過指令 `/idlevillage-initial` 進行初始化綁定.

### 2. 行動週期與租賃模型 (Action Cycle & Lease Model)
- 行動週期 (Cycle Duration): 
  - 遊戲的核心計算單位. 預設值為 60 分鐘, 可由環境變數 `ACTION_CYCLE_MINUTES` 控制.
  - 縮短週期會同步加速資源產出與消耗頻率, 保持產銷比例恆定.
- 資源預扣 (Pre-deduction): 
  - 任何非 `idle` 行動在週期開始時, 立即扣除村莊倉庫所需資源.
  - 糧食消耗: `max(1, 10 - Food_Efficiency_Level)`.
  - 建設額外消耗: `10 木材`、`5 石材`.
  - 資源扣除採先結算者優先 (First-come, first-served).
  - 資源一經扣除概不退還 (Non-refundable).
- 自動續期判定 (Auto-restart Check):
  - 週期結束後, 系統檢查村莊倉庫資源.
  - 若資源不足以支付下一個週期, 玩家狀態將自動變更為 `idle`.
- 資源入庫 (Settlement):
  - 行動週期正常結束後, 產出的資源直接累加至村莊表.
  - 若玩家在週期結束前主動切換行動, 系統會先結算目前已經完成的部分進度, 再開始新的行動週期.
- 溢出處理: 
  - 若存入資源後超過 `Storage Capacity` 建築提供的上限, 溢出的資源將直接被捨棄 (Discarded).

### 3. 混合式損耗演算法 (Hybrid Decay)
為了確保離線期間建築仍會損壞, 採用延遲結算模型:
- 觸發時機: 任何涉及村莊狀態的指令或 Watcher 掃描.
- 演算法:
  1. 時差 (Delta): 現在時間 - last_tick_time.
  2. 總損耗: (Delta/3600) * (10 + 活躍玩家數).
  3. 套用: 將 villages 表中所有 XP 欄位減去總損耗 (最小為 0).
  4. 更新: last_tick_time = 現在時間.

### 4. 建築效果調整 (Building Effects)
- 廚房 (Food Efficiency): 降低每次行動週期所需的糧食消耗.
  - 公式: 消耗 = `max(1, 10 - Level)`.
- 儲存容量 (Storage Capacity): 
  - 總容量 = 1000 * (2 ^ Level).
- 加工 (Resource Yield): 
  - 全體產量加成 = 1.0 + (Level * 0.1).

## Changelog
- 2026.04.07.00: Replaced satiety refill with 1-hour lease logic. Updated building effects. - See [2026.04.07.00.md](../changelogs/2026.04.07.00.md)
- 2026.04.08.00: Implemented Action Cycle Duration and updated Food Efficiency cost logic. - See [2026.04.08.00.md](../changelogs/2026.04.08.00.md)

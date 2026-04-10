# Module: Village

定義村莊與 Discord 伺服器的綁定關係, 資源與村莊增益 (Buffs) 的正規化管理以及行動週期 (Action Cycle) 租賃模型.

### 1. 伺服器綁定 (Guild Binding)
- 一個 Discord 伺服器 (Guild ID) 對應一個唯一的村莊資料實例.
- `villages.id` 直接使用 Discord Guild ID 作為主鍵.
- 玩家資料以 `(discord_id, village_id)` 為識別鍵, 因此同一 Discord 使用者可以在不同伺服器持有彼此獨立的村民狀態.
- 需透過指令 `/idlevillage-initial` 進行初始化綁定.
- 初始化資源 (v2026.04.09.01): 村莊建立時, 系統自動在 `village_resources` 寫入糧食、木材、石材各 1,000 單位.

### 2. 行動週期與租賃模型 (Action Cycle & Lease Model)
- 行動週期 (Cycle Duration): 
  - 遊戲的核心計算單位. 預設值為 60 分鐘, 可由環境變數 `ACTION_CYCLE_MINUTES` 控制.
  - 縮短週期會同步加速資源產出與消耗頻率, 保持產銷比例恆定.
- 資源預扣 (Pre-deduction): 
  - 任何非 `idle` 行動在週期開始時, 立即扣除村莊倉庫所需資源.
  - 基礎產出 (BASE_OUTCOME): 50. (v2026.04.09.01)
  - 建設額外消耗 (BASE_BUILD_COST): 50 木材、50 石材. (v2026.04.09.01)
  - 糧食基礎消耗 (BASE_FOOD_COST): 20. (v2026.04.09.01)
  - 實際糧食消耗: `max(2, 20 - 2 * Kitchen_Level)`. (v2026.04.09.01)
  - 資源扣除採先結算者優先 (First-come, first-served).
  - 資源一經扣除概不退還 (Non-refundable).
- 自動續期判定 (Auto-restart Check):
  - 週期結束後, 系統檢查村莊倉庫資源.
  - 若資源不足以支付下一個週期, 玩家狀態將自動變更為 `idle`.
- 資源入庫 (Settlement):
  - 行動週期正常結束後, 產出的資源直接累加至 `village_resources` 表. (v2026.04.09.01)
- 溢出處理: 
  - 若存入資源後超過 `Storage Capacity` 增益提供的上限, 溢出的資源將直接被捨棄 (Discarded).

### 3. 正規化數據結構 (Normalized Schema) (v2026.04.09.01)
為了支援未來擴充, 資源與增益 (建築) 資料已從 `villages` 表分離:
- **`village_resources` 表**: 儲存 `(village_id, resource_type, amount)`. 支援無限資源類型擴展.
- **`buffs` 表**: 儲存 `(village_id, buff_id, xp)`. 透過累積 XP 提升增益等級 (Level), 適用於建築與長期效果.

### 4. 混合式損耗演算法 (Hybrid Decay)
為了確保離線期間建築仍會損壞, 採用延遲結算模型:
- 觸發時機: 任何涉及村莊狀態的指令或 Watcher 掃描.
- 演算法:
  1. 時差 (Delta): 現在時間 - last_tick_time.
  2. 週期單位 (Cycle Units): `Delta_Minutes / ACTION_CYCLE_MINUTES`.
  3. 損耗公式 (每週期): `int(活躍玩家數 * 0.5) + int(當前 XP * (0.001 + 當前 XP / 5,000,000))`.
  4. 總損耗: `週期單位 * 每週期損耗`.
  5. 套用: 將 `buffs` 表中所有相關項目的 XP 減去總損耗 (最小為 0).
  6. 降級偵測: 若結算後增益等級低於結算前, 系統將發送降級公告. (v2026.04.09.01)
  7. 更新: last_tick_time = 現在時間.

### 5. 村莊增益 (Buffs/Buildings)
- 廚房 (Food Efficiency): 降低每次行動週期所需的糧食消耗.
  - Buff ID: 1
  - 公式: 消耗 = `max(2, 20 - 2 * Level)`. (v2026.04.09.01)
- 儲存容量 (Storage Capacity): 
  - Buff ID: 2
  - 總容量 = 1000 * (2 ^ Level).
- 加工 (Resource Yield): 
  - Buff ID: 3
  - 全體產量加成 = 1.0 + (Level * 0.1).

## Changelog
- 2026.04.07.00: Replaced satiety refill with 1-hour lease logic. Updated building effects. - See [2026.04.07.00.md](../changelogs/2026.04.07.00.md)
- 2026.04.08.00: Implemented Action Cycle Duration and updated Food Efficiency cost logic. - See [2026.04.08.00.md](../changelogs/2026.04.08.00.md)
- 2026.04.08.03: Switched to dynamic exponential decay model for buildings. - See [2026.04.08.03.md](../changelogs/2026.04.08.03.md)
- 2026.04.09.01: Normalized Resources and Buildings (as "buffs") into separate tables. Performed numerical rebalance. Added level-down notifications. - See [2026.04.09.01.md](../changelogs/2026.04.09.01.md)

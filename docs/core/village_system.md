# Core: Village System

定義村莊與 Discord 伺服器的綁定關係.

### 1. 伺服器初始化 (Guild Initialization)
- 觸發事件: 透過指令 `/idlevillage-initial` 手動初始化 (僅限特定管理員使用).
- 初始邏輯:
  - 建立對應的 villages 紀錄.
  - 初始糧食: 100.
  - 初始木材/石材: 0.
  - 建築 XP: 0.

### 2. 資料庫結構 (Table: villages)
| 欄位名 | 型別 | 說明 |
| :--- | :--- | :--- |
| id | INTEGER (PK) | |
| guild_id | TEXT (Unique) | |
| food | INTEGER | |
| wood | INTEGER | |
| stone | INTEGER | |
| food_efficiency_xp | INTEGER | |
| storage_capacity_xp | INTEGER | |
| resource_yield_xp | INTEGER | |
| last_tick_time | TIMESTAMP | |

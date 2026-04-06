# Core: Player System

定義玩家的核心狀態與基礎資料結構.

### 1. 活躍度定義 (Active Status)
- 活躍玩家: 7 天內於 Discord 伺服器有發言紀錄.
- 處理: 非活躍玩家會被系統自動設為 Idle 並移回村莊.

### 2. 資料庫結構 (Table: players)
| 欄位名 | 型別 | 說明 |
| :--- | :--- | :--- |
| id | INTEGER (PK) | |
| discord_id | TEXT (Unique) | |
| village_id | INTEGER (FK) | 關聯至 villages.id |
| satiety_deadline | TIMESTAMP | 飽食度歸零的預計時間點 |
| last_message_time | TIMESTAMP | 用於追蹤玩家活躍度 (7 天內發言) |
| current_weight | INTEGER | 當前負重 |
| status | TEXT | idle, moving, working, exploring |
| location_status | TEXT | at_village, at_node, en_route |
| current_action_type | TEXT | gather, build, explore |
| target_node_id | INTEGER (FK) | |
| auto_restart | INTEGER | 0/1 |
| last_update_time | TIMESTAMP | |
| completion_time | TIMESTAMP | |

### 3. 初始值 (Initial Values for New Players)
- Satiety Deadline: Now + 100 小時
- Status: idle
- Location: at_village
- Current Weight: 0
- Auto Restart: 0

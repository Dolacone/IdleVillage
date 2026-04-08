# Core: Player System

定義玩家的核心狀態與基礎資料結構.

### 1. 狀態與活躍度 (Status and Activity)
- 不活躍 (Inactive): 7 天內未於 Discord 伺服器發言, 且 7 天內未提交過任何 IdleVillage 指令/行動.
- 失蹤 (Missing): 若玩家被判定為不活躍, 狀態將變更為 `missing`.
- 處理: `missing` 狀態下的玩家不參與 `idle` 產出, 且會被移回村莊.

### 2. 資料庫結構 (Table: players)
| 欄位名 | 型別 | 說明 |
| :--- | :--- | :--- |
| id | INTEGER (PK) | |
| discord_id | TEXT | (discord_id, village_id) 組合為 Unique |
| village_id | INTEGER (FK) | 關聯至 villages.id |
| last_message_time | TIMESTAMP | 用於追蹤玩家活躍度 (7 天內發言或行動) |
| status | TEXT | idle, gathering, building, exploring, missing |
| target_id | INTEGER | 當前行動的目標 ID (如果是採集則為 resource_nodes.id, 建設則為建築類別) |
| last_update_time | TIMESTAMP | 本次行動片段開始或上次結算的時間 |
| completion_time | TIMESTAMP | 當前 Action Cycle 的預計完成時間 |

### 3. 初始值 (Initial Values for New Players)
- Status: idle
- Last Update Time: Now (TIMESTAMP)
- Last Message Time: Now (TIMESTAMP)

## Changelog
- 2026.04.07.00: Simplified status and schema. Removed weight and satiety. See [2026.04.07.00.md](../../changelogs/2026.04.07.00.md)
- 2026.04.08.00: Added exploring to the active player states and clarified Action Cycle timing fields. See [2026.04.08.00.md](../../changelogs/2026.04.08.00.md)

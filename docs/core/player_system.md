# Core: Player System

定義玩家的核心狀態與基礎資料結構.

### 1. 狀態與活躍度 (Status and Activity)
- 不活躍 (Inactive): 7 天內未於 Discord 伺服器發言, 且 7 天內未執行過 `/idlevillage`.
- 判定時不考慮 in-game actions, 例如按鈕切換行動、Refresh Status、或背景中的行動循環進度.
- 失蹤 (Missing): 若玩家被判定為不活躍, 狀態將變更為 `missing`.
- 處理: `missing` 狀態下的玩家不參與 `idle` 產出, 且會被移回村莊.

### 2. 資料庫結構 (Table: players)
| 欄位名 | 型別 | 說明 |
| :--- | :--- | :--- |
| discord_id | INTEGER (PK-part) | 與 village_id 組成複合主鍵 |
| village_id | INTEGER (FK) | 關聯至 villages.id |
| last_message_time | TIMESTAMP | 玩家最後一次在該 Discord Guild 發言的時間 |
| last_command_time | TIMESTAMP | 玩家最後一次執行 `/idlevillage` 的時間 |
| status | TEXT | idle, gathering, building, exploring, missing |
| target_id | INTEGER | 當前行動的目標 ID (如果是採集則為 resource_nodes.id, 建設則為建築類別) |
| last_update_time | TIMESTAMP | 本次行動片段開始或上次結算的時間 |
| completion_time | TIMESTAMP | 當前 Action Cycle 的預計完成時間 |

### 3. 初始值 (Initial Values for New Players)
- Status: idle
- Last Update Time: Now (TIMESTAMP)
- Last Message Time: 空值, 直到玩家在 Guild 發言
- Last Command Time: 玩家首次執行 `/idlevillage` 時寫入

## Changelog
- 2026.04.07.00: Simplified status and schema. Removed weight and satiety. See [2026.04.07.00.md](../../changelogs/2026.04.07.00.md)
- 2026.04.08.00: Added exploring to the active player states and clarified Action Cycle timing fields. See [2026.04.08.00.md](../../changelogs/2026.04.08.00.md)

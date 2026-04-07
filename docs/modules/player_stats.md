# Module: Player Stats and Status

定義素質計算規則、加成係數以及 150h 滑動窗口機制.

### 1. 150h 滑動窗口素質 (150h Sliding Window)
- 計算: 基礎 50 點 + 過去 150 小時行動紀錄所獲得的點數.
- 紀錄方式: `player_actions_log` 在每 1 小時行動循環結束時寫入一筆紀錄, 記錄該行動的 `action_type`, `start_time`, `end_time`.
- 行動分配權重 (每行動 1 小時獲得之點數):
  - `idle`: 觀察 (PER) +1, 知識 (KNO) +1.
  - `gathering` (Food): 觀察 (PER) +1, 知識 (KNO) +1.
  - `gathering` (Wood/Stone): 力量 (STR) +1, 耐力 (END) +1.
  - `exploring`: 敏捷 (AGI) +1, 觀察 (PER) +1.
  - `building`: 知識 (KNO) +1, 耐力 (END) +1.

### 2. 素質加成公式 (Modifiers)
- 通用效率係數 (Efficiency): `(StatA + StatB) / 2 / 100`.
- 力量 (STR): 影響 `Wood/Stone` 採集效率.
- 敏捷 (AGI): 影響 `Exploring` 判定效率.
- 觀察 (PER): 影響 `Food` 採集、`Exploring` 與 `Idle` 效率.
- 知識 (KNO): 影響 `Building` 建設與 `Idle` 效率.
- 耐力 (END): 影響 `Wood/Stone` 採集與 `Building` 建設效率.

### 3. 屬性緩存與更新 (Table: player_stats)
為了優化計算成本, 系統會維護此緩存表, 僅在玩家行動結算或提交時更新.

| 欄位名 | 型別 | 說明 | 初始值 |
| :--- | :--- | :--- | :--- |
| player_id | INTEGER (PK/FK) | 關聯至 players.id | |
| strength | INTEGER | 力量 | 50 |
| agility | INTEGER | 敏捷 | 50 |
| perception | INTEGER | 觀察 | 50 |
| knowledge | INTEGER | 知識 | 50 |
| endurance | INTEGER | 耐力 | 50 |
| last_calc_time | TIMESTAMP | 上次計算窗口的時間點 | |

### 4. 相關 Schema (Table: player_actions_log)
| 欄位名 | 型別 | 說明 |
| :--- | :--- | :--- |
| id | INTEGER (PK) | |
| player_id | INTEGER (FK) | |
| action_type | TEXT | idle, gathering, exploring, building |
| start_time | TIMESTAMP | |
| end_time | TIMESTAMP | |

### 5. 平衡性參數 (Balance Numbers)
- 素質計算視窗: 150 小時.
- 基礎值: 50.
- 每個行動小時點數: 2 點 (依權重分配).

## Changelog
- 2026.04.07.00: Aligned stats with 1-hour cycle. Removed weight and satiety modifiers. Preserved 150h window logic. See [2026.04.07.00.md](../../changelogs/2026.04.07.00.md)

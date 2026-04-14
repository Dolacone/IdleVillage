# Module: Player Stats and Status

定義素質計算規則、加成係數以及 150 週期滑動窗口機制.

### 1. 150 週期滑動窗口 (150 Cycles Sliding Window)
- 計算: 基礎素質值 (STATS_BASE_VALUE) + `player_actions_log` 中最近 150 次完整行動週期所記錄的素質點數總和.
- 基礎素質值 (STATS_BASE_VALUE): 50.
- 紀錄方式: `player_actions_log` 僅在一次完整行動週期 (Cycle) 結束時寫入一筆素質紀錄. 未完成的 partial slice 不寫入此表.
- 保留規則: 每位玩家在 `player_actions_log` 中最多保留最新 150 筆紀錄. 超過 150 筆時, 系統刪除最舊的紀錄.
- 行動分配權重 (每行動 1 週期獲得之點數):
  - idle: 觀察 (PER) +1, 知識 (KNO) +1.
  - gathering_food: 觀察 (PER) +1, 知識 (KNO) +1.
  - gathering_wood: 力量 (STR) +1, 耐力 (END) +1.
  - gathering_stone: 力量 (STR) +1, 耐力 (END) +1.
  - exploring: 敏捷 (AGI) +1, 觀察 (PER) +1.
  - building: 知識 (KNO) +1, 耐力 (END) +1.
  - attack (v2026.04.10.00): 力量 (STR) +1, 敏捷 (AGI) +1.

### 2. 素質加成公式 (Modifiers)
- 通用效率係數 (Efficiency Invariant): (StatA + StatB) / 2 / 100.
- 力量 (STR): 影響 Wood/Stone 採集效率與對怪物傷害 (Attack).
- 敏捷 (AGI): 影響 Exploring 判定效率與對怪物傷害 (Attack).
- 觀察 (PER): 影響 Food 採集、Exploring 與 Idle 效率.
- 知識 (KNO): 影響 Building 建設與 Idle 效率.
- 耐力 (END): 影響 Wood/Stone 採集與 Building 建設效率.

### 3. 屬性緩存與更新 (Table: player_stats)
為了優化計算成本, 系統會維護此緩存表, 僅在玩家行動結算或提交時更新.

| 欄位名 | 型別 | 說明 | 初始值 |
| :--- | :--- | :--- | :--- |
| player_discord_id | INTEGER (PK/FK) | 關聯至 players.discord_id | |
| village_id | INTEGER (PK/FK) | 關聯至 villages.id | |
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
| player_discord_id | INTEGER (FK) | |
| village_id | INTEGER (FK) | |
| strength_delta | INTEGER | 該完整週期對 STR 的貢獻 |
| agility_delta | INTEGER | 該完整週期對 AGI 的貢獻 |
| perception_delta | INTEGER | 該完整週期對 PER 的貢獻 |
| knowledge_delta | INTEGER | 該完整週期對 KNO 的貢獻 |
| endurance_delta | INTEGER | 該完整週期對 END 的貢獻 |
| cycle_end_time | TIMESTAMP | 用於排序並保留最新 150 筆 |

### 5. 平衡性參數 (Balance Numbers)
- 素質計算視窗: 最近 150 次完整行動週期.
- 基礎值 (STATS_BASE_VALUE): 50.
- 每個行動週期點數: 2 點 (依權重分配).

## Changelog
- 2026.04.07.00: Aligned stats with 1-hour cycle. - See [2026.04.07.00.md](../changelogs/2026.04.07.00.md)
- 2026.04.08.00: Transitioned from 150h window to 150 cycles window. - See [2026.04.08.00.md](../changelogs/2026.04.08.00.md)
- 2026.04.09.01: Introduced STATS_BASE_VALUE constant and standardized action log types. - See [2026.04.09.01.md](../changelogs/2026.04.09.01.md)
- 2026.04.10.00: Added attack action type and weights (STR + AGI). - See [2026.04.10.00.md](../changelogs/2026.04.10.00.md)
- 2026.04.14.00: Planned `player_actions_log` redesign to store per-cycle stat deltas, keep only 150 rows per player, and exclude partial slices from stat growth. - See [2026.04.14.00.md](../changelogs/2026.04.14.00.md)

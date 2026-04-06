# Module: Player Stats and Status

定義素質計算規則, 加成係數以及數據紀錄結構.

### 1. 150h 滑動窗口素質 (150h Sliding Window)
- 計算: 基礎 50 點 + 過去 150 小時行動紀錄 (1 小時 = 2 點).
- 紀錄方式: `player_actions_log` 僅在玩家狀態切換時寫入一筆完整區段紀錄, 記錄該行動的 `action_type`, `start_time`, `end_time`. 尚未結束的當前狀態不會提前寫入.
- 行動分配權重 (每小時, 由 action_type 對應):
  - `idle`: 觀察 +1, 知識 +1.
  - `moving` / `returning`: 耐力 +1, 敏捷 +1.
  - `explore`: 觀察 +1, 敏捷 +1.
  - `gather_material`: 力量 +1, 耐力 +1.
  - `gather_food`: 觀察 +1, 知識 +1.
  - `build`: 知識 +1, 力量 +1.

### 2. 素質加成公式 (Modifers)
- 效率係數: (StatA + StatB) / 2 / 100.
- 力量: +1 負重/點, +1% 採集量/點.
- 敏捷: -0.5% 移動時間/點, -0.5% 飽食度消耗/點.
- 知識: +2% 建設 XP/點.
- 耐力: +1 負重/點, -0.2% 飽食度消耗/點.

### 3. 狀態平衡 (Scaled Integer)
- 飽食度 (Satiety Deadline): 存儲為 TIMESTAMP。
  - 定義: 玩家飽食度歸零的預計時間點。
  - 容量: 最大 100 小時 (即 Now + 360,000 秒)。
  - 消耗: 僅當玩家不處於 `idle` 狀態時才會消耗. 此時該時間點保持不變, 並隨時間接近而減少剩餘值。
  - 閒置 (Idle): 玩家處於 `idle` 狀態時, 系統會隨時間同步推移該時間點, 使剩餘時間不變。
  - 補給: 玩家在村莊中進入 `idle` 狀態時, 或由 `idle` 狀態準備出發前, 會使用村莊糧食嘗試自動補滿至 100 小時。
- 負重 (Weight): 力量 + 耐力. (資源數量採 1x 整數儲存).

### 4. 緩存表定義 (Table: player_stats)
為了優化 150h 滑動窗口的計算成本, 系統會維護此緩存表, 僅在玩家行動改變或結算時更新.

| 欄位名 | 型別 | 說明 | 初始值 |
| :--- | :--- | :--- | :--- |
| player_id | INTEGER (PK/FK) | 關聯至 players.id | |
| strength | INTEGER | 力量 | 50 |
| agility | INTEGER | 敏捷 | 50 |
| perception | INTEGER | 觀察 | 50 |
| knowledge | INTEGER | 知識 | 50 |
| endurance | INTEGER | 耐力 | 50 |
| last_calc_time | TIMESTAMP | 上次計算窗口的時間點 | |

### 5. 相關 Schema (Table: player_actions_log)
| 欄位名 | 型別 | 說明 |
| :--- | :--- | :--- |
| id | INTEGER (PK) | |
| player_id | INTEGER (FK) | |
| action_type | TEXT | idle, moving, returning, explore, gather_food, gather_material, build |
| start_time | TIMESTAMP | |
| end_time | TIMESTAMP | |

### 6. 平衡性參數 (Balance Numbers)
- 素質計算視窗: 150 小時.
- 結算精度: 秒.

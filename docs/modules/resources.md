# Module: Resources and Exploration

定義資源獲取, 探索抽獎, 移動對稱性以及閒置採集機制.

### 1. 閒置採集 (Idle Gathering)
- 觸發: 玩家位置為 `at_village` 且狀態為 `idle`.
- 內容: 自動採集糧食.
- 公式: 每小時產出 = 10 (基礎速率) * 效率係數 * 0.5 (固定品質).
- 紀錄: 不採逐小時寫入. 系統在 `idle` 狀態結束並切換到下一個狀態時, 寫入一筆 `player_actions_log` 紀錄, 由該筆紀錄的 `action_type=idle` 與持續時間推導 觀察 與 知識 素質.

### 2. 探索抽獎機制 (Lottery)
- 效率係數: (敏捷 + 觀察) / 2 / 100.
- 虛擬預算 (分鐘): 實際執行分鐘數 * 效率係數.
- 判定規則: 預算 >= 30m 即可進行一次判定.
- 權重與成本:
  - Miss: 40% | 成本 30m.
  - Lv1 Node: 35% | 成本 30m | 儲量 1000 | 品質 75-125.
  - Lv2 Node: 15% | 成本 60m | 儲量 2000 | 品質 100-150.
  - Lv3 Node: 7% | 成本 120m | 儲量 4000 | 品質 125-175.
  - Lv4 Node: 3% | 成本 240m | 儲量 8000 | 品質 150-200.
- 距離生成: 隨機 (1800, 當前剩餘預算 * 60 * 0.3) 秒.

### 3. 移動對稱性 (Travel Symmetry)
- 計算: 抵達時間 = 觸發回程時間 + (觸發回程時間 - 出發時間).
- 消耗: 前往目標每小時消耗 1 點飽食度, 回程則免.
- 失敗處理: 
  - 若移動途中目標消失, 立即執行對稱回程.
  - 若 satiety 到達 0, 玩家強制執行 [回村結算流程], 且回程不需負面處罰 (Debuffs). 回村後若村莊糧食充足則自動補給.

### 4. 平衡性參數 (Balance Numbers)
- 基礎採集速率: 10 / 小時.
- 移動速度: 每單位距離 60 秒.
- 節點品質公式: 基礎 75 + (Level-1)*25 至 125 + (Level-1)*25 (DB 儲存 100x 整數).
- 節點有效期: 發現後 48 小時.

### 5. 擴充 Schema (Table: resource_nodes)
| 欄位名 | 型別 | 說明 |
| :--- | :--- | :--- |
| id | INTEGER (PK) | |
| village_id | INTEGER (FK) | |
| type | TEXT | food, wood, stone |
| level | INTEGER | 1, 2, 3, 4 |
| quality | INTEGER | 75 - 200 |
| distance | INTEGER | 距離 (秒) |
| remaining_amount | INTEGER | |
| max_capacity | INTEGER | |
| expiry_time | TIMESTAMP | |

### 6. 已知議題 (Known Issues)
- 視覺化限制: 由於 Discord 下拉選單限制為 25 項, 當村莊探索出的有效節點過多時, 介面需實作分頁或優先排序邏輯 (預計於 Alpha 測試處理).

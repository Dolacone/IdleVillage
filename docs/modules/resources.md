# Module: Resources and Exploration

定義資源獲獲取、探索機制以及 1 小時循環採集機制.

### 1. 閒置狀態 (Idle State)
- 觸發: 玩家狀態為 `idle`.
- 內容: 視為非採集行動, 居民於村莊內協助基礎生產.
- 消耗: 無 (不消耗村莊糧食).
- 效果: 直接產出糧食至村莊倉庫.
- 屬性掛鉤: 觀察 (PER) + 知識 (KNO).
- 公式: 每小時產出 = 10 (基礎速率) * 效率係數 * 0.5 (固定品質).
- 紀錄: 當 1 小時結束時, 結算產出並更新 `last_update_time`.

### 2. 資源採集 (Gathering)
- 觸發: 玩家選擇一個有效資源節點並提交 `gather` 指令.
- 1 小時循環週期 (1-Hour Tick):
  - 啟動預扣: 循環開始時, 立即從村莊倉庫扣除 1 單位糧食 (資源概不退還).
  - 產出結算: 1 小時後計算產出並直接存入村莊倉庫.
  - 自動續期: 若週期結束時村莊仍有糧食且節點尚有儲量, 自動開啟下一個 1 小時循環.
- 屬性掛鉤 (Efficiency Stats):
  - 採集糧食 (Food): 觀察 (PER) + 知識 (KNO).
  - 採集木材 (Wood): 力量 (STR) + 耐力 (END).
  - 採集石材 (Stone): 力量 (STR) + 耐力 (END).
- 效率公式: (屬性 A + 屬性 B) / 2 / 100.
- 採集產出: 基礎速率 * 效率係數. (不計負重, 直接入庫).

### 3. 探索機制 (Exploring)
- 屬性掛鉤: 敏捷 (AGI) + 觀察 (PER).
- 效率係數: (敏捷 + 觀察) / 2 / 100.
- 1 小時循環預扣: 每小時消耗 1 單位糧食.
- 虛擬預算 (分鐘): 每小時獲得 `60 * 效率係數` 分鐘的預算.
- 判定規則: 預算累積每滿 30m 即可進行一次隨機判定.
- 權重與成本:
  - Miss: 40% | 成本 30m.
  - Lv1 Node: 35% | 成本 30m | 儲量 1000 | 品質 75-125.
  - Lv2 Node: 15% | 成本 60m | 儲量 2000 | 品質 100-150.
  - Lv3 Node: 7% | 成本 120m | 儲量 4000 | 品質 125-175.
  - Lv4 Node: 3% | 成本 240m | 儲量 8000 | 品質 150-200.

### 4. 平衡性參數 (Balance Numbers)
- 糧食消耗: 每行動小時 1 單位.
- 節點有效期: 發現後 48 小時.
- 基礎採集速率: 10 / 小時.
- 節點品質公式: 基礎 75 + (Level-1)*25 至 125 + (Level-1)*25 (DB 儲存 100x 整數).

### 5. 擴充 Schema (Table: resource_nodes)
| 欄位名 | 型別 | 說明 |
| :--- | :--- | :--- |
| id | INTEGER (PK) | |
| village_id | INTEGER (FK) | |
| type | TEXT | food, wood, stone |
| level | INTEGER | 1, 2, 3, 4 |
| quality | INTEGER | 75 - 200 |
| remaining_amount | INTEGER | |
| expiry_time | TIMESTAMP | |

## Changelog
- 2026.04.07.00: Implemented 1-hour cycle gathering and exploring. Removed distance and weight. See [2026.04.07.00.md](../../changelogs/2026.04.07.00.md)

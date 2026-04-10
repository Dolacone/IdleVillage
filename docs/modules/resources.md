# Module: Resources

定義資源獲取效率、正規化村莊倉庫管理與探索機制.

### 1. 資源節點 (Resource Nodes)
- 單一節點模型 (Singleton Model):
  - 每個村莊每種資源類型 (糧食, 木材, 石材) 同時僅存在一個永久節點. (v2026.04.09.00)
  - 庫存上限 (Stock Cap): 每個節點庫存上限為 8,000 單位. (v2026.04.09.00)
  - 永久性: 資源節點不再具有過期時間, 會持續存在直到被採集至 0 (缺貨).
- 資源品質 (Node Quality):
  - 基礎品質為 100.
  - 若探索發現新資源且該類型已存在, 則採用加權平均計算新品質.
  - 品質公式: `New_Quality = floor((Old_Quality * Old_Stock + Found_Quality * Found_Stock) / (Old_Stock + Found_Stock))`. (v2026.04.09.00)
- 探索機制 (Exploring) (v2026.04.09.01):
  - 探索效率: 敏捷 (AGI) + 觀察 (PER).
  - 探索機率 (Exploring Probability): `效率係數 * 20%`. (例如效率 0.5 則機率為 10%).
  - 探索產出 (Exploring Output): `基礎產出 (50) * random(20, 40) * 效率係數`.
  - 探索結果: 若該資源類型的 singleton 節點已存在, 則補充庫存並重算品質; 若不存在, 則建立該類型節點.
  - 發現公告: 不另外發送 discovery 訊息, 僅更新資料與後續 dashboard 顯示.
- 採集效率 (Gathering Efficiency):
  - 糧食採集: 感知 (PER) + 知識 (KNO).
  - 木材/石材採集: 力量 (STR) + 耐力 (END).
  - 效率公式 (Invariant): `(StatA + StatB) / 2 / 100`.
  - 產出公式 (v2026.04.09.01): `基礎產出 (50) * 效率係數 * (品質修正) * (實際持續分鐘 / ACTION_CYCLE_MINUTES)`.
  - 品質修正: `max(75, Node_Quality) / 100`.
  - 加工增益: 採集產出在入庫前再乘上 `1.0 + (Resource_Yield_Level * 0.1)`.

### 2. 正規化資源管理 (Normalized Resources) (v2026.04.09.01)
村莊資源存儲於 `village_resources` 表, 支援動態資源類型擴充:
- **糧食 (food)**: 初始化 1,000 單位, 行動基礎消耗 20.
- **木材 (wood)**: 初始化 1,000 單位, 建設基礎消耗 50.
- **石材 (stone)**: 初始化 1,000 單位, 建設基礎消耗 50.

### 3. 資源採集流程 (Gathering Process)
- 庫存檢查: 行動週期開始前, 若目標節點庫存為 0, 玩家無法啟動採集.
- 行動期間耗損: 每週期結束結算時, 從節點扣除實際獲得量.
- 缺貨處理 (Out of Stock):
  - 若結算時節點庫存歸零, 玩家會獲得剩餘庫存的所有資源, 並自動切換為 idle 狀態.
  - 系統會在公告頻道發送節點缺貨通知.

### 4. 資源倉儲限制 (Storage Limits)
- 倉儲上限: `1,000 * (2 ^ 倉庫增益等級)`. (v2026.04.09.01)
- 溢出處理: 超過上限的產出將直接被捨棄 (Discarded).

## Changelog
- 2026.04.07.00: Defined gathering efficiency and base output values. - See [2026.04.07.00.md](../changelogs/2026.04.07.00.md)
- 2026.04.08.00: Aligned gathering with 1-hour cycle and storage limits. - See [2026.04.08.00.md](../changelogs/2026.04.08.00.md)
- 2026.04.09.00: Implemented singleton resource nodes, 8,000 stock cap, and weighted quality. Removed node expiry. - See [2026.04.09.00.md](../changelogs/2026.04.09.00.md)
- 2026.04.09.01: Transitioned resource storage to village_resources table, rebalanced exploring probability (20% base) and discovery output (BASE * 20-40 * EFF). - See [2026.04.09.01.md](../changelogs/2026.04.09.01.md)

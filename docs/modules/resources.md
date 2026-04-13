# Module: Resources

定義資源節點、採集產出與村莊倉庫管理。本文件不重述探索與怪物規則，相關內容統一以 `docs/modules/exploration.md` 為準。

### 1. 資源節點 (Resource Nodes)
- 單一節點模型 (Singleton Model):
  - 每個村莊每種資源類型 (糧食, 木材, 石材) 同時僅存在一個永久節點.
  - 庫存上限 (Stock Cap): 每個節點庫存上限為當前村莊倉庫容量的 2 倍 (`Storage Capacity * 2`)。
  - 永久性: 資源節點持續存在直到被採集至 0 (缺貨).
- 資源品質 (Node Quality):
  - 基礎品質為 100, 上限限制為 175%. (v2026.04.10.00)
  - 若探索發現新資源且該類型已存在, 則採用加權平均計算新品質 (詳細探索流程見 `docs/modules/exploration.md`)。
  - 品質公式: `min(175, floor((Old_Quality * Old_Stock + Found_Quality * Found_Stock) / (Old_Stock + Found_Stock)))`.

### 2. 採集 (Gathering)
- 交互邏輯: 玩家透過 `/idlevillage` 的 Interact 選單選取資源節點開始採集。
- 採集前提: 目標節點必須存在，且 `remaining_amount > 0`。
- 屬性掛鉤:
  - 糧食採集: 感知 (PER) + 知識 (KNO).
  - 木材/石材採集: 力量 (STR) + 耐力 (END).
- 產出公式: 基礎產出 (50) * 效率係數 * (max(75, 品質) / 100) * 加工加成 * 時間比例.

### 3. 正規化資源管理 (Normalized Resources)
村莊資源存儲於 village_resources 表:
- 糧食 (food): 初始化 1,000 單位.
- 木材 (wood): 初始化 1,000 單位.
- 石材 (stone): 初始化 1,000 單位.
- 黃金 (gold): 初始化 0 單位, 僅能透過狩獵獲得. (v2026.04.10.00)

### 4. 資源倉儲限制 (Storage Limits)
- 倉儲上限: 1,000 * (2 ^ 倉庫增益等級).
- 溢出處理 (v2026.04.10.00): 
  - 核心邏輯: 若當前庫存因等級下降已超過上限, 系統將保留原始資源, 但不允許存入新收益.
  - 計算公式: `新庫存 = min(max(倉儲上限, 當前庫存), 當前庫存 + 本次收益)`.

## Changelog
- 2026.04.07.00: Defined gathering efficiency and base output values. - See [2026.04.07.00.md](../changelogs/2026.04.07.00.md)
- 2026.04.08.00: Aligned gathering with 1-hour cycle and storage limits. - See [2026.04.08.00.md](../changelogs/2026.04.08.00.md)
- 2026.04.09.00: Implemented singleton resource nodes and weighted quality. Removed node expiry. - See [2026.04.09.00.md](../changelogs/2026.04.09.00.md)
- 2026.04.09.01: Transitioned resource storage to village_resources table, rebalanced exploring probability (20% base) and discovery output (BASE * 20-40 * EFF). - See [2026.04.09.01.md](../changelogs/2026.04.09.01.md)
- 2026.04.10.00: Added Monster system, Gold resource, 175% Quality cap, and unified interaction logic via existing UI. - See [2026.04.10.00.md](../changelogs/2026.04.10.00.md)

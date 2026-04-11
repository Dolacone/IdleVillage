# Module: Resources

定義資源獲取效率、正規化村莊倉庫管理與探索機制.

### 1. 資源節點 (Resource Nodes)
- 單一節點模型 (Singleton Model):
  - 每個村莊每種資源類型 (糧食, 木材, 石材) 同時僅存在一個永久節點.
  - 庫存上限 (Stock Cap): 每個節點庫存上限為 8,000 單位.
  - 永久性: 資源節點持續存在直到被採集至 0 (缺貨).
- 資源品質 (Node Quality):
  - 基礎品質為 100, 上限限制為 175%. (v2026.04.10.00)
  - 若探索發現新資源且該類型已存在, 則採用加權平均計算新品質.
  - 品質公式: New_Quality = min(175, floor((Old_Quality * Old_Stock + Found_Quality * Found_Stock) / (Old_Stock + Found_Stock))).

### 2. 怪物系統 (Monsters) (v2026.04.10.00)
探索時有機會觸發怪物威脅, 需全村合作擊退.
- 種類與獎勵:
  - 野豬 (Boar): 掉落 糧食 + 黃金.
  - 樹妖 (Tree Folk): 掉落 木材 + 黃金.
  - 石怪 (Golem): 掉落 石材 + 黃金.
- 數值屬性:
  - HP (血量): BASE_OUTCOME (50) * random(15, 25) * 效率係數. (均值約 1,000)
  - 品質 (防禦): 繼承探索發現時的品質, 上限 175%.
  - 逃跑機制: 若 48 小時內未擊敗, 怪物將自動逃跑.
- 威脅效果: 怪物存在期間, 村莊所有建築的 XP 損耗 (Decay) 翻倍 (x2).
- 擊敗獎勵:
  - 資源 (視種類) = HP上限 * (品質 / 100).
  - 黃金 = HP上限 * (品質 / 100).
  - 狩獵 XP = 固定 1,000.

### 3. 探索機制 (Exploring) (v2026.04.10.00)
- 探索效率: 敏捷 (AGI) + 觀察 (PER).
- 觸發機率 (Exploring Probability):
  - 發現資源: 效率係數 * 90%. (三種基礎資源均分)
  - 發現怪物: 效率係數 * 10%. (若村莊已有怪物, 則此機率轉回資源發現)
- 探索產出 (資源): 基礎產出 (50) * random(20, 40) * 效率係數.

### 4. 交互與戰鬥 (Interact & Combat)
- 交互邏輯: 透過 /idlevillage 的選單進行. 系統自動判斷目標類型, 執行「採集」或「攻擊」.
- 戰鬥 (Attack):
  - 屬性掛鉤: 力量 (STR) + 敏捷 (AGI).
  - 傷害公式: 50 * 效率 * (1.0 + 狩獵等級 * 0.05) * ((200 - 品質) / 100) * 時間比例.
- 採集 (Gathering):
  - 糧食採集: 感知 (PER) + 知識 (KNO).
  - 木材/石材採集: 力量 (STR) + 耐力 (END).
  - 產出公式: 基礎產出 (50) * 效率係數 * (max(75, 品質) / 100) * 加工加成 * 時間比例.

### 5. 正規化資源管理 (Normalized Resources)
村莊資源存儲於 village_resources 表:
- 糧食 (food): 初始化 1,000 單位.
- 木材 (wood): 初始化 1,000 單位.
- 石材 (stone): 初始化 1,000 單位.
- 黃金 (gold): 初始化 0 單位, 僅能透過狩獵獲得. (v2026.04.10.00)

### 6. 資源倉儲限制 (Storage Limits)
- 倉儲上限: 1,000 * (2 ^ 倉庫增益等級).
- 溢出處理 (v2026.04.10.00): 
  - 核心邏輯: 若當前庫存因等級下降已超過上限, 系統將保留原始資源, 但不允許存入新收益.
  - 計算公式: `新庫存 = min(max(倉儲上限, 當前庫存), 當前庫存 + 本次收益)`.

## Changelog
- 2026.04.07.00: Defined gathering efficiency and base output values. - See [2026.04.07.00.md](../changelogs/2026.04.07.00.md)
- 2026.04.08.00: Aligned gathering with 1-hour cycle and storage limits. - See [2026.04.08.00.md](../changelogs/2026.04.08.00.md)
- 2026.04.09.00: Implemented singleton resource nodes, 8,000 stock cap, and weighted quality. Removed node expiry. - See [2026.04.09.00.md](../changelogs/2026.04.09.00.md)
- 2026.04.09.01: Transitioned resource storage to village_resources table, rebalanced exploring probability (20% base) and discovery output (BASE * 20-40 * EFF). - See [2026.04.09.01.md](../changelogs/2026.04.09.01.md)
- 2026.04.10.00: Added Monster system, Gold resource, 175% Quality cap, and unified interaction logic via existing UI. - See [2026.04.10.00.md](../changelogs/2026.04.10.00.md)

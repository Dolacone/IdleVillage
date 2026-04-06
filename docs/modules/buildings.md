# Module: Buildings

定義村莊輔助建築的級距, 效果公式與損耗平衡.

### 1. 建築功能效果 (Effect Formulas)
- 糧食效率 (Food Efficiency):
  - 效果: 決定每單位糧食可恢復的飽食度.
  - 公式: 1 糧食 = 1.0 + (Level * 0.2) 點飽食度.
  - 範例: Lv5 時, 1 糧食恢復 2.0 點飽食度.
- 儲存容量 (Storage Capacity):
  - 效果: 提升村莊三種資源的存放上限.
  - 公式: 總容量 = 1000 * (2 ^ Level).
  - 範例: Lv0 = 1000, Lv1 = 2000, Lv5 = 32000.
- 資源產量 (Resource Yield):
  - 效果: 全體居民採集速率的乘算加成.
  - 公式: 加成係數 = 1.0 + (Level * 0.1).
  - 範例: Lv5 時, 採集量為 1.5x.

### 2. XP 與等級門檻 (XP Thresholds)
採用指數成長門檻, 每級所需 XP 加倍. XP 超過門檻的部分視為耐久緩衝.
- Lv1: 1000 (總計 1000)
- Lv2: 2000 (總計 3000)
- Lv3: 4000 (總計 7000)
- Lv4: 8000 (總計 15000)
- 公式: NextThreshold = CurrentThreshold + (1000 * 2^(Level-1)).

### 3. 平衡性參數 (Balance Numbers)
- 基礎損耗 (Base Decay): 每小時 10 XP.
- 人口係數 (Activity Scale): 每 1 名活躍玩家增加 1 XP / 小時.
- 建設效率 (Construction): 每小時基礎增加 50 XP (受知識素質加成).
- 建設消耗: 每小時消耗 10 單位木材與 5 單位石材.
- 降級機制: 當 XP 跌破門檻時立即降級.

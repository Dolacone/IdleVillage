# Module: Buildings

定義村莊建築的級距、正規化增益 (Buffs) 存儲與行動週期 (Action Cycle) 建設機制.

### 1. 建設機制 (Building Process)
- 循環規則:
  - 啟動預扣: 每個行動週期 (Cycle) 開始時, 從村莊倉庫扣除所需資源.
- 預扣成本 (v2026.04.10.00):
  - 所有建築每週期固定消耗 **50 + 50** 單位資源.
  - 資源不足判定: 若資源低於預扣標準, 玩家將自動切換為 `idle` 狀態.
  - 產出結算: 週期結束後, 增加 `buffs` 表中對應項目的 XP.
  - 升級通知: 若 XP 達到下一等級門檻 (Level Up), 系統將在村莊公告頻道發送慶祝訊息.
  - 不可退還: 資源一旦扣除, 即使玩家中斷行動也不予退還.
- 屬性掛鉤 (Efficiency Stats):
  - 建設效率: 知識 (KNO) + 耐力 (END).
- 效率公式 (Invariant): `(知識 + 耐力) / 2 / 100`.
- 產出公式: `基礎產出 (50 XP) * 效率係數 * (實際持續分鐘 / ACTION_CYCLE_MINUTES)`.

### 2. XP 與等級門檻
- 採用指數成長門檻, 每級所需 XP 加倍.
- 公式: 下一級門檻 = 當前門檻 + (1000 * 2^(Level-1)).

### 3. 正規化增益定義 (Normalized Buffs) (v2026.04.10.00)
建築功能數據儲存於 `buffs` 表, 消耗組合如下:

| ID | 名稱 | 效果描述 | 每週期成本 (50+50) |
| :--- | :--- | :--- | :--- |
| 1 | 廚房 (Food Efficiency) | 降低全體村民行動時的糧食消耗. | 糧食 + 木材 |
| 2 | 倉庫 (Storage Capacity) | 提升村莊各項資源的儲存上限. | 木材 + 石材 |
| 3 | 加工 (Resource Yield) | 提升採集行動獲得的資源產量. | 木材 + 石材 |
| 4 | 狩獵 (Hunting) | 提升對怪物的傷害效率 (每級 +5%). | 石材 + 黃金 |

- **ID 1: 廚房**
  - 公式: 消耗 = `max(10, 20 - Level)`.
- **ID 2: 倉庫**
  - 公式: 總容量 = `1000 * (2 ^ Level)`.
- **ID 3: 加工**
  - 公式: 全體產量乘算加成 = `1.0 + (Level * 0.1)`.
- **ID 4: 狩獵**
  - 公式: 對怪物傷害加成 = `1.0 + (Level * 0.05)`.

### 4. 建築損耗 (XP Decay)
- 損耗規則: 每個行動週期 (Cycle) 結束後, 對所有建築增益執行 XP 損耗.
- 公式: `Decay_per_Cycle = int(Active_Players * 0.5) + int(Current_XP * (0.001 + Current_XP / 5,000,000))`.
- **倍增威脅 (v2026.04.10.00)**: 若村莊內存在活躍怪物, 損耗值翻倍 (`x2`).
- 降級公告: 若損耗導致增益等級下降, 系統會在村莊公告頻道發送提醒訊息.

## Changelog
- 2026.04.07.00: Defined construction efficiency and 1-hour cycle building process. - See [2026.04.07.00.md](../changelogs/2026.04.07.00.md)
- 2026.04.08.00: Refactored to Cycle-based logic and aligned base output to 20 XP. - See [2026.04.08.00.md](../changelogs/2026.04.08.00.md)
- 2026.04.08.02: Increased base output from 20 XP to 50 XP. - See [2026.04.08.02.md](../changelogs/2026.04.08.02.md)
- 2026.04.08.03: Rebalanced building XP decay using a dynamic exponential model and added upgrade announcements. - See [2026.04.08.03.md](../changelogs/2026.04.08.03.md)
- 2026.04.09.01: Transitioned building storage to buffs table, standardized base XP (50), increased build costs (50/50), and enhanced Kitchen effect (2*Level). Added level-down notifications. - See [2026.04.09.01.md](../changelogs/2026.04.09.01.md)
- 2026.04.10.00: Added Hunting buff, refactored building costs (50+50 dual-resource), and implemented double decay during monster presence. - See [2026.04.10.00.md](../changelogs/2026.04.10.00.md)

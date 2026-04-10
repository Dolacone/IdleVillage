# Module: Buildings

定義村莊建築的級距、正規化增益 (Buffs) 存儲與行動週期 (Action Cycle) 建設機制.

### 1. 建設機制 (Building Process)
- 循環規則:
  - 啟動預扣: 每個行動週期 (Cycle) 開始時, 從村莊倉庫扣除所需資源.
- 預扣成本 (v2026.04.09.01): 糧食 (`max(10, 20 - Level)`)、`50 木材`、`50 石材`.
  - 資源不足判定: 若資源低於預扣標準, 玩家將自動切換為 `idle` 狀態.
  - 產出結算: 週期結束後, 增加 `buffs` 表中對應項目的 XP. (v2026.04.09.01)
  - 升級通知: 若 XP 達到下一等級門檻 (Level Up), 系統將在村莊公告頻道發送慶祝訊息.
  - 不可退還: 資源一旦扣除, 即使玩家中斷行動也不予退還.
- 屬性掛鉤 (Efficiency Stats):
  - 建設效率: 知識 (KNO) + 耐力 (END).
- 效率公式 (Invariant): `(知識 + 耐力) / 2 / 100`.
- 產出公式 (v2026.04.09.01): `基礎產出 (50 XP) * 效率係數 * (實際持續分鐘 / ACTION_CYCLE_MINUTES)`.

### 2. XP 與等級門檻
- 採用指數成長門檻, 每級所需 XP 加倍.
- 公式: 下一級門檻 = 當前門檻 + (1000 * 2^(Level-1)).

### 3. 正規化增益定義 (Normalized Buffs) (v2026.04.09.01)
建築功能現在被定義為村莊增益 (Buffs), 數據儲存於 `buffs` 表, 使用 ID 進行識別:
- **ID 1: 廚房 (Food Efficiency)**
  - 效果: 降低全體村民行動時的糧食消耗.
  - 公式: 消耗 = `max(10, 20 - Level)`.
- **ID 2: 倉庫 (Storage Capacity)**
  - 效果: 提升村莊各項資源的儲存上限.
  - 公式: 總容量 = `1000 * (2 ^ Level)`.
- **ID 3: 加工 (Resource Yield)**
  - 效果: 提升採集行動獲得的資源產量.
  - 公式: 全體產量乘算加成 = `1.0 + (Level * 0.1)`.

### 4. 建築損耗 (XP Decay)
- 損耗規則: 每個行動週期 (Cycle) 結束後, 對所有建築增益執行 XP 損耗.
- 公式: `Decay_per_Cycle = int(Active_Players * 0.5) + int(Current_XP * (0.001 + Current_XP / 5,000,000))`.
  - **活躍人數基礎**: `Active_Players * 0.5` 確保即使低等級項目也有基礎維護壓力.
  - **動態 XP 比例**: 基礎 0.1% 隨 XP 增加而上升 (加上 `XP / 5M`), 形成指數級的維護牆.
- 降級公告 (v2026.04.09.01): 若損耗導致增益等級下降, 系統會在村莊公告頻道發送提醒訊息.
- 平衡目標:
  - **Lv2 (3,000 XP)**: 極度輕鬆, 任何規模村莊皆可維持.
  - **Lv5 (31,000 XP)**: 需要持續且明顯的建設投入.
  - **Lv9 (511,000 XP)**: 幾乎無法到達, 損耗將超過任何正常規模村莊的產能極限.

## Changelog
- 2026.04.07.00: Defined construction efficiency and 1-hour cycle building process. - See [2026.04.07.00.md](../changelogs/2026.04.07.00.md)
- 2026.04.08.00: Refactored to Cycle-based logic and aligned base output to 20 XP. - See [2026.04.08.00.md](../changelogs/2026.04.08.00.md)
- 2026.04.08.02: Increased base output from 20 XP to 50 XP. - See [2026.04.08.02.md](../changelogs/2026.04.08.02.md)
- 2026.04.08.03: Rebalanced building XP decay using a dynamic exponential model and added upgrade announcements. - See [2026.04.08.03.md](../changelogs/2026.04.08.03.md)
- 2026.04.09.01: Transitioned building storage to buffs table, standardized base XP (50), increased build costs (50/50), and enhanced Kitchen effect (2*Level). Added level-down notifications. - See [2026.04.09.01.md](../changelogs/2026.04.09.01.md)

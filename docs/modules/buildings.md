# Module: Buildings

定義村莊建築的級距、效果公式與行動週期 (Action Cycle) 建設機制.

### 1. 建設機制 (Building Process)
- 循環規則:
  - 啟動預扣: 每個行動週期 (Cycle) 開始時, 從村莊倉庫扣除所需資源.
  - 預扣成本: 糧食 (`max(1, 10 - Food_Eff_Level)`)、`10 木材`、`5 石材`.
  - 資源不足判定: 若資源低於預扣標準, 玩家將自動切換為 `idle` 狀態.
  - 產出結算: 週期結束後, 增加對應建築的 XP.
  - 升級通知: 若建築 XP 達到下一等級門檻 (Level Up), 系統將在村莊公告頻道發送慶祝訊息.
  - 不可退還: 資源一旦扣除, 即使玩家中斷行動也不予退還.
- 屬性掛鉤 (Efficiency Stats):
  - 建設效率: 知識 (KNO) + 耐力 (END).
- 效率公式: (知識 + 耐力) / 2 / 100.
- 產出公式: 基礎產出 (50 XP) * 效率係數 * (實際持續分鐘 / ACTION_CYCLE_MINUTES).

### 2. XP 與等級門檻
- 採用指數成長門檻, 每級所需 XP 加倍.
- 公式: 下一級門檻 = 當前門檻 + (1000 * 2^(Level-1)).

### 3. 建築損耗 (XP Decay)
- 損耗規則: 每個行動週期 (Cycle) 結束後, 對所有建築執行 XP 損耗.
- 公式: `Decay_per_Cycle = int(Active_Players * 0.5) + int(Current_XP * (0.001 + Current_XP / 5,000,000))`.
  - **活躍人數基礎**: `Active_Players * 0.5` 確保即使低等級建築也有基礎維護壓力.
  - **動態 XP 比例**: 基礎 0.1% 隨 XP 增加而上升 (加上 `XP / 5M`), 形成指數級的維護牆.
- 平衡目標:
  - **Lv2 (3,000 XP)**: 極度輕鬆, 任何規模村莊皆可維持 (約需 0.2 ~ 0.3 人人力).
  - **Lv5 (31,000 XP)**: 需要努力, 約需 10-15% 活躍人口專職建造 (約需 1.5 人人力).
  - **Lv9 (511,000 XP)**: 幾乎無法到達, 損耗將超過任何正常規模村莊的產能極限.

### 4. 建築功能效果
- 廚房 (Food Efficiency): 
  - ID: 1
  - 效果: 降低行動所需的糧食消耗.
  - 公式: 每次週期消耗糧食 = `max(1, 10 - Level)`.
- 倉庫 (Storage Capacity): 
  - ID: 2
  - 效果: 總容量 = 1000 * (2 ^ Level).
- 加工 (Resource Yield): 
  - ID: 3
  - 效果: 全體產量乘算加成 = 1.0 + (Level * 0.1).

## Changelog
- 2026.04.07.00: Defined construction efficiency and 1-hour cycle building process. - See [2026.04.07.00.md](../changelogs/2026.04.07.00.md)
- 2026.04.08.00: Refactored to Cycle-based logic and aligned base output to 20 XP. - See [2026.04.08.00.md](../changelogs/2026.04.08.00.md)
- 2026.04.08.02: Increased base output from 20 XP to 50 XP. - See [2026.04.08.02.md](../changelogs/2026.04.08.02.md)
- 2026.04.08.03: Rebalanced building XP decay using a dynamic exponential model and added upgrade announcements. - See [2026.04.08.03.md](../changelogs/2026.04.08.03.md)

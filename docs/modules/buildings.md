# Module: Buildings

定義村莊建築的級距、效果公式與 1 小時循環建設機制.

### 1. 建設機制 (Building Process)
- 循環規則:
  - 啟動預扣: 每一小時循環開始時, 從村莊倉庫扣除 `1 糧食`、`10 木材` 與 `5 石材`.
  - 資源不足判定: 若木材或石材低於上述標準, 玩家將自動切換為 `idle` 狀態.
  - 產出結算: 1 小時結束後, 增加對應建築的 XP.
  - 不可退還: 資源一旦扣除, 即使玩家中斷行動也不予退還.
- 屬性掛鉤 (Efficiency Stats):
  - 建設效率: 知識 (KNO) + 耐力 (END).
- 效率公式: (知識 + 耐力) / 2 / 100.
- 產出公式: 基礎產出 (50 XP) * 效率係數.

### 2. XP 與等級門檻
- 採用指數成長門檻, 每級所需 XP 加倍.
- 公式: 下一級門檻 = 當前門檻 + (1000 * 2^(Level-1)).

### 3. 建築功能效果
- 糧食效率 (Food Efficiency): 
  - ID: 1
  - 效果: 1 糧食可支撐 `1.0 + (Level * 0.2)` 小時行動.
- 儲存容量 (Storage Capacity): 
  - ID: 2
  - 效果: 總容量 = 1000 * (2 ^ Level).
- 資源產量 (Resource Yield): 
  - ID: 3
  - 效果: 全體產量乘算加成 = 1.0 + (Level * 0.1).

## Changelog
- 2026.04.07.00: Defined construction efficiency and 1-hour cycle building process. See [2026.04.07.00.md](../../changelogs/2026.04.07.00.md)

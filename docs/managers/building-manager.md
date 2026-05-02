---
title: "Module: building-manager"
doc_type: module
last_reviewed: 2026-05-01
source_paths:
  - src/managers/building_manager.py
---

# Module: building-manager

管理四棟村莊建築的 XP 進度、等級升級與等級上限。

## 建築種類

| 建築 | XP 來源 | 設施加成效果 | 特殊功能 |
| :--- | :--- | :--- | :--- |
| 採集場 | 建設行動（玩家指定） | 全服採集效率 +FACILITY_BONUS_PER_LEVEL/級 | — |
| 加工廠 | 建設行動（玩家指定） | 全服建設效率 +FACILITY_BONUS_PER_LEVEL/級 | — |
| 狩獵場 | 建設行動（玩家指定） | 全服戰鬥效率 +FACILITY_BONUS_PER_LEVEL/級 | — |
| 研究所 | 研究行動（固定） | 全服研究效率 +FACILITY_BONUS_PER_LEVEL/級 | **等級 = 全服裝備等級上限** |

## XP 規則

- **建設行動**：玩家執行建設時，須指定目標建築（採集場/加工廠/狩獵場 擇一），XP 只進入該棟。
- **研究行動**：XP 固定進入研究所，無需選擇。
- **XP 永久保留**：不隨時間衰減。
- `xp_progress` 僅代表目前等級升到下一級的進度，不是 lifetime total XP。

## 升級門檻

每一級使用獨立進度條。升級時扣除需求，超出的 XP 留在新等級進度中。

```
xp_required_for_next_level = (current_level + 1) × BUILDING_XP_PER_LEVEL
```

| 目前等級 | 下一等級 | 需求 |
| :--- | :--- |
| Lv 0 | Lv 1 | 1 × BUILDING_XP_PER_LEVEL |
| Lv 1 | Lv 2 | 2 × BUILDING_XP_PER_LEVEL |
| Lv 2 | Lv 3 | 3 × BUILDING_XP_PER_LEVEL |
| Lv n | Lv n+1 | (n+1) × BUILDING_XP_PER_LEVEL |

例：Lv0 取得 `BUILDING_XP_PER_LEVEL + 50` XP 後升至 Lv1，扣除 `BUILDING_XP_PER_LEVEL`，留下 `xp_progress = 50`。Lv1 升 Lv2 需要 `2 × BUILDING_XP_PER_LEVEL`，因此還差 `2 × BUILDING_XP_PER_LEVEL - 50`。

## 等級上限

`level_cap = floor(stages_cleared / 5) + 1`

- 每通過一個升級關（第 5、10、15… 關），所有建築等級上限同步 +1。
- 初始等級上限為 1（0 關時 floor(0/5)+1 = 1）。
- 達到 level cap 時仍可累積 XP，但 `xp_progress` 不得超過 `(level + 1) × BUILDING_XP_PER_LEVEL`（即升級門檻）。
- 顯示範例：LvN capped 時最高顯示 `(N+1) × BUILDING_XP_PER_LEVEL / (N+1) × BUILDING_XP_PER_LEVEL`（100%），多餘 XP 不再增加。
- level cap 提升時，立即檢查所有建築是否可升級；可升多級時逐級升級並逐級通知。

## 操作介面（供其他模組呼叫）

- `addXP(building, amount)` — 增加指定建築 XP，並自動觸發升級檢查
- `getLevel(building)` — 取得當前等級
- `getXP(building)` — 取得當前等級的 XP 進度
- `getLevelCap()` — 取得當前等級上限（依 stage-manager 的 stages_cleared 計算）
- `checkUpgrade(building)` — 檢查是否達到升級門檻，若是則升級並觸發通知
- `checkAllUpgrades()` — level cap 提升後檢查所有建築

## Changelog

- 2026.05.02.03: Corrected XP cap rule: `xp_progress` cap at `(level + 1) × BUILDING_XP_PER_LEVEL` (upgrade threshold), not `level × BUILDING_XP_PER_LEVEL`. Display example updated accordingly.

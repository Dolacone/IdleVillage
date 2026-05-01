---
title: "Module: gear-manager"
doc_type: module
last_reviewed: 2026-05-01
source_paths:
  - src/managers/gear_manager.py
---

# Module: gear-manager

處理玩家裝備強化邏輯，包含成功率計算、保底機制與素材消耗。

## 裝備類型對應

| 裝備 | 行動類型 | 消耗素材 | 強化效果 |
| :--- | :--- | :--- | :--- |
| 採集道具 | 採集 | 工具素材 | 採集效率 +GEAR_BONUS_PER_LEVEL/級 |
| 建築工具 | 建設 | 建設素材 | 建設效率 +GEAR_BONUS_PER_LEVEL/級 |
| 武器防具 | 戰鬥 | 武器素材 | 戰鬥效率 +GEAR_BONUS_PER_LEVEL/級 |
| 研究裝備 | 研究 | 研究素材 | 研究效率 +GEAR_BONUS_PER_LEVEL/級 |

## 強化消耗

每次強化嘗試消耗：
- **1 AP**
- **目標等級個素材**（升至 n 級消耗 n 個，例如 Lv4→5 消耗 5 個）

失敗時 AP 與素材**全部消耗，不退還**。

## 成功率計算

```
current_level = 當前裝備等級
pity_count    = 當前保底累積次數（失敗次數，成功後歸零）

base_rate  = max(GEAR_MIN_SUCCESS_RATE, 100% - current_level × GEAR_RATE_LOSS_PER_LEVEL)
final_rate = min(100%, base_rate + pity_count × GEAR_PITY_BONUS)
```

## 強化流程

```
1. 前置檢查：
   - gear_level < research_institute_level（不得超過研究所等級上限）
   - player.ap >= 1
   - player.materials[type] >= target_level

2. 扣除資源：
   - AP -= 1
   - materials[type] -= target_level

3. 計算最終成功率（base_rate + pity × GEAR_PITY_BONUS）

4. 擲骰（random integer 1~100）：
   成功（roll <= final_rate）：
     → gear_level += 1
     → pity[type] = 0
     → 回傳成功結果

   失敗：
     → pity[type] += 1
     → 回傳失敗結果
```

## 操作介面（供其他模組呼叫）

- `attemptUpgrade(playerId, gearType)` — 執行強化嘗試，回傳 `{success, newLevel, rate}`
- `getUpgradeInfo(playerId, gearType)` — 回傳強化預覽資訊（成功率、消耗量、保底狀態）

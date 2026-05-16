---
title: "Module: gear-manager"
doc_type: module
last_reviewed: 2026-05-15
source_paths:
  - src/managers/gear_manager.py
---

# Module: gear-manager

處理玩家工具強化邏輯，包含成功率計算、保底機制與素材消耗。

## 工具類型對應

| 工具 | 行動類型 | 消耗素材 | 強化效果 |
| :--- | :--- | :--- | :--- |
| 採集工具 | 採集 | 工具素材 | 採集效率 +GEAR_BONUS_PER_LEVEL/級 |
| 建設工具 | 建設 | 建設素材 | 建設效率 +GEAR_BONUS_PER_LEVEL/級 |
| 狩獵工具 | 戰鬥 | 武器素材 | 戰鬥效率 +GEAR_BONUS_PER_LEVEL/級 |
| 研究工具 | 研究 | 研究素材 | 研究效率 +GEAR_BONUS_PER_LEVEL/級 |

## 強化模式

玩家可在每次強化時選擇三種模式，均消耗 1 AP：

| 模式 | 顯示名稱 | 素材消耗 | 擲骰 | 成功效果 | 失敗效果 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `normal` | 標準 | 目標等級個（升至 n 級消耗 n 個） | 是 | gear +1，pity 歸零 | pity +1 |
| `buffer` | 墊檔 | ceil(目標等級 / 2)，最少 1 個 | 否 | — | pity +1（保證觸發） |
| `risky` | 鐵齒 | 1 個 | 是 | gear +1，pity 歸零 | gear 歸零、pity 歸零；`risky_failed_levels` += 當前等級 |

三種模式共用相同前置條件：gear_level < research_institute_level、AP >= 1、素材 >= 該模式消耗量。
失敗時 AP 與素材**全部消耗，不退還**。

## 強化消耗（依模式）

- **標準**：1 AP + 目標等級個素材（升至 n 級消耗 n 個，例如 Lv4→5 消耗 5 個）
- **墊檔**：1 AP + ceil(目標等級 / 2) 個素材（最少 1 個）
- **鐵齒**：1 AP + 1 個素材

## 成功率計算

```
current_level        = 當前裝備等級
pity_count           = 當前保底累積次數（失敗次數，成功後歸零）
risky_failed_levels  = 玩家全域鐵齒炸裂等級總額（僅鐵齒模式失敗時累加）

base_rate  = max(GEAR_MIN_SUCCESS_RATE, 100% - current_level × GEAR_RATE_LOSS_PER_LEVEL)

# 標準 / 鐵齒：
final_rate = min(100%, base_rate + pity_count × GEAR_PITY_BONUS + risky_failed_levels × 0.0001)

# 墊檔：
final_rate = min(100%, base_rate + pity_count × GEAR_PITY_BONUS)
```

成功率必須依設定值的十進位意圖計算，不得因二進位浮點誤差低於文件公式結果。
例如 `GEAR_RATE_LOSS_PER_LEVEL=0.10` 時，Lv6 且 `pity_count=0` 的
`base_rate` 與 `final_rate` 都是 40%，不是 39.999999999% 或 39%。

## 強化流程

```
1. 前置檢查：
   - gear_level < research_institute_level（不得超過研究所等級上限）
   - player.ap >= 1
   - player.materials[type] >= material_cost（依所選模式計算）

2. 扣除資源：
   - AP -= 1
   - materials[type] -= material_cost

3. 依模式執行：

   標準 (normal)：
     計算 final_rate（base_rate + pity × GEAR_PITY_BONUS + risky_failed_levels × 0.0001）
     擲骰（random integer 1~100）：
       成功（roll <= final_rate）：gear_level += 1, pity = 0
       失敗：pity += 1

   墊檔 (buffer)：
     不擲骰，直接 pity += 1，gear_level 不變

   鐵齒 (risky)：
     計算 final_rate（base_rate + pity × GEAR_PITY_BONUS + risky_failed_levels × 0.0001）
     擲骰（random integer 1~100）：
       成功（roll <= final_rate）：
         level_gain = 1
         gear_level += 1, pity = 0
       失敗：
         risky_failed_levels += current_level（強化前等級）
         gear_level = 0（工具等級歸零）
         pity = 0（失去所有累積保底）

4. 回傳結果（success, new_level, level_gain, pity_before, pity_after, rate, mode）
```

## 操作介面（供其他模組呼叫）

- `attempt_upgrade(db, user_id, gear_type, now, mode="normal")` — 執行強化嘗試，回傳 `{success, new_level, level_gain, pity_before, pity_after, rate, mode}`
- `get_upgrade_info(db, user_id, gear_type, now, mode="normal")` — 回傳強化預覽資訊（成功率、依模式計算的消耗量、保底狀態、模式）；標準與鐵齒模式額外回傳 `risky_failed_levels` 與 `risky_bonus_pct`

## Changelog

- 2026.05.16: Standard (normal) mode now includes `risky_failed_levels × 0.0001` in success rate, same as risky mode. `get_upgrade_info()` now returns `risky_failed_levels` and `risky_bonus_pct` for normal mode in addition to risky mode. UI embed displays the risky bonus line for normal mode.

- 2026.05.15: Risky mode simplification — removed random multi-level gain on success (was +1/+2/+3 at 60/30/10% when pity=0); success now always grants exactly gear +1 regardless of pity state.
- 2026.05.15: Risky mode enhancements — permanent `risky_failed_levels` bonus (+0.01% per level), multi-level success (+1/+2/+3 at 60/30/10% when pity=0), research institute cap is precondition-only and does not truncate results.
- 2026.05.15: Added three upgrade modes — 標準 (normal), 墊檔 (buffer), 鐵齒 (risky). Each mode has distinct material cost and pity behavior. `attempt_upgrade()` and `get_upgrade_info()` now accept a `mode` parameter.
- 2026.05.06.01: Official user-facing gear naming changed to tools:
  採集工具, 建設工具, 狩獵工具, 研究工具.
- 2026.05.06.00: Defined the gear success-rate precision contract. Decimal
  config values such as `0.10` must calculate at their intended percent value,
  so Lv6 with no pity is exactly 40%.

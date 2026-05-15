---
title: "鐵齒強化模式移除隨機多段升級"
status: Ready-to-implement
created: 2026-05-15
doc_type: change
last_reviewed: 2026-05-15
source_paths:
  - src/managers/gear_manager.py
  - docs/managers/gear-manager.md
scope: "Tracks this change from design through review."
---

## Problem Statement

如何讓鐵齒強化模式的成功結果更易預測，同時維持其高風險高報酬的定位？

## Recommended Direction

移除鐵齒模式成功時的隨機多段升級邏輯（pity=0 時 +1/+2/+3 各 60/30/10%），改為不論 pity 狀態，成功一律 gear +1。

鐵齒模式的核心差異化在於：
- 最低素材消耗（1 個）
- 失敗時 gear 歸零、pity 歸零（高風險）
- `risky_failed_levels` 永久累積，轉化為後續成功率加成

隨機多段升級是錦上添花但引入了不必要的隨機性。移除後，鐵齒的風險/報酬模型更清晰：用最少素材賭一次 +1，失敗代價是清零。

## Key Assumptions

- [x] 鐵齒成功時不再區分 pity=0 / pity>0，一律 gear +1，pity 歸零
- [x] 失敗行為不變：gear 歸零、pity 歸零、risky_failed_levels += 當前等級
- [x] 成功率公式不變（base_rate + pity × GEAR_PITY_BONUS + risky_failed_levels × 0.0001）
- [x] `level_gain` 回傳值固定為 1（不再有 2 或 3 的情況）

## MVP Scope

- `gear_manager.py`：`attempt_upgrade()` 鐵齒成功分支，移除 pity=0 判斷與隨機抽取邏輯，改為 `level_gain = 1`
- `gear-manager.md`：更新強化模式表格與流程描述，移除 pity=0 隨機說明
- 測試更新：確保鐵齒成功只回傳 `level_gain=1`，移除 +2/+3 測試情境

## Not Doing

- 調整成功率公式
- 調整失敗懲罰（gear 歸零）
- 調整素材消耗
- 為 pity=0 引入任何其他特殊行為

## Tasks

<!-- Tasks 1, 2, 3 are independent and can be implemented in parallel. -->

- [ ] Task 1: 移除 `gear_manager.py` 鐵齒成功的隨機多段升級邏輯，固定 `level_gain = 1`
  - 在 `attempt_upgrade()` 的鐵齒成功分支，移除 `if pity == 0` 判斷與隨機抽取（60/30/10%）
  - 改為直接 `level_gain = 1`，無論 pity 狀態
  - 驗收：`attempt_upgrade()` 鐵齒成功路徑回傳的 `level_gain` 永遠為 1

- [x] Task 2: 更新 `docs/managers/gear-manager.md` 移除隨機升級描述
  - 強化模式表格中 `risky` 的「成功效果」欄位改為 `gear +1，pity 歸零`
  - 強化流程中鐵齒成功分支移除 `若 pity = 0：level_gain = 隨機選取（+1: 60%, +2: 30%, +3: 10%）` 及「否則」分支，改為 `level_gain = 1`
  - 移除「注意：研究所等級上限僅在前置檢查時驗證，不截斷多段升級結果。」（該注意事項僅適用於多段升級場景）
  - Changelog 補一條記錄本次變更
  - 驗收：文件中不再出現 pity=0 隨機升級的說明

- [x] Task 3: 更新測試，確認鐵齒成功只有 `level_gain=1`
  - 移除測試中 pity=0 時 level_gain=2 或 level_gain=3 的斷言或測試案例
  - 確認 pity=0 與 pity>0 的鐵齒成功均斷言 level_gain=1
  - 驗收：所有測試通過，且無任何測試期望 level_gain>1

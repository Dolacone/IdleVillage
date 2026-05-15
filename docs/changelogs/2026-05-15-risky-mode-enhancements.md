---
title: "鐵齒模式強化：永久保底與多段升級"
status: Issues-confirmed
created: 2026-05-15
doc_type: change
last_reviewed: 2026-05-15
source_paths:
  - src/managers/gear_manager.py
  - src/cogs/ui_renderer.py
  - src/database/schema.py
  - tests/test_gear_manager.py
  - tests/test_discord_commands.py
scope: "Tracks this change from design through review."
---

## Problem Statement

鐵齒模式目前只有「省材料但失去保底」的特性，缺乏長期累積的誘因。
新增永久成功率加成與多段升級機制，強化高風險高回報的定位。

## Recommended Direction

**永久保底（鐵齒等級）**
- 每次鐵齒失敗，將強化前的當前等級加入玩家全域 `risky_failed_levels`（四種工具共用整數）
- 成功率公式加入第三項：`base_rate + pity × GEAR_PITY_BONUS + risky_failed_levels × 0.01%`
- UI 在鐵齒模式下額外顯示一行：`鐵齒等級: {n} (+{n×0.01}%)`

**多段升級**
- 鐵齒成功且 pity = 0 時，隨機 +1/+2/+3（60% / 30% / 10%）
- pity > 0 時僅 +1（與現行相同）
- 研究所等級上限僅作前置檢查（gear_level < research_institute_level），不截斷多段升級結果

## Key Assumptions

- `risky_failed_levels` 為 per-player 全域整數，四種工具共用
- 失敗時累加的是強化前的當前等級（11→12 失敗 → +11）
- 多段升級亂數權重：+1(60%), +2(30%), +3(10%)
- 研究所上限不截斷鐵齒多段升級結果（例：Lv4 成功 +3 → Lv7，即使研究所 Lv5）

## MVP Scope

- DB schema：`players` 表新增 `risky_failed_levels INTEGER NOT NULL DEFAULT 0`
- `gear_manager`：鐵齒失敗累積 `risky_failed_levels`；成功率公式加入第三項；pity=0 時多段升級
- `get_upgrade_info()`：回傳 `risky_failed_levels` 與加成百分比供 UI 使用
- UI：鐵齒模式新增 `鐵齒等級` 行；更新模式 Dropdown 描述

## Not Doing

- 其他模式（標準、墊檔）受 `risky_failed_levels` 影響
- 截斷多段升級結果至研究所上限
- 不同工具各自獨立的 `risky_failed_levels`

## Tasks

- [x] Task 1: DB schema 新增 `risky_failed_levels` 欄位；`gear_manager` 實作永久保底累積、成功率第三項、多段升級；`get_upgrade_info()` 回傳 `risky_failed_levels` 與加成；新增 / 更新 tests
- [x] Task 2: UI embed 新增 `鐵齒等級` 行；更新模式 Dropdown 描述；新增 / 更新 UI tests

## Review Issues

- [x] Important: 鐵齒失敗不應重設工具等級。`docs/managers/gear-manager.md` 的鐵齒失敗流程只要求 `risky_failed_levels += current_level` 與 `pity = 0`，但 `src/managers/gear_manager.py` 目前在失敗時呼叫 `set_gear_level(..., 0, ...)` 並回傳 `new_level = 0`。`tests/test_gear_manager.py` 也用 `test_risky_failure_resets_gear_level_to_zero` 鎖住這個與規格不符的行為。
- [x] Important: 鐵齒失敗規格仍未一致。`src/managers/gear_manager.py` 目前在鐵齒失敗時保留 `gear_level` 並回傳原等級，`tests/test_gear_manager.py::test_risky_failure_preserves_gear_level` 也鎖住此行為；但 `docs/managers/gear-manager.md` 仍寫失敗效果為 `gear 歸零` / `gear_level = 0`，且 `src/cogs/ui_renderer.py` 的鐵齒失敗訊息仍顯示「等級與保底計數歸零」。需先確認鐵齒失敗是否應重設工具等級，再同步實作、測試、UI 文案與文件。
- [ ] Important: 鐵齒失敗 gear 歸零仍未實作。最後複查要求以 `gear_level = 0` 為準；`docs/managers/gear-manager.md` 已寫明鐵齒失敗 `gear_level = 0`，但 `src/managers/gear_manager.py` 的鐵齒失敗分支未呼叫 `set_gear_level(..., 0, ...)`，仍回傳 `new_level = gear_level`；`tests/test_gear_manager.py` 也沒有 `test_risky_failure_resets_gear_level_to_zero`，目前存在的 `test_risky_failure_preserves_gear_level` 反而斷言 DB gear 保持 5。需同步程式、測試名稱與斷言，並確認 UI 失敗訊息仍符合最終規格。

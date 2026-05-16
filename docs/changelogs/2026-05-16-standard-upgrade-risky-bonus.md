---
title: "標準升級成功率納入鐵齒炸裂等級加成"
status: Ready-to-review
created: 2026-05-16
doc_type: change
last_reviewed: 2026-05-16
source_paths:
  - src/managers/gear_manager.py
  - src/cogs/ui_renderer.py
  - tests/test_gear_manager.py
  - tests/test_discord_commands.py
  - docs/managers/gear-manager.md
scope: "Tracks this change from design through review."
---

## Problem Statement

目前鐵齒炸裂等級（`risky_failed_levels`）只對鐵齒模式的成功率有加成效果，標準模式完全無法受益。玩家在鐵齒失敗後切換回標準模式，過去的犧牲沒有任何補償，導致鐵齒風險回報感不足。

## Recommended Direction

在標準（normal）模式的成功率公式中加入與鐵齒模式相同的 `risky_failed_levels` 加成項：

```
# 修改後的標準模式公式：
final_rate = base_rate + pity_count × GEAR_PITY_BONUS + risky_failed_levels × 0.0001
```

讓兩種模式共享相同的 `risky_failed_levels` 加成邏輯，使鐵齒炸裂的代價在任何模式下都能兌換成長期補償。

## Clarifications

Q: 標準模式套用 `risky_failed_levels` 的加成倍率應該是多少？
A: 與鐵齒相同（×0.0001，即每炸1級+0.01%）。

Q: 是否要對標準模式的 `risky_failed_levels` 加成設上限？
A: 不設上限，與鐵齒模式一致。

## MVP Scope / Not Doing

**做：**
- 標準模式成功率公式加入 `risky_failed_levels × 0.0001`
- 更新 `get_upgrade_info` 在標準模式下也回傳 `risky_failed_levels` 與 `risky_bonus_pct`（或將此資訊納入現有回傳格式）
- 更新 `docs/managers/gear-manager.md` 中的成功率公式文件

**不做：**
- 不更改倍率（維持 0.0001）
- 不為標準模式設置 risky_failed_levels 加成的獨立上限
- 不更動墊檔（buffer）模式的公式

## Architecture Decisions

- **`_compute_rate()` 條件擴展**：將 `if mode == "risky":` 改為 `if mode in ("normal", "risky"):`，讓 normal 模式也套用 `risky_failed_levels × 0.0001` 加成；buffer 模式維持不變。這是最小改動，保持函式簽名與參數語意不變。
- **`get_upgrade_info()` 回傳欄位擴展**：將 `risky_failed_levels` 和 `risky_bonus_pct` 的回傳條件從 `mode == "risky"` 改為 `mode in ("normal", "risky")`，讓呼叫端在 normal 模式下也能顯示此加成資訊；buffer 模式不回傳（buffer 不受此加成影響）。
- **UI Renderer 顯示**：`ui_renderer.py` 目前只對 risky 模式顯示炸裂加成一行。Normal 模式現在也受影響，應同步顯示，讓玩家能看到此加成。
- **測試更新策略**：現有斷言「normal 模式忽略 risky_failed_levels」的測試需更新為驗證「包含加成」；新增 `attempt_upgrade()` 在 normal 模式下受 `risky_failed_levels` 影響的迴歸測試；assert 值（非僅欄位存在）；buffer 模式相關測試維持不變。

## Tasks

- [x] Task 1：更新 `src/managers/gear_manager.py` — `_compute_rate()` 條件改為 `mode in ("normal", "risky")`；`get_upgrade_info()` risky 欄位回傳條件同步改為 `mode in ("normal", "risky")`；更新函式 docstring（`_compute_rate` 第 32 行與 `get_upgrade_info` 第 98 行）說明 normal 模式也套用此加成
- [x] Task 2：更新 `src/cogs/ui_renderer.py` — (a) 將第 356 行 `if mode == "risky" and rate > final_rate:` 改為 `if mode in ("normal", "risky") and rate > final_rate:`，讓 normal 模式的 `final_rate_pct` 也套用含 risky_failed_levels 加成的實際費率；(b) 將第 379 行 `if mode == "risky":` 改為 `if mode in ("normal", "risky"):`，讓 normal 模式也顯示炸裂加成行
- [x] Task 3：更新 `tests/test_gear_manager.py` — (a) 將 `test_compute_rate_normal_ignores_failed_levels` 改為驗證 normal 模式包含加成（含 assert 值）；(b) 更新 `test_get_upgrade_info_risky_rate_includes_failed_levels` 為驗證 normal 模式費率也反映 risky_failed_levels；(c) 更新 `test_get_upgrade_info_normal_does_not_return_risky_fields` 改為驗證 normal 模式確實回傳這兩個欄位（含值驗證）；(d) 新增 normal 模式 `attempt_upgrade()` 迴歸測試：確認 `risky_failed_levels` 影響回傳 `rate`
- [x] Task 4：更新 `tests/test_discord_commands.py` — (a) 修正 `normal` 模式下不顯示炸裂加成行的斷言，改為驗證確實顯示；(b) 補充驗證 normal 模式成功率文字反映加成後的費率
- [x] Task 5：更新 `docs/managers/gear-manager.md` — 成功率公式區塊中「標準 / 墊檔」分開列出，標準包含 risky_failed_levels 加成，墊檔不含；更新 `get_upgrade_info` 介面說明；更新 Changelog

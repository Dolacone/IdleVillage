---
title: "鐵齒升級成功隨機多段升級（50/35/15%）"
status: Ready-to-implement
created: 2026-05-31
doc_type: change
last_reviewed: 2026-05-31
source_paths: []
scope: "鐵齒升級成功時改為隨機 +1/+2/+3（50/35/15%），不限 pity 狀態。"
---

## Problem Statement

鐵齒模式成功目前固定 +1，高風險僅在「省素材」與「risky_failed_levels 累積」上有體現，成功報酬沒有上升空間。玩家在高等級反覆鐵齒時，成功一律 +1 顯得單調，缺乏興奮感。

## Recommended Direction

鐵齒升級成功時，隨機決定升級幅度：

| 結果 | 機率 |
| :--- | :--- |
| +1 | 50% |
| +2 | 35% |
| +3 | 15% |

此隨機不受 pity 狀態影響（與 2026-05-15 舊版「pity=0 才觸發」不同）。
研究所等級上限仍僅作前置檢查，不截斷多段升級結果（例：Lv4 鐵齒成功 +3 → Lv7，即使研究所 Lv5）。

選此方向而非「pity=0 才觸發」，因為玩家在任何保底狀態下成功都應獲得相同的報酬期望，不應因為剛好 pity > 0 而損失多段升級機會。
選此機率分佈（50/35/15）而非舊版（60/30/10），因為平均期望值提高（舊 1.5 → 新 1.65），強化鐵齒模式的高報酬定位。

## Clarifications

無需額外釐清。

## MVP Scope / Not Doing

做：
- `gear_manager.py`：鐵齒成功時依 50/35/15% 隨機決定 `level_gain`（1/2/3）
- `docs/managers/gear-manager.md`：更新強化模式表、強化流程描述
- `docs/discord/ui-renderer.md`：更新鐵齒 Dropdown 描述含多段升級說明
- `src/cogs/ui_renderer.py`：更新鐵齒 Dropdown 描述文字
- 測試更新：覆蓋 +1/+2/+3 三條路徑

不做：
- 研究所上限截斷（維持現行前置檢查即可）
- 標準或墊檔模式的多段升級
- pity 加權（pity 狀態不影響多段升級機率）

## Key Assumptions

- `level_gain` 回傳值可為 1、2 或 3；UI 現有邏輯已使用 `level_gain` 顯示升幅，無需另改 embed 格式

## Architecture Decisions

1. 在 `gear_manager.py` 鐵齒成功分支，以 `random.choices([1, 2, 3], weights=[50, 35, 15])[0]` 決定 `level_gain`，替換原本的 `level_gain = 1`。
2. `gear_level += level_gain`（不截斷至研究所上限）；pity 歸零。
3. 回傳的 `level_gain` 可為 1/2/3，呼叫端（UI）已使用此欄位，無需修改介面簽名。
4. 文件同步：`gear-manager.md` 強化模式表與流程、`ui-renderer.md` Dropdown 描述。
5. `ui_renderer.py` 鐵齒 Dropdown 描述更新為：`僅消耗 1 個素材，成功 +1~+3（50/35/15%），失敗則工具等級與 pity 均歸零`。
6. 工具強化成功通知的 `target_level` 改為使用 `new_level`（= `current_level + level_gain`）而非固定 `current_level + 1`，以正確反映多段升級結果。`notification.md` 更新 `target_level` 定義；`notification.py`/`actions.py` 傳入實際 `new_level`。

## Tasks

- [ ] Task 1: `gear_manager.py` 鐵齒成功分支改用 50/35/15% 隨機 level_gain；更新 `tests/test_gear_manager.py` 覆蓋三條路徑；更新 `docs/managers/gear-manager.md` 強化模式表與流程
  - Files: `src/managers/gear_manager.py`, `tests/test_gear_manager.py`, `docs/managers/gear-manager.md`
  - Acceptance: 鐵齒成功可回傳 level_gain=1/2/3；gear_level 正確累加；pity 歸零；舊 level_gain=1 固定測試移除或更新；三條路徑均有測試

- [ ] Task 2: `ui_renderer.py` 鐵齒 Dropdown 描述更新；更新 `docs/discord/ui-renderer.md`；在 `tests/test_discord_commands.py` 驗證 Dropdown 描述文字
  - Files: `src/cogs/ui_renderer.py`, `docs/discord/ui-renderer.md`, `tests/test_discord_commands.py`
  - Depends on: Task 1（level_gain 結構確認）
  - Acceptance: 鐵齒 Dropdown 描述含「+1~+3（50/35/15%）」字樣；至少一個測試驗證描述文字

- [ ] Task 3: 修正工具強化成功通知使用實際 `new_level` 而非固定 `current_level + 1`；更新 `docs/discord/notification.md` 的 `target_level` 定義；在 `tests/test_discord_commands.py` 或 `tests/test_discord_notifications.py` 驗證通知使用正確終點等級
  - Files: `src/cogs/actions.py`, `docs/discord/notification.md`, `tests/test_discord_commands.py`
  - Depends on: Task 1（level_gain 結構確認）
  - Acceptance: 鐵齒成功 +2 時通知顯示 `Lv{n} -> Lv{n+2}`；至少一個測試覆蓋此路徑

## Plan Review Issues

- [x] 公開強化通知仍以 `target_level = current_level + 1` 顯示結果；鐵齒成功 +2/+3 時會公告錯誤終點等級。已新增 Task 3 修正，並在 AD6 說明決策。
- [x] Task 2 要求「在現有測試中驗證 Dropdown 描述文字」，但 Files 未列出對應測試檔。已補入 `tests/test_discord_commands.py`。

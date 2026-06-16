---
title: "在個人資訊 AP 欄顯示下次回復時間"
status: Done
created: 2026-06-16
doc_type: change
last_reviewed: 2026-06-16
source_paths:
  - src/cogs/ui_renderer.py
  - tests/test_discord_commands.py
scope: "Tracks this change from design through review."
---

## Problem Statement

個人資訊的 AP 欄目前只顯示 `⚡ AP：{ap} / {ap_cap}`，玩家無法得知下一點 AP 何時回復，難以規劃行動時機。

## Recommended Direction

在 AP 行尾追加 Discord 相對時間戳：
`⚡ AP：{ap} / {ap_cap}（下次：<t:{next_ap_unix}:R>）`

- AP 已滿（`ap >= ap_cap`）時不顯示括號部分。
- 下次回復時間公式：`ap_full_time - (ap_cap - ap - 1) × AP_RECOVERY_MINUTES`
- 使用 Discord `<t:unix:R>` 相對時間格式，與「下次結算」顯示慣例一致。

## Clarifications

Q: 是否需要顯示「距離 AP 全滿的時間」？
A: 不需要，只顯示下一點 AP 的增加時間即可。

## MVP Scope / Not Doing

- 只修改 `⚡ AP` 顯示行，不新增 AP 相關邏輯
- 不修改 AP 計算、消耗流程

## Architecture Decisions

- `player_row["ap_full_time"]` 已有 ISO datetime string，直接用於計算，不新增 DB 查詢
- 需要在 `ui_renderer.py` 的 `build_main_embed()` 傳入 `ap_full_time` 並計算 `next_ap_unix`
- Discord timestamp format: `<t:{unix}:R>` 顯示相對時間（如「3 分鐘後」）

## Key Assumptions

- `player_row["ap_full_time"]` 在 `build_main_embed()` 呼叫時已存在且為 ISO 格式字串
- `AP_RECOVERY_MINUTES` 從 env var 讀取，與 `player_manager.py` 邏輯一致

## Tasks

- [x] Task 1: 在 `ui_renderer.py` 的 `build_main_embed()` 中，讀取 `ap_full_time` 並計算 `next_ap_unix`，在 AP < AP_CAP 時追加 `（下次：<t:{next_ap_unix}:R>）`
  - 接受標準：AP < cap 時顯示相對時間戳；AP == cap 時不顯示括號部分
- [x] Task 2: 新增或更新對應測試
  - 接受標準：測試覆蓋 AP < cap 與 AP == cap 兩種情況；包含 `next_ap_unix` 精確數值驗證（AP = 0、AP = cap - 1、`ap_full_time` 非整分鐘邊界）

## Plan Review Issues

- [x] Task 2 測試範圍偏鬆：只列 AP < cap 與 AP == cap 兩種 case，未要求驗證 `next_ap_unix` 數值精確性（如 AP = 0、AP = cap - 1、以及 `ap_full_time` 非整分鐘邊界）。建議補充 `next_ap_unix` 的精確公式驗證 case，防止公式偏差卻仍通過測試。

## Review Issues

- [Minor] `tests/test_discord_commands.py:445-460` `test_ap_next_recovery_exact_value_non_integer_boundary` 使用 `ap = ap_cap - 1`，導致乘數 `(ap_cap - ap - 1) = 0`，`expected_next` 實際等於 `ap_full_time_unix`，與 37 秒偏移無關。測試名稱宣稱驗證非整分鐘邊界，但真正驗證的是 ap = cap - 1 的場景；應改用 ap_cap - 2 之類的值使乘數 > 0，才能確認偏移秒數被正確保留而非截斷。

---
title: "調整強化介面成功率顯示格式"
status: Done
created: 2026-05-16
doc_type: change
last_reviewed: 2026-05-16
source_paths:
  - src/cogs/ui_renderer.py
  - tests/test_discord_commands.py
  - docs/discord/ui-renderer.md
scope: "調整工具強化嵌入訊息中成功率行的顯示格式，並分拆保底率與鐵齒率的明細行。"
---

## Problem Statement

現行強化介面的成功率行僅以 `(+3×5% 保底)` 格式顯示保底加成，且鐵齒等級另外顯示於最底部，導致：
- 讀者須自行心算才能知道保底實際加了幾 %
- 鐵齒等級貢獻率未納入成功率行的說明
- 鐵齒等級資訊與成功率的關聯性不直觀

## Recommended Direction

調整成功率行格式，並於其下方新增兩行明細，同時移除底部的 `鐵齒等級` 獨立行：

**Before**
```
成功率：10%（+3×5% 保底）= 35%
...
鐵齒等級: 1000 (+10.0%)
```

**After**
```
成功率：10%（+保底15% +鐵齒10%）= 35%
保底率：3 x 5% = 15%
鐵齒率：1000 x 0.01% = 10%
```

調整範圍：純 UI 文字格式，不改變任何計算邏輯。

## Clarifications

無需澄清。使用者已提供精確的 before/after 範例。

## MVP Scope / Not Doing

**In scope**
- 更新標準模式強化預覽嵌入訊息的成功率行格式
- 新增 `保底率` 與 `鐵齒率` 明細行
- 移除底部 `鐵齒等級` 獨立行

**Not doing**
- 更改鐵齒模式（risky）或墊檔模式（buffer）的顯示格式（除非其共用同一段顯示邏輯，需同步調整）
- 更改任何計算邏輯

## Architecture Decisions

- 純 UI 格式調整，不觸及任何計算邏輯
- `risky_failed_levels` 與 `risky_bonus_pct` 的擷取提前至 rate_line 組裝之前，以供格式化使用
- 以 `f"{risky_bonus_pct:g}"` 去除浮點數尾隨零（10.0 → "10"，0.05 → "0.05"）
- 保底率與鐵齒率明細行僅在 normal / risky 模式下插入，buffer 模式維持原有的單行說明

## Tasks

- [x] Task 1: 更新 `ui_renderer.py` 成功率行格式並插入明細行，同步更新相關測試

## Review Issues

---
title: "試煉達成通知每行格式順序調整"
status: Draft
created: 2026-08-09
doc_type: change
last_reviewed: 2026-08-09
source_paths: []
scope: "Tracks reordering each participant line in the 試煉達成 (trial_success) notification from name-first to contribution-first."
---

## Problem Statement

上次調整（`docs/changes/2026-08-08-trial-success-player-name.md`）已將試煉達成通知的參與者清單從 `<@{user_id}>` mention 改成顯示玩家名稱，顯示內容本身符合預期。這次要求只調整每一行內部欄位的排列順序，不改變欄位內容、不改變跨行排序（仍依貢獻降冪）。

目前每行格式：
```
{display_name}：貢獻 {contribution}，獲得 {reward} 個
```

要改成：
```
貢獻 {contribution} ({reward} 素材)：{display_name}
```

範例（僅格式順序改變，數值與跨行排序不變）：
```
貢獻 6138 (62 素材)：Yai
貢獻 5415 (55 素材)：archie
貢獻 1656 (17 素材)：Mei/乾媽的工人
```

## Recommended Direction

只修改 `src/core/notification.py` 的 `_format_event` 函式中 `trial_success` 分支組每一行文字的 f-string，將欄位順序由 `{display_name}：貢獻 {contribution}，獲得 {reward} 個` 改為 `貢獻 {contribution} ({reward} 素材)：{display_name}`。不改變：
- 迴圈本身（仍依 `participants` 既有順序逐行輸出，該順序已由呼叫端依貢獻降冪排序，本次不觸碰排序邏輯）。
- 截斷規則（超過 1900 字元截斷 + 提示文字，不受影響）。
- `name_map` 解析機制（member cache 優先、fetch_member fallback、`user_id` 最終 fallback）完全不變，本次只動最終字串组裝的欄位順序。

此為單一位置的字串樣板調整，範圍極小，不存在需要比較的替代方案。

## Clarifications

<!-- Q: 跨行排序是否也要調整？ / A: 不需要，使用者明確表示「across multiple rows are the same, order by 貢獻」，只調整單行內的欄位順序。 — resolved during idea stage -->
<!-- Q: 「素材」字樣要放在哪裡？ / A: 使用者提供的目標格式為 `({reward} 素材)`，直接採用。 — resolved during idea stage -->

## MVP Scope / Not Doing

- 範圍內：
  - `src/core/notification.py`：`_format_event` 的 `trial_success` 分支，調整參與者行的 f-string 順序。
  - `docs/discord/notification.md`：更新試煉達成範本、Changelog。
  - 測試：更新 `tests/test_discord_notifications.py` 中斷言舊格式字串的既有測試，改為新格式。
- 範圍外：
  - 跨行排序邏輯（維持依貢獻降冪，不變動）。
  - `trial_start`／`trial_fail` 訊息格式（未受影響）。
  - 名稱解析機制（`dispatch_events` 的 cache/fetch_member 邏輯，本次不動）。

## Key Assumptions

- 無新假設；沿用上次變更已驗證的名稱解析行為，本次純屬顯示格式調整，無需重新驗證解析邏輯本身。

## Architecture Decisions

<!-- 於 plan 階段補充 -->

## Tasks

<!-- 於 plan 階段補充 -->

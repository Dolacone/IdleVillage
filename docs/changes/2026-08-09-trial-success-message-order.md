---
title: "試煉達成通知每行格式順序調整"
status: Ready-to-implement
created: 2026-08-09
doc_type: change
last_reviewed: 2026-08-09
source_paths:
  - src/core/notification.py
  - docs/discord/notification.md
  - tests/test_discord_notifications.py
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

1. **只改字串樣板，不動迴圈與資料結構**：`for p in participants:` 迴圈、`name_map.get(...)` 解析呼叫、`lines.append(...)` 的位置全部不變，只改 `lines.append()` 內的 f-string 內容本身，將 `f"{display_name}：貢獻 {p['contribution']}，獲得 {p['reward']} 個"` 改為 `f"貢獻 {p['contribution']} ({p['reward']} 素材)：{display_name}"`。維持最小 diff。

## Tasks

- [x] Task 1: `src/core/notification.py` — 調整 `_format_event` 的 `trial_success` 分支參與者行格式
  - Files: `src/core/notification.py`
  - Tests: 更新 `tests/test_discord_notifications.py`：
    - `test_format_trial_success` 斷言改為 `貢獻 3000 (25 素材)：Alice`／`貢獻 2000 (25 素材)：Bob`
    - `test_format_trial_success_without_name_map_falls_back_to_user_id` 斷言改為 `貢獻 3000 (25 素材)：111`
    - `test_format_trial_success_truncates_long_participant_list` 沿用新格式產生的行文字，確認截斷邏輯（1900 字元 + 提示文字）仍正確觸發
    - `test_dispatch_events_resolves_trial_success_participant_names`、`test_dispatch_events_trial_success_fetch_member_failure_falls_back_to_user_id`、`test_dispatch_events_mixed_batch_only_resolves_trial_success_names`、`test_dispatch_events_uses_member_cache_without_network_call`、`test_dispatch_events_trial_success_transport_error_falls_back_without_aborting_batch` 等既有 `dispatch_events` 測試的文字斷言同步改為新格式（僅調整斷言字串順序，不改測試邏輯本身）
  - Depends on: 無
  - Acceptance: 每行格式為 `貢獻 {contribution} ({reward} 素材)：{display_name}`；跨行排序（依貢獻降冪）、截斷規則、`name_map` 解析（cache/fetch_member/user_id fallback）、`allowed_mentions` 皆不受影響；全數測試通過

- [ ] Task 2: `docs/discord/notification.md` 更新試煉達成範本
  - Files: `docs/discord/notification.md`
  - Tests: 無（文件變更）
  - Depends on: Task 1（需與實作後的實際格式一致）
  - Acceptance: 範本改為 `貢獻 {contribution} ({reward} 素材)：{display_name}`；`last_reviewed` 更新為實作當日日期；新增 Changelog 條目說明此次格式調整

### 平行任務標記（僅供未來參考，目前循序執行）

- 無可平行任務：Task 2 依賴 Task 1 完成後的實際格式。

## Plan Review Issues

- [x] Issue 1: `source_paths` 在 frontmatter（line 7）仍是 `[]`，但本計畫已實際檢視並引用三個檔案的確切內容：`src/core/notification.py`（Architecture Decisions, line 63，逐字引用 `_format_event` 的 `trial_success` 分支現有 f-string）、`tests/test_discord_notifications.py`（Tasks, line 69-73，逐一列出既有測試名稱與斷言字串）、`docs/discord/notification.md`（Problem Statement, line 15-18，引用現有範本）。依 `AGENTS.md` 規則「當描述已實作行為時，需以實際建立或檢視過的檔案更新 `source_paths`」，且同系列前一份計畫文件 `docs/changes/2026-08-08-trial-success-player-name.md` 已將這三個檔案列入 `source_paths`，本文件應比照補上，而非留空。

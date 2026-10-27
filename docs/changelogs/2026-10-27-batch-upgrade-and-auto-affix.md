---
title: "工具強化執行次數與自動抽取所有空格"
status: Draft
created: 2026-10-27
doc_type: change
last_reviewed: 2026-10-27
source_paths:
  - docs/README.md
  - docs/changelogs/2026-10-27-batch-upgrade-and-auto-affix.md
  - docs/discord/command-handler.md
  - docs/discord/notification.md
  - docs/discord/ui-renderer.md
  - src/cogs/actions.py
  - src/cogs/ui_renderer.py
  - src/core/notification.py
scope: "Tracks this change from design through review."
---

## Problem Statement

重複強化與重複抽詞條需要玩家逐次點擊。

- 工具強化每按一次 `🎲 強化工具` 只執行一次 `attempt_upgrade`。
- 自動抽取一次只填第一個空槽。多個空槽要用相同條件抽選時，玩家必須重複開啟設定畫面。
- 自動抽取設定畫面選「特定效果」時已用滿 Discord 5 個 ActionRow，無法再加選單。

## Recommended Direction

工具強化：

- 新增「選擇執行次數...」下拉選單（1 / 5 / 10 / 20 / 無限），放在強化模式選單下方、按鈕列上方。
- 按下 `🎲 強化工具` 後重複呼叫 `attempt_upgrade`，直到達到次數或前置條件不滿足（AP、素材、等級上限）。失敗不中斷。
- 無限 = 重複到前置條件不滿足。

自動抽取設定畫面改為 5 列：

```
row0 選擇目標效果...  (任意 / 行動效率 / 素材掉落 / 強化成功 / 素材退還 / 週期縮短)
row1 選擇目標數值...  (1+ ~ 5)
row2 選擇花費素材...  (工具素材 / 萬能素材)
row3 選擇抽取數量...  (僅一格 / 所有空格)
row4 [✅ 開始自動抽取] [← 返回詞條管理]
```

- 原「目標種類」與「目標效果」兩個選單合併為 row0。
- 所有空格：從第一個空槽開始，每格用相同條件呼叫一次 `auto_extract_affix`。某格素材耗盡仍未抽中時整批停止，該格與之後的空槽保持空的。

結果通知：

- 批次操作只發送一則 Public 訊息：標題一行，之後每次結果一行。
- 訊息超過 Discord 2000 字元上限時才拆成多則，每則在行邊界切開。
- 執行次數 1 與僅一格維持現有單行通知。

```
Dola 的 研究工具 鐵齒連續升級
成功 :tada: Lv220 -> Lv223（總失敗次數：0）
成功 :tada: Lv223 -> Lv225（總失敗次數：0）
...
```

替代方向：

- 自動抽取不動選單，在按鈕列加「抽滿所有空格」按鈕：使用者選擇合併選單並新增數量選單。不採用。
- manager 層新增批次函式，在一個交易內完成整批：失敗時整批回滾，玩家看不到已完成的結果，且長交易持有寫入鎖。不採用。

選擇 handler 迴圈呼叫既有單次 manager 函式的原因：每次嘗試沿用既有交易與驗證，manager 介面不變，中途停止時已完成的結果保留。

## Clarifications

- Q: 無限強化什麼時候停？ / A: 前置條件不滿足才停，失敗不中斷（鐵齒失敗歸零後也繼續）。
- Q: 自動抽取選單超過 5 列怎麼辦？ / A: row0 合併目標種類與目標效果，row3 新增抽取數量（僅一格 / 所有空格）。
- Q: 批次結果怎麼通知？ / A: 單一訊息，超過 Discord 長度上限才拆開。
- Q: Jira ticket？ / A: 沒有。

## MVP Scope / Not Doing

MVP Scope:

- 工具強化執行次數選單與批次執行。
- 自動抽取設定畫面合併效果選單、新增抽取數量選單、所有空格批次執行。
- 批次結果單一通知，超過長度上限才拆分。

Not Doing:

- 手動 `✨ 抽取詞條` 不加次數。
- 不新增 manager 層批次函式。
- 不記住玩家上次選的次數或數量。

## Key Assumptions

- 玩家 AP 上限讓無限強化的次數保持在單次互動可完成的範圍。
- 批次每行結果長度約 40 字元，一般批次不會超過 2000 字元。

## Architecture Decisions

- 批次在 handler 迴圈內執行。每次迭代開一個連線、呼叫既有單次 manager 函式並 commit。`gear_manager` 與 `affix_manager` 介面不變。
- 工具強化停止條件：達到次數，或 `attempt_upgrade` raise 任何例外（`ValueError` 為前置條件不滿足）。第一次就 raise 時沿用現有錯誤顯示，不發通知。至少一次已 commit 後 raise 時，保留已完成的結果並照常通知。
- 執行次數選單沿用強化模式選單的無預設選中慣例。模式或次數未選定時 `🎲 強化工具` 停用。
- 工具強化 custom_id：
  - `upgrade_mode_select:{gear_type}:{count}`
  - `upgrade_count_select:{gear_type}:{mode}`
  - `attempt_upgrade:{gear_type}:{mode}:{count}`
  - `{count}` 為 `1`、`5`、`10`、`20`、`inf` 或 `none`；`{mode}` 未選定時為 `none`。
- 自動抽取狀態欄位改為 `{gear}:{target}:{value}:{source}:{scope}`。`{target}` 為 `any`、詞條類型或 `none`；`{scope}` 為 `one`、`all` 或 `none`。
  - 選單 custom_id：`auto_affix_target:`、`auto_affix_value:`、`auto_affix_material:`、`auto_affix_scope:` 加上狀態欄位。
  - 確認 ID：`auto_affix_run:{gear}:{target}:{value}:{source}:{scope}:{expected_slot}:{token}`，仍為 8 段。最長約 76 字元。
  - 抽取數量選單沿用無預設選中慣例，未選定時確認按鈕停用。
- 所有空格迴圈：第一格使用確認 ID 的 `expected_slot`，之後每格重讀第一個空槽。沒有空槽、該格未抽中或 manager raise 時停止。第一格就 raise 時沿用現有錯誤畫面，不發通知。
- 通知：
  - 執行次數 1 發送既有 `gear_success`/`gear_fail`；其他次數發送一個 `gear_batch` 事件。
  - 僅一格發送既有 `affix_auto_extracted`；所有空格發送一個 `affix_auto_batch` 事件。
  - `dispatch_events` 對超過 2000 字元的文字依行切成多則，每則不超過 2000 字元。

## Tasks

依賴圖（Task 2、3 都改 `ui_renderer.py` 與 `actions.py`，依序執行）：

```
Task 1 (notification) -> Task 2 (gear count) -> Task 3 (auto affix scope)
```

- [ ] Task 1: 批次通知格式與長訊息拆分（`src/core/notification.py`；tests: `tests/test_discord_notifications.py`）
  - AC: `gear_batch` 輸出標題 `{user} 的 {gear_name} {標準|墊檔|鐵齒}連續升級`，之後每次結果一行，格式見 `docs/discord/notification.md`「工具連續強化」。
  - AC: `affix_auto_batch` 輸出標題 `{user} 的 {gear_name} 自動抽取所有空格`，之後每格一行，格式見「詞條自動抽取所有空格」。
  - AC: `dispatch_events` 遇到超過 2000 字元的文字時依行切成多則送出，每則不超過 2000 字元，行內容與順序不變；不超過時只送一則。
- [ ] Task 2: 工具強化執行次數（`src/cogs/ui_renderer.py`、`src/cogs/actions.py`；tests: `tests/test_discord_commands.py`、`tests/test_discord_notifications.py`）
  - AC: 工具強化子選單有 4 列：工具類型、強化模式、執行次數（1 / 5 / 10 / 20 / 無限，無預設選中）、按鈕列。custom_id 依 Architecture Decisions。
  - AC: 選模式保留次數、選次數保留模式。
  - AC: 次數 N 時最多呼叫 `attempt_upgrade` N 次；強化失敗不中斷；raise 任何例外時停止；`inf` 只在 raise 時停止。
  - AC: 次數 1 發送一個既有 `gear_success`/`gear_fail` 事件；其他次數且至少一次成功執行時發送一個 `gear_batch` 事件，包含每次結果。
  - AC: 子選單重繪時保留模式與次數。結果區顯示最後一次成功執行的結果；第一次就 raise 時顯示錯誤。
  - AC: 既有測試中舊格式 `attempt_upgrade:{gear}` 的 ID（`tests/test_discord_notifications.py` 582、614 行，`tests/test_discord_commands.py` 2734 行）改為 `attempt_upgrade:{gear}:{mode}:1`。
- [ ] Task 3: 自動抽取目標效果合併與所有空格（`src/cogs/ui_renderer.py`、`src/cogs/actions.py`；tests: `tests/test_discord_commands.py`）
  - AC: 自動抽取設定畫面固定 5 列：目標效果（任意 + 5 種效果）、目標數值、花費素材、抽取數量（僅一格 / 所有空格）、按鈕列。
  - AC: Embed 顯示目標效果與抽取數量，不再顯示目標種類。
  - AC: 確認 ID 為 8 段新格式，長度不超過 100；設定未完成（含抽取數量）時停用。
  - AC: 僅一格行為與現有自動抽取相同，發送既有 `affix_auto_extracted`。
  - AC: 所有空格依 Architecture Decisions 的迴圈逐格抽取，已完成的格子保留；發送一個 `affix_auto_batch` 事件，包含每格結果（含最後未抽中的那格）。

## Plan Review Issues

- [x] [Major] Task 2 的測試範圍漏了 `tests/test_discord_notifications.py`。
  - 該檔 582、614 行用舊的 `attempt_upgrade:gathering` 觸發 handler，並斷言 `dispatch.assert_called_once()`。
  - `tests/test_discord_commands.py:2734` 也用同一個舊 ID。
  - 新 handler 要求 `{mode}:{count}` 時，這些測試會提早 return 而失敗。
  - 修正：Task 2 的 tests 加入 `tests/test_discord_notifications.py`，三處改成 `attempt_upgrade:{gear}:{mode}:1`。
- [x] [Minor] 強化迴圈只處理 `ValueError`，其他例外會丟掉已提交的結果。
  - `src/cogs/actions.py:526-531` 只 catch `ValueError`；`attempt_upgrade` 遇到 DB 錯誤（例如 database is locked）會 raise 其他例外。
  - 情境：次數 20，第 7 次 raise `OperationalError`。前 6 次已 commit，但不發 `gear_batch`，也不重繪子選單。
  - 修正：至少一次已 commit 後，任何例外都停止迴圈並照常發送 `gear_batch`。這與自動抽取「manager raise 時停止」一致。
- [x] [Minor] Task 2 AC「結果區顯示最後一次結果」沒定義停止時的 `ValueError` 算不算結果。
  - `inf` 一定以 `ValueError` 結束。若顯示它，`build_gear_embed` 會在連續成功後顯示 `⚠️ 操作失敗：Insufficient AP`（`src/cogs/ui_renderer.py:629`）。
  - 修正：AC 改為「顯示最後一次成功執行的結果；第一次就 raise 時顯示錯誤」，並同步 `docs/discord/command-handler.md` 的 `attempt_upgrade` 列。
- [x] [Minor] `docs/discord/command-handler.md`「自動抽取確認」段落結尾仍寫「handler 提交成功後才 dispatch `affix_auto_extracted`」。
  - 所有空格發送的是 `affix_auto_batch`，同檔 `auto_affix_run` 列已這樣寫。
  - 修正：該句改為「handler 提交成功後才 dispatch 通知事件」，事件類型由路由表那一列說明。

## Review Issues

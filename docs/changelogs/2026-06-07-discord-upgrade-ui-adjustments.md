---
title: "Discord 強化介面 UI 調整"
status: Done
created: 2026-06-07
doc_type: change
last_reviewed: 2026-06-07
source_paths:
  - src/cogs/ui_renderer.py
  - src/cogs/actions.py
  - tests/test_discord_commands.py
scope: "調整強化工具介面的開啟條件、詞條清除流程與按鈕標籤格式。"
---

## Problem Statement

強化介面目前有三個 UX 問題：
1. AP 為 0 時按鈕禁用，玩家無法進入介面查看詞條或強化資訊
2. 清除詞條流程分散為多個「清除槽 N」按鈕，佔用 row 且操作直覺性差
3. 介面內各按鈕標籤長短不一（`🎲 強化`、`🩸 獻祭`），風格不統一

## Recommended Direction

A（採用）：直接調整 `ui_renderer.py` 與 `actions.py`，不引入新的狀態物件。

- 移除強化工具按鈕的 AP 禁用條件
- 把「清除槽 N」按鈕群改為單一「🗑️ 清除詞條」按鈕，點擊後重繪介面並加入 StringSelect 讓玩家選擇要清除的詞條
- 統一介面內四個操作按鈕格式為 `{icon}+四字`

B（排除）：用 Modal 彈窗替代 Dropdown 選單。Discord Modal 不支援 Select 元件，無法實現下拉式選詞條。

## Clarifications

Q: `清除詞條` 按鈕何時出現？僅在有詞條時？還是 max_slots > 0 就出現？
A: max_slots > 0 時出現，有詞條才 enabled，空詞條時 disabled。

Q: 選擇詞條的 dropdown 出現時，其他按鈕（強化、獻祭）是否維持可用？
A: 是，其他按鈕維持原本的 disabled 邏輯不變。

Q: 清除詞條的 dropdown 是出現在 Row 5，還是替代 Row 4 的按鈕 row？
A: Row 5，Row 4 的按鈕（抽取詞條、清除詞條）維持。

## MVP Scope / Not Doing

MVP 包含：
- 移除「強化工具」按鈕的 `ap < 1` 禁用條件
- 移除所有「清除槽 N」按鈕
- Row 4 加入「🗑️ 清除詞條」按鈕（與「✨ 抽取詞條」並排）
- 點擊「🗑️ 清除詞條」觸發 Row 5 出現 StringSelect（選項為現有詞條）
- 選擇後執行清除並重繪
- 統一按鈕標籤：`🎲 強化工具`、`🩸 獻祭素材`、`✨ 抽取詞條`、`🗑️ 清除詞條`

Not doing：
- 改變清除成本邏輯
- 清除後提示/通知格式

## Architecture Decisions

### 按鈕標籤變更

| 舊標籤 | 新標籤 |
| :--- | :--- |
| `🎲 強化` | `🎲 強化工具` |
| `🩸 獻祭` | `🩸 獻祭素材` |
| `✨ 抽取詞條` | `✨ 抽取詞條`（不變） |
| `清除槽 N`（多個） | `🗑️ 清除詞條`（單一） |

### 清除詞條流程

新增 `open_clear_affix:{gear_type}` button custom_id。`actions.py` handler 以 `show_clear_select=True` 重繪 gear 介面。`build_gear_components()` 新增 `show_clear_select: bool = False` 參數，當為 True 且有詞條時，在 Row 5 加入 StringSelect（`custom_id=clear_affix_select:{gear_type}`，選項為現有詞條）。

選中 `clear_affix_select` 後，handler 解析 slot_index 並呼叫既有 `affix_manager.clear_affix()`，然後正常重繪介面（不帶 show_clear_select）。

### 主介面按鈕禁用條件

`disabled=all_gear_at_cap`（移除 `ap < 1`）。

## Tasks

- [x] Task 1: 移除主介面「強化工具」按鈕的 `ap < 1` 禁用條件，更新測試
- [x] Task 2: 統一強化介面四個操作按鈕標籤格式，更新測試
- [x] Task 3: 移除「清除槽 N」按鈕群，改為單一「🗑️ 清除詞條」按鈕 + StringSelect 流程，更新測試

## Review Issues
- [x] [Major] `clear_affix_select:{gear_type}` dropdown handler references `user_id` without defining it in `on_dropdown`, so selecting an affix from the new StringSelect raises an unbound variable error before `affix_manager.clear_affix()` can run. Existing tests cover the old `clear_affix:{gear_type}:{slot}` button path and route registration, but not the new dropdown clear flow.

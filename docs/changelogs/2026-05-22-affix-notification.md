---
title: "詞條抽取/清除公告"
status: Ready-to-implement
created: 2026-05-22
doc_type: change
last_reviewed: 2026-05-22
source_paths:
  - src/core/notification.py
  - src/managers/affix_manager.py
  - src/cogs/actions.py
  - docs/discord/notification.md
---

## Problem Statement

玩家抽取或清除詞條時，公告頻道不會發送任何訊息，其他玩家無法得知詞條操作結果。此功能在 `2026-05-21-tool-affixes.md` 中明確列為 Not Doing，現補實作。

## Recommended Direction

方向 A（選用）：在現有 notification 事件系統新增兩個事件類型 `affix_extracted` 和 `affix_cleared`，由 `actions.py` 的 handler 觸發，透過 `notification.dispatch_events()` 發送公告訊息。

選用原因：與現有 gear upgrade 通知的觸發模式完全一致（handler → events → dispatch），無需新增通路，改動集中在兩個檔案。

方向 B（排除）：在 `affix_manager.py` 內部直接送通知。排除原因：manager 層不應持有 Discord bot 參照，違反現有架構分層（manager 無 I/O 副作用）。

方向 C（排除）：用 Ephemeral 訊息回傳詞條結果而非 Public 公告。排除原因：使用者明確要求 Public 公告，且與其他強化類事件的公告一致性原則相符。

## Spec

### 新增事件

| 事件 | 觸發時機 | 訊息內容 | 公開/私人 |
| :--- | :--- | :--- | :--- |
| 詞條抽取 | `extract_affix` handler 成功後 | `{user_display_name} 的 {gear_name} 抽到詞條：{affix_label}（+{value}%）` | Public |
| 詞條清除 | `clear_affix` handler 成功後 | `{user_display_name} 的 {gear_name} 清除詞條：{affix_label}（+{value}%）` | Public |

### 工具名稱對照

與現有工具強化通知一致：採集工具、建設工具、狩獵工具、研究工具。

### 詞條類型標籤

| affix_type | 顯示標籤 |
| :--- | :--- |
| `efficiency` | 行動效率 |
| `material_drop` | 素材掉落率 |
| `upgrade_success` | 強化成功率 |
| `upgrade_cost_reduce` | 強化素材消耗 |
| `upgrade_ap_refund` | 強化 AP 退還 |
| `upgrade_material_refund` | 強化素材退還 |
| `cycle_time_reduce` | 行動週期縮短 |

### 訊息範本

```
{user_display_name} 的 {gear_name} 抽到詞條：{affix_label}（+{value}%）
{user_display_name} 的 {gear_name} 清除詞條：{affix_label}（+{value}%）
```

## Tasks

- [ ] Task 1: `notification.py` — 在 `_format_event` 新增 `affix_extracted` 與 `affix_cleared` 兩個 kind 分支，加入 `AFFIX_TYPE_LABELS` 對照表（7 種詞條的中文標籤）；更新 `docs/discord/notification.md`：在 `## 訊息範本` 新增 `### 詞條抽取` 與 `### 詞條清除` 小節，在 `## 通知去重` 補上「詞條抽取/清除通知只在操作瞬間發送，不需持久去重」
- [ ] Task 2: `affix_manager.py` + `actions.py` — 修改 `clear_affix`：將現有的 `any(a["slot_index"] == slot_index for a in existing)` 改為 `target = next((a for a in existing if a["slot_index"] == slot_index), None)`，以 `target is None` 做存在檢查，DELETE 後 `return {"affix_type": target["affix_type"], "value": target["value"]}`（回傳型別 `-> dict`）；`extract_affix` handler 改為 `result = await affix_manager.extract_affix(...)`，`clear_affix` handler 改為 `result = await affix_manager.clear_affix(...)`；兩個 handler 成功後各建立事件 dict（`type`=`"affix_extracted"` 或 `"affix_cleared"`，`user_display_name`=`inter.author.display_name`，`gear_type`，`affix_type`=`result["affix_type"]`，`value`=`result["value"]`）並呼叫 `await notification.dispatch_events(self.bot, [event])`；更新 `tests/test_discord_commands.py`（驗證 extract/clear 成功後觸發 dispatch_events）

## Key Assumptions

- `extract_affix` 已回傳 `{"slot_index", "affix_type", "value"}`，可直接用於事件內容，無需額外查 DB。
- `clear_affix` 目前回傳 `None`，需改為回傳 `{"affix_type", "value"}`；`existing` list 在函式內已可取得，在 DELETE 前取出目標 dict 即可。
- `GEAR_LABELS` 已在 `notification.py` 透過 `from cogs.ui_renderer import GEAR_LABELS` 引入，`_format_event` 內直接使用 `GEAR_LABELS.get(gear_type, gear_type)` 轉換工具名稱（與現有 gear 事件一致）。
- `user_display_name` 由 handler 傳入（`inter.author.display_name`），與現有 gear upgrade 通知的做法相同。
- 詞條公告無需去重（與 gear upgrade 通知相同，只在操作瞬間發送）。
- `docs/discord/notification.md` 事件清單已有詞條兩列（已在工作目錄修改，未 commit），Task 1 只需補訊息範本小節。

## Review Issues

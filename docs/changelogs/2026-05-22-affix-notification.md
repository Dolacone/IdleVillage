---
title: "詞條抽取/清除公告"
status: Draft
created: 2026-05-22
doc_type: change
last_reviewed: 2026-05-22
source_paths:
  - src/core/notification.py
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

- [ ] Task 1: `notification.py` 新增 `affix_extracted`/`affix_cleared` 事件處理，含工具名稱與詞條標籤對照表；更新 `docs/discord/notification.md`
- [ ] Task 2: `actions.py` 的 `extract_affix` 與 `clear_affix` handler 在成功後建立並 dispatch 對應事件；更新 `tests/test_discord_commands.py`

## Key Assumptions

- 詞條清除時，需在 DB commit 前先讀取即將被清除的詞條值（type + value），才能放入事件內容。
- `affix_manager.extract_affix` 目前不回傳抽到的詞條內容；需確認是否需要修改其簽名或改為查 DB。

## Review Issues

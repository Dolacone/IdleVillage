---
title: "取消一般關卡通關通知，只保留升級關通關通知"
status: Refactored
created: 2026-11-05
doc_type: change
last_reviewed: 2026-11-05
source_paths:
  - docs/README.md
  - docs/changelogs/2026-11-05-remove-stage-clear-notification.md
  - docs/discord/notification.md
  - docs/managers/stage-manager.md
  - src/core/notification.py
  - src/core/settlement.py
  - tests/test_discord_notifications.py
scope: "Tracks this change from design through review."
---

## Problem Statement

每次關卡通關，Bot 都在通知頻道發送一則「通過第 X 關」Public 訊息。

- 第 1-4 關的通關訊息頻繁出現，洗掉頻道內其他通知。
- 第 5 關（升級關）通關時會發兩則訊息：一般「通過第 X 關」與「升級關通關」。
  - 升級關訊息已含「下一目標」與「目標需求」，一般通關訊息重複。

## Recommended Direction

所有關卡都不再發送一般關卡通關通知。升級關通關時只發送「升級關通關」訊息，範本不變。

```
第 1-4 關通關：（無訊息）

第 5 關通關：
升級關通關，第 {round} 輪完成
建築等級上限從 Lv{old_cap} 變成 Lv{new_cap}
下一目標：{next_stage_name}
目標需求：{next_target}
```

- 關卡逾時、建築升級、工具、詞條、試煉通知不變。
- 通關判定、`stages_cleared` 累加、建築等級上限提升邏輯不變。
- Dashboard 仍每輪結算後更新關卡進度。

### Alternatives

| 方向 | 結果 |
| :--- | :--- |
| A：移除一般通關通知（選定） | 第 5 關只發一則升級關訊息 |
| B：只移除第 1-4 關通知 | 第 5 關仍發兩則訊息 |
| C：第 5 關合併兩則為新範本 | 需新範本 |

- 選 A：使用者確認第 5 關只發升級關訊息。
- 排除 B：第 5 關的一般通關訊息與升級關訊息重複。
- 排除 C：升級關範本已含下一目標資訊，結果與 A 相同但要多改範本。

## Key Assumptions

- 玩家可從 Dashboard 得知第 1-4 關進度與切換，不需要 Public 通知。
- 升級關通關訊息足以讓玩家得知每輪完成。

## Clarifications

<!-- Q: 取消小關卡訊息後，第 5 關要發幾則？ / A: 只發升級關訊息，不發一般「通過第 X 關」。 — resolved during idea stage -->

## MVP Scope / Not Doing

MVP Scope:

- 停止發送一般關卡通關通知。
- 升級關通關時發送升級關通知，範本不變。

Not Doing:

- 不改升級關訊息範本。
- 不改關卡逾時通知。
- 不改 Dashboard。

## Architecture Decisions

- 在事件來源移除 `stage_clear`：`src/core/settlement.py` 不再 append `stage_clear` 事件。
  - `stage_clear` 只有 `src/core/notification.py` 的 `_format_event` 消費。
  - `upgrade_stage_clear` 已帶 `next_stage_type` 與 `next_target`，不依賴 `stage_clear`。
- 刪除 `_format_event` 的 `stage_clear` 分支，不留無來源的範本。
- 升級關通關判定 `new_stages_cleared % 5 == 0`、`stage_post` 讀取、建築升級檢查維持原位。

## Tasks

Dependency graph:

```
Task 1 (settlement.py + notification.py + tests)
```

- [x] Task 1: Stop emitting and formatting `stage_clear`
  - Files: `src/core/settlement.py`, `src/core/notification.py`, `tests/test_discord_notifications.py`.
  - Parallel: none.
  - Acceptance criteria:
    - Clearing stage 1-4 (`stages_cleared` not a multiple of 5) returns no `stage_clear` event and no `upgrade_stage_clear` event.
    - Clearing the upgrade stage (`stages_cleared` becomes 5) returns exactly one stage-related event, `upgrade_stage_clear`, with `round`, `old_cap`, `new_cap`, `next_stage_type`, `next_target`; building upgrade events still follow.
    - `_format_event` has no `stage_clear` branch; `upgrade_stage_clear` text is unchanged.
    - `TestActionChangeNotificationDispatch.test_confirm_action_dispatches_overdue_catchup_events` asserts dispatch of catch-up events with a marker other than `stage_clear` (for example `upgrade_stage_clear` with `stages_cleared=4`).
    - `uv run python -m pytest` passes.

## Review Issues

- None.

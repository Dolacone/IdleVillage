---
title: "取消建築升級通知"
status: Draft
created: 2026-11-05
doc_type: change
last_reviewed: 2026-11-05
source_paths: []
scope: "Tracks this change from design through review."
---

## Problem Statement

每次建築升級，Bot 都在通知頻道發送一則「{建築名稱} 從 Lv{old_level} 變成 Lv{new_level}」Public 訊息。

- 建築一次升多級時，每個等級各發一則。
- 升級關通關提升等級上限後，所有建築可連帶升級，一次洗出多則訊息。
- Dashboard 已顯示每座建築的等級與 XP 進度。

## Recommended Direction

所有建築升級都不再發送 Discord 通知。

```
建築升級（任何來源）：（無訊息）

升級關通關：
升級關通關，第 {round} 輪完成
建築等級上限從 Lv{old_cap} 變成 Lv{new_cap}
下一目標：{next_stage_name}
目標需求：{next_target}
```

- 建築升級判定、逐級升級、XP 上限邏輯不變。
- 升級關通關、關卡逾時、工具、詞條、試煉通知不變。
- Dashboard 仍每輪結算後更新建築等級。

### Alternatives

| 方向 | 結果 |
| :--- | :--- |
| A：移除所有建築升級通知（選定） | 不發任何建築升級訊息 |
| B：只移除升級關連帶升級的通知 | 一般 XP 升級仍發訊息 |
| C：多級升級合併為一則 | 需新範本，訊息仍存在 |

- 選 A：使用者確認所有建築升級都停發。
- 排除 B：使用者要求全部停發。
- 排除 C：仍發訊息，不符需求。

## Key Assumptions

- 玩家可從 Dashboard 得知建築等級，不需要 Public 通知。

## Clarifications

<!-- Q: 哪些建築升級要停發？ / A: 全部，包含升級關連帶升級與自動工具結算觸發的升級。 — resolved during idea stage -->

## MVP Scope / Not Doing

MVP Scope:

- 停止發送建築升級通知。

Not Doing:

- 不改建築升級邏輯。
- 不改升級關通關訊息範本。
- 不改 Dashboard。

## Architecture Decisions

## Tasks

## Review Issues

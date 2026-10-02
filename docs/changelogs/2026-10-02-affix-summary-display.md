---
title: "詞條合計顯示與四字名稱"
status: Draft
created: 2026-10-02
doc_type: change
last_reviewed: 2026-10-02
source_paths: []
scope: "Tracks the affix summary display and four-character affix labels from design through review."
---

## Problem Statement

工具強化頁面逐槽列出全部詞條。槽位多時（例如 22 槽）畫面很長，玩家看不出每種效果的總加成。詞條管理頁面也沒有合計資訊。詞條名稱長度不一（2 到 6 字），介面與 Public 通知使用兩份不一致的名稱對照表。

## Recommended Direction

- 工具強化頁面：`詞條槽（已用/總槽）` 標題保留，下方改為每種詞條類型一行合計，格式 `{label}: {total}%`。
- 詞條管理頁面：持有素材列與分隔線之間新增 `詞條合計` 區塊，格式同上；分隔線下方逐槽清單保留。
- 七種詞條統一為四字名稱，介面與通知共用同一份對照表。
- 所有詞條數值一律顯示為正數，包含 `素材減免`。

Alternatives considered:

- 合計只放詞條管理頁面，工具強化頁面保留逐槽清單：被排除，因為使用者要求工具強化頁面改為合計。
- 兩份名稱對照表分別改為四字但保留兩份：被排除，因為兩份已出現不一致，合併為一份可避免再次分歧。
- 選定方向：兩頁共用一個合計渲染函式與一份名稱對照表，改動集中在 renderer 與 notification。

## Clarifications

- Q: `upgrade_ap_refund` 的名稱？ / A: `ＡＰ退還`，使用全形 `ＡＰ` 以便排列對齊。
- Q: `upgrade_cost_reduce` 的名稱？ / A: `素材減免`。
- Q: Public 通知是否一起改為四字名稱？ / A: 是，介面與通知共用一份對照表。
- Q: 數值正負號？ / A: 全部使用正數，包含 `素材減免`；適用於合計、逐槽清單、槽位下拉描述與通知。
- Q: 合計列出哪些類型？ / A: 只列合計大於 0 的類型，依固定順序排列；有槽位但無詞條時顯示 `（尚無詞條）`；未解鎖詞條槽時維持現有顯示。

名稱對照：

| 代碼 | 名稱 |
| :--- | :--- |
| `efficiency` | 行動效率 |
| `material_drop` | 素材掉落 |
| `upgrade_success` | 強化成功 |
| `upgrade_cost_reduce` | 素材減免 |
| `upgrade_ap_refund` | ＡＰ退還 |
| `upgrade_material_refund` | 素材退還 |
| `cycle_time_reduce` | 週期縮短 |

合計排序依上表由上到下。

## Key Assumptions

- 玩家主要關心每種效果的總加成，不需要在工具強化頁面看到逐槽明細。
- 全形 `ＡＰ` 在 Discord 桌面與手機用戶端都與其他四字名稱等寬。
- 移除 `-` 號不會讓玩家誤解 `素材減免` 的效果方向，因為名稱本身表達減少。

## MVP Scope / Not Doing

MVP:

- 工具強化頁面詞條合計。
- 詞條管理頁面詞條合計區塊。
- 七種詞條四字名稱，介面與通知共用。
- 數值一律正數。

Not doing:

- 不改變詞條效果、抽取、清除或自動抽取規則。
- 不改變槽位計算與 custom_id。
- 不改變 `/idlevillage-manager` 管理員介面。

## Architecture Decisions

## Tasks

## Review Issues

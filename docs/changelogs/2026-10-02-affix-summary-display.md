---
title: "詞條合計顯示與四字名稱"
status: Issues-confirmed
created: 2026-10-02
doc_type: change
last_reviewed: 2026-10-02
source_paths:
  - src/cogs/ui_renderer.py
  - src/core/notification.py
  - tests/test_discord_commands.py
  - tests/test_discord_notifications.py
  - docs/discord/ui-renderer.md
  - docs/discord/notification.md
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

- `src/cogs/ui_renderer.py` 的 `AFFIX_TYPE_LABELS` 是唯一的名稱對照表，dict 順序即合計排序。`src/core/notification.py` 已從 `cogs.ui_renderer` 匯入常數，改為匯入同一份 `AFFIX_TYPE_LABELS`，並刪除本地的 `AFFIX_TYPE_LABELS` 與 `REDUCE_AFFIX_TYPES`。
- 數值一律正數後 `REDUCE_AFFIX_TYPES` 沒有用途，兩個模組都刪除。
- renderer 新增一個合計函式，回傳合計行清單；工具強化子選單與詞條管理畫面共用。逐槽清單沿用現有 `_build_affix_section` 的逐槽邏輯，只供詞條管理畫面使用。
- 不改 custom_id、manager 介面或資料表。

## Tasks

依賴關係：

```
Task 1 (ui_renderer.py) ──> Task 2 (notification.py)
```

Task 2 匯入 Task 1 的對照表，必須依序執行，不可平行。

- [x] Task 1: renderer 詞條名稱、正數與合計顯示
  - Files: `src/cogs/ui_renderer.py`, `tests/test_discord_commands.py`
  - AC1: `AFFIX_TYPE_LABELS` 依 Clarifications 對照表順序包含七種四字名稱；`REDUCE_AFFIX_TYPES` 已刪除。
  - AC2: 工具強化子選單 `max_slots > 0` 時顯示分隔線、`詞條槽（{used}/{max_slots}）` 與合計行，不顯示 `槽 {n}:` 逐槽行；`max_slots == 0` 時不顯示詞條區塊。
  - AC3: 合計行格式 `{label}: {total}%`，同類型數值相加，只列總和大於 0 的類型，依對照表順序；有槽位但無詞條時顯示 `（尚無詞條）`。
  - AC4: 詞條管理畫面在持有素材列之後、分隔線之前顯示空行、`詞條合計` 與合計行；分隔線後的逐槽清單保留。
  - AC5: 逐槽清單、槽位下拉描述與即將清除提示一律為 `+{value}%`，`upgrade_cost_reduce` 也不顯示 `-`。
  - AC6: 自動抽取效果選單選項使用新名稱。
  - Tests: 只更新 `tests/test_discord_commands.py` 中 renderer 輸出的詞條斷言，保留通知文字斷言（`tests/test_discord_commands.py:1667`）；Task 1 完成時通知仍使用舊名稱，完整測試必須通過；新增合計加總、排序、排除 0、`（尚無詞條）`、兩畫面版面與 `素材減免` 正數的測試。
- [x] Task 2: 通知共用名稱對照表與正數
  - Files: `src/core/notification.py`, `tests/test_discord_notifications.py`, `tests/test_discord_commands.py`
  - AC1: `notification.py` 從 `cogs.ui_renderer` 匯入 `AFFIX_TYPE_LABELS`，本地對照表與 `REDUCE_AFFIX_TYPES` 已刪除。
  - AC2: 詞條抽取、清除與自動抽取通知使用四字名稱，數值一律為 `+{value}%`，例如 `清除詞條：素材減免（+3%）`。
  - Tests: 更新 `tests/test_discord_notifications.py` 與 `tests/test_discord_commands.py` 中依賴舊通知名稱的斷言。反轉 `tests/test_discord_notifications.py:998`、`:999`、`:1012`、`:1013` 的負號斷言為正號，並同步更新測試名稱與 :985 的說明。抽取、清除與自動抽取通知都要驗證新名稱與正號。
- [x] Task 3: 執行完整測試
  - AC: `uv run python -m pytest` 全部通過。

## Plan Review Issues

- [x] P1: Task 2 實際涉及三個邏輯檔案，超過每項任務兩檔上限。證據：本文件:104 列出 `src/core/notification.py` 與 `tests/test_discord_notifications.py`；本文件:107 又要求修改 `tests/test_discord_commands.py`。後者:1667 斷言通知使用 `行動週期縮短`。`src/core/notification.py:210` 決定該通知名稱。Task 2 共用新對照表後，該斷言必須同步改為 `週期縮短`。必須重新拆分任務並列出完整檔案範圍。Task 1 必須明訂只更新 renderer 的斷言，保留 :1667 的通知斷言。若 Task 1 提前更新該斷言，尚未修改的 notification 仍回傳舊名稱。Task 1 單獨通過測試的條件必須寫入計畫。此為任務分界問題，無需新增重現測試；尚未執行實作後測試。
  - Resolution: 測試檔不計入兩檔上限，Task 2 只有一個邏輯檔。Task 2 Files 補列 `tests/test_discord_commands.py`；Task 1 Tests 明訂保留 :1667 通知斷言，且 Task 1 完成時完整測試必須通過。
- [x] P2: Task 2 漏列通知正負號測試更新。證據：`docs/changelogs/2026-10-02-affix-summary-display.md:107` 的 Tests 僅列舊通知名稱斷言。`tests/test_discord_notifications.py:998` 與 `tests/test_discord_notifications.py:1012` 要求負號。`tests/test_discord_notifications.py:999` 與 `tests/test_discord_notifications.py:1013` 排除正號。這四個斷言不依賴詞條名稱。它們與本文件:106 的正數 AC 衝突。Task 2 必須明列反轉這四個斷言。測試名稱與 `tests/test_discord_notifications.py:985` 的說明必須同步改為正數。抽取、清除與自動抽取均須驗證新名稱與正號。此為測試計畫缺漏，無需新增重現測試。尚未執行實作後測試。
  - Resolution: Task 2 Tests 明列反轉四個負號斷言、更新測試名稱與說明，並涵蓋三種通知的新名稱與正號。

## Review Issues

- [x] [Major] R1: 詞條管理畫面缺少空詞條合計的測試斷言。`docs/changelogs/2026-10-02-affix-summary-display.md:98-99` 要求合計與 `（尚無詞條）`。`tests/test_discord_commands.py:1341-1357` 只驗證已有詞條的管理畫面。`tests/test_discord_commands.py:1482-1485` 傳入空詞條，但只斷言持有素材。`tests/test_discord_commands.py:1304-1309` 的空詞條斷言只涵蓋工具強化畫面。`src/cogs/ui_renderer.py:741-744` 是管理畫面的合計入口。若入口錯誤地排除空詞條，現有測試不會失敗。必須新增選定工具、已解鎖槽位、`affixes=[]` 的管理畫面測試。必須斷言合計標題、`（尚無詞條）` 與保留的空槽清單。此為測試缺漏，現行實作符合空詞條規格。無需新增實作錯誤的失敗重現測試。覆蓋率驗證使用記憶體中的錯誤變體，不修改儲存庫程式碼。基準命令：`UV_CACHE_DIR=/private/tmp/idlevillage-review-uv-cache uv run python /private/tmp/affix-summary-coverage-probe.py`。變體命令只增加 `--mutated`。變體把該入口改成 `if affix_section and affixes:`。基準輸出：`Original empty management summary: present`。變體輸出：`Mutated empty management summary: absent`。兩次測試輸出均為 `655 passed, 24 subtests passed in 12.13s`。
- [ ] [Minor] R2: 新變更文件缺少導覽連結。`docs/changelogs/2026-10-02-affix-summary-display.md:1-14` 建立此變更文件。`docs/README.md:35-41` 未連結此文件。修改的 `docs/discord/ui-renderer.md:358` 與 `docs/discord/notification.md:160` 也未連結此文件。`AGENTS.md:29` 要求所有文件能從文件入口到達。搜尋此檔名只命中變更文件本身。必須從文件入口或其連結的文件加入導覽連結。此為文件導覽問題，無需重現測試。

原始分支全套測試：`UV_CACHE_DIR=/private/tmp/idlevillage-review-uv-cache uv run python -m pytest -q`。結果：`655 passed, 24 subtests passed in 10.30s`。

獨立 CLI 審查未完成。受限環境無法啟動 `codex exec review`。`copilot` 缺少驗證資訊。自動核准拒絕外部 Codex 審查。拒絕原因為未授權將私有程式碼與文件傳至該服務。

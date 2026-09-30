---
title: "詞條自動抽取"
status: Ready-to-review
created: 2026-09-30
doc_type: change
last_reviewed: 2026-09-30
source_paths:
  - src/managers/affix_manager.py
  - src/cogs/ui_renderer.py
  - src/cogs/actions.py
  - src/core/notification.py
  - tests/test_affix_manager.py
  - tests/test_discord_commands.py
  - tests/test_discord_notifications.py
  - docs/managers/affix-manager.md
  - docs/managers/player-manager.md
  - docs/discord/ui-renderer.md
  - docs/discord/command-handler.md
  - docs/discord/notification.md
  - docs/README.md
scope: "Tracks automatic affix extraction from design through review."
---

## Problem Statement

玩家需要重複抽取與清除才能取得目標詞條。每次抽選也會產生公告。

## Recommended Direction

方向 A: 在詞條管理新增「自動抽取」。設定效果、最低數值與素材來源後執行一次批次。只保存符合目標的詞條。只發送一則總結。採用此方向以滿足使用者確認的規則。

方向 B: 逐次抽取後自動清除。排除此方向。清除會產生額外成本與公告。

方向 C: 背景排程持續抽取。排除此方向。本功能只需要一次操作的批次結果。

## Clarifications

- 入口: 新增「自動抽取」按鈕。原「抽取詞條」維持單抽。
- 成本: 自動抽取每次消耗 1 工具素材或 5 萬能素材。只扣玩家選定的來源。素材不足以支付下一次時停止。
- 單抽: 保留工具素材優先、萬能素材 1:1 補足差額的規則。
- 目標種類: 任意或指定現有七種效果之一。指定效果與最低數值必須同時符合。
- 目標數值: 1+、2+、3+、4+、5。門檻代表百分比的絕對數值。
- 槽位: 只針對第一個空槽。滿槽時無法使用。成功保存一條後停止。
- 未達標: 扣除本次成本後丟棄結果。不清除既有詞條。不支付清除成本。
- 耗盡: 未抽到目標時保持空槽。剩餘不足 5 的萬能素材保留。
- 公告: 只送一則成功或未達標總結。列出總抽選次數與實際花費。
- 成功範例: `<player name> 的 研究工具 抽到詞條：行動週期縮短（+4%），抽選次數50 (250萬能素材)`。
- 耗盡範例: `<player name> 的 研究工具 未抽到目標詞條，抽選次數50 (250萬能素材)`。

## MVP Scope / Not Doing

- 範圍: 詞條管理入口、設定介面、自動抽取、單則公告與驗證。
- 不含: 背景排程、取消按鈕、抽選上限、機率調整、覆蓋既有詞條。

## Architecture Decisions

沿用 manager、互動 handler、renderer 與 notification 的分層。抽選規則由 affix-manager 擁有。

- Manager: 新增 `auto_extract_affix(db, user_id, gear_type, gear_level, now, *, target_affix_type=None, min_value=1, material_source="tool", expected_slot=None)`。回傳 `{affix, attempts, material_spent, material_source}`。`affix` 為單抽同型 dict 或 `None`。
- 成本: 固定工具素材 1、萬能素材 5。保留單抽與清除的成本設定。只保存最終符合條件的結果。
- 抽選: 使用既有 `random.choice(AFFIX_TYPES)` 與 `random.randint(1, 5)`。每 100 次讓出事件迴圈。
- 交易: manager 在讀取起始素材後抽選，不持有寫入鎖。抽選完成後以 `BEGIN IMMEDIATE` 重讀工具等級、槽位與素材。依最新餘額縮減可扣次數。成功結果超過可扣次數時丟棄。總成本只扣一次。handler 提交或回滾。
- 並行: 本批次只使用開始時持有的素材。抽選期間新增的素材保留。抽選期間素材減少時縮減次數。最新槽位全滿時拒絕且不扣款。
- 目標槽: 設定頁將第一空槽寫入確認 ID。manager 在抽選前與交易內檢查目標槽。目標槽改變時拒絕確認，不移至下一個空槽。
- 一次性確認: renderer 接收每次渲染產生的 8 字元 URL-safe token。確認 ID 格式為 `auto_affix_run:{gear}:{mode}:{effect}:{value}:{source}:{expected_slot}:{token}`。handler 依玩家只保留目前介面的完整 ID，並在首次 await 前消耗。已消耗、過期、跨玩家或遭改寫的確認不扣款、不公告。
- 介面: 「目標種類」選任意或特定效果。選特定效果後顯示七種效果選單。另有「目標數值」與「花費素材」。設定未齊時停用確認。
- 介面狀態: 沿用 custom_id 帶選擇值的慣例。四個選單與按鈕共用最多五列。每個 custom_id 必須不超過 100 字元。
- 提交: handler 延後回應，再提交批次。重新檢查滿槽與素材。起始素材不足時顯示錯誤，不送零次公告。
- 公告: 新增 `affix_auto_extracted`。成功沿用詞條名稱與正負號。未達標使用確認的文案。只發送一則事件。
- 文件: 在程式存在後更新模組文件。同一主題維持 canonical 文件。變更紀錄放在 `docs/changelogs/`。
- 驗證: 使用已安裝的 Python 3.11.14、disnake 2.12.0、aiosqlite 0.22.1。以 unittest 執行既有測試。測試資料庫使用既有 `DatabaseTestCase`。
- 整合驗證: 從真實互動 handler 執行設定、確認、manager、SQLite、renderer 與 notification。外部 Discord 傳輸使用 mock。Discord 實際點擊與發送標記為未驗證。

```text
Task 1 (manager) + Task 2 (UI/events) --> Task 3 (handler/integration) --> Review --> approved --> refactor --> draft PR
                                                                           |  ^
                                                                           v  |
                                                                          Fixes
```

## Tasks

- [x] Task 1: 自動抽取 manager。[可與 Task 2 平行]
  - Source: `src/managers/affix_manager.py`。
  - Tests: `tests/test_affix_manager.py`。
  - Acceptance: 任意效果與特定效果均與最低數值共同判斷。失敗結果不入庫。成功只填第一空槽。滿槽與無槽拒絕。
  - Acceptance: 工具素材耗盡不扣萬能素材。萬能素材每次扣 5，不扣工具素材。餘數保留。次數與花費包含成功那次。
  - Acceptance: 未達標保持空槽。既有詞條不變。所有無效參數與起始素材不足不扣款。單抽補足測試維持通過。
  - Evidence: `UV_CACHE_DIR=/private/tmp/idlevillage-uv-cache uv run --no-project python -m unittest tests.test_affix_manager -q` — 44 tests, OK.
- [x] Task 2: 設定介面與批次公告。[可與 Task 1 平行]
  - Source: `src/cogs/ui_renderer.py`、`src/core/notification.py`。
  - Tests: `tests/test_discord_commands.py`、`tests/test_discord_notifications.py`。
  - Acceptance: 新增自動抽取入口。無工具、無槽或滿槽停用。設定頁列出任意與特定效果、七種效果、五個數值門檻與兩種素材。
  - Acceptance: 未選齊、滿槽或所選素材不足時確認停用。所有選項狀態保留。所有組合最多五列。ID 不超過 100 字元。
  - Acceptance: 公告成功與耗盡均只有一條文案。研究工具週期縮短 4%、50 次、250 萬能素材符合使用者範例。素材成本降低顯示負號。
- [x] Task 3: 互動路由、整合驗證與模組文件。
  - Source: `src/cogs/actions.py`。
  - Tests: `tests/test_discord_commands.py`。
  - Docs: `docs/managers/affix-manager.md`、`docs/managers/player-manager.md`、`docs/discord/ui-renderer.md`、`docs/discord/command-handler.md`、`docs/discord/notification.md`、`docs/README.md`。
  - Acceptance: 真實路由從設定頁到確認執行。切換任意或特定效果時保留其餘設定。操作前先 defer。使用者與 guild 沿用既有判斷。
  - Acceptance: 重讀狀態並在交易內完成扣款與填槽。成功或耗盡後只 dispatch 一則公告。非法、缺值、過期滿槽與素材不足均不扣款、不公告。
  - Acceptance: 真實 manager 與 SQLite 驗證兩種素材、AND 判斷、首次成功停止、第一空槽、耗盡保持空槽。既有單抽維持原規則。
  - Acceptance: 扣款後或提交前發生錯誤時回滾素材與詞條，不送公告。兩個並行確認只能填一個空槽。第二次確認不得扣款。
  - Acceptance: 大量未達標抽選期間，其他 SQLite 連線可以寫入。扣款次數固定為一次。抽選期間新增與減少素材均符合批次規則。
  - Evidence: `UV_CACHE_DIR=/private/tmp/idlevillage-uv-cache uv run --no-project python -m unittest discover -s tests -q` — `Ran 637 tests in 7.929s`; `OK`. Handler integration uses real SQLite, manager, renderer and notification formatting with mocked Discord transport. Live Discord interaction remains unverified.
  - Acceptance: 更新文件及 `last_reviewed`。更新 `source_paths` 為實際建立或檢查的路徑。完整測試套件通過。
- [x] Task 4: manager 固定本次目標槽。[Review/Major 的第一步]
  - Source: `src/managers/affix_manager.py`。
  - Tests: `tests/test_affix_manager.py`。
  - Acceptance: 新增 `expected_slot`。參數無效或不符第一空槽時拒絕且不扣款。抽選完成後第一空槽改變時拒絕。
  - Acceptance: 抽選期間原目標槽被填入時不轉抽其他槽。保留原有素材、回滾及分布規則。
  - Evidence: `UV_CACHE_DIR=/private/tmp/idlevillage-uv-cache uv run --no-project python -m unittest tests.test_affix_manager -q` — `Ran 48 tests in 0.867s`; `OK`.
- [x] Task 5: 確認 ID 綁定目標槽。[依賴 Task 4]
  - Source: `src/cogs/ui_renderer.py`、`src/cogs/actions.py`。
  - Tests: `tests/test_discord_commands.py`。
  - Docs: `docs/discord/command-handler.md`、`docs/discord/ui-renderer.md`、`docs/managers/affix-manager.md`。
  - Acceptance: 確認 ID 附帶設定頁第一空槽。handler 驗證並傳入 `expected_slot`。完整 ID 仍不超過 100 字元。
  - Acceptance: 同一確認在兩個空槽上並行時只扣一次、填一槽、發一則公告。完成後再次提交同一確認不得扣款。
  - Acceptance: 重新開啟設定頁可對下一個空槽正常抽取。所有既有確認測試配合新 ID。完整測試套件通過。
- [x] Task 6: 一次性確認與目標種類切換驗證。[Review/Major]
  - Source: `src/cogs/actions.py`、`src/cogs/ui_renderer.py`。
  - Tests: `tests/test_discord_commands.py`。
  - Docs: `docs/discord/command-handler.md`、`docs/discord/ui-renderer.md`。
  - Acceptance: handler 產生 token 並註冊渲染後的完整 ID。確認必須符合玩家目前 ID。首次 await 前消耗 ID。
  - Acceptance: 成功後即使原槽被清除，同一 ID 也不得再次扣款或公告。耗盡後新增素材仍不得重送同一 ID。
  - Acceptance: 重新開啟設定頁取得新確認，可正常使用原空槽。舊介面與其他玩家的確認不得消耗素材。
  - Acceptance: 特定效果 -> 任意 -> 特定效果保留效果、門檻與素材來源。從真實渲染 ID 執行切換。
  - Acceptance: 所有 ID 不超過 100 字元。現有整合測試必須從真實 handler 渲染取得有效確認，不手動注入 registry。
  - Evidence: `UV_CACHE_DIR=/private/tmp/idlevillage-uv-cache uv run --no-project python -m unittest discover -s tests -q` — `Ran 646 tests in 8.794s`; `OK`. Full runner output: `/private/tmp/idlevillage-task6.log`. `test_confirmation_replay_after_clear_is_rejected_and_new_render_works`, `test_exhausted_confirmation_replay_after_refill_is_rejected`, `test_obsolete_other_user_and_tampered_ids_do_not_consume_current_confirmation`, and `test_kind_switch_round_trip_uses_rendered_dropdown_ids_and_retains_settings` exercise the live handler/renderer registry with real SQLite and notification dispatch.
- [x] Task 7: 批次扣款次數驗證。[Review/Major]
  - Tests: `tests/test_affix_manager.py`。
  - Acceptance: 工具素材與萬能素材均使用真實扣款函式。spy 或 SQLite trace 必須證明每批次只有一次扣款。
  - Acceptance: 含失敗抽選的批次仍只扣一次總成本。單純改成逐次扣款時測試必須失敗。
  - Evidence: `UV_CACHE_DIR=/private/tmp/idlevillage-uv-cache uv run --no-project python -m unittest tests.test_affix_manager -q` — `Ran 50 tests in 0.949s`; `OK`. Output: `/private/tmp/idlevillage-task7.log`.

## Review Issues

- [x] [Review/Major] 一次性確認必須綁定玩家目前 renderer 產生的完整 ID，並在首次 await 前消耗。`test_confirmation_replay_after_clear_is_rejected_and_new_render_works` 驗證成功後清槽再重送不扣款、不公告；`test_exhausted_confirmation_replay_after_refill_is_rejected` 驗證耗盡後加素材仍拒絕舊 ID。
- [x] [Review/Major] 批次扣款次數固定為一次。`test_tool_batch_calls_real_debit_once_after_rejected_draws` 與 `test_universal_exhaustion_calls_real_debit_once_for_total_cost` 使用 wraps 執行真實素材扣款與 SQLite，並檢查所選扣款只呼叫一次、金額等於總成本、另一來源未呼叫及最終餘額。
- [x] [Review/Major] 任意與特定效果切換必須由當前 renderer custom_id 驅動，並保留效果、門檻與素材來源。`test_kind_switch_round_trip_uses_rendered_dropdown_ids_and_retains_settings` 驗證特定 -> 任意 -> 特定切換期間資料庫素材不變。
- [x] [Review/Major] 每個自動抽取確認 ID 必須綁定當下第一個空槽。`test_slot_bound_confirmation_blocks_repeat_and_allows_next_slot` 驗證等級 10 的並行確認只扣一次並填槽 0；重送同 ID 不扣款、不公告；重新渲染後的槽 1 確認可成功。`test_confirmation_binds_first_empty_slot_and_stays_within_limit` 驗證最早空槽與滿槽 ID。
- [x] [Plan/Major] 抽選不得長時間持有寫入鎖。抽選先在交易外完成。交易內只重讀狀態、一次扣款與最終填槽。
- [x] [Plan/Major] 補上扣款後失敗、提交失敗與並行競爭的真實 SQLite 測試。
- [x] [Plan/Minor] 素材 canonical 文件納入更新。新增自動抽取規則的交叉連結。
- [x] [Plan] 獨立 Codex 複審結果為 Approved。

## Key Assumptions

- 批次抽選保留單抽的效果與數值分布。
- Discord 使用者操作後只需要最終結果。
- 自動抽取不消耗 AP。

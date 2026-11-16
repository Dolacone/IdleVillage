---
title: "數字顯示加上千分位逗號"
status: Ready-to-implement
created: 2026-11-16
doc_type: change
last_reviewed: 2026-11-16
source_paths:
  - "docs/README.md"
  - "docs/discord/ui-renderer.md"
  - "docs/discord/notification.md"
  - "src/cogs/ui_renderer.py"
  - "src/core/notification.py"
  - "src/cogs/actions.py"
scope: "Tracks this change from design through review."
---

## Problem Statement

Bot 顯示的數字沒有千分位分隔，大數字難以閱讀。

```
村莊試煉達成！目標 750000 點行動產出已完成
共 12 位玩家瓜分了 7505 個 🌟萬能素材（25% 平均分配、75% 依貢獻度）：
貢獻 156618 (1331 素材)：𝕯𝖔𝖑𝖆
```

## Recommended Direction

所有玩家可見的數字都以 `,` 分隔千分位。

```
村莊試煉達成！目標 750,000 點行動產出已完成
共 12 位玩家瓜分了 7,505 個 🌟萬能素材（25% 平均分配、75% 依貢獻度）：
貢獻 156,618 (1,331 素材)：𝕯𝖔𝖑𝖆
```

- 範圍涵蓋所有 Discord 顯示文字：
  - 村莊 Dashboard 與主介面 Embed。
  - 工具強化、詞條管理、自動抽取、自動工具、試煉目標選單的 Embed 與元件 label/description。
  - Public 通知。
  - `/idlevillage-ranking` 與管理員介面。
- 等級（`Lv{n}`）也加逗號，例如 `Lv1,024`。
- 小數保留現有位數規則，只在整數部分加逗號。
- 數值本身、四捨五入與計算邏輯不變。

### Alternatives

| 方向 | 結果 |
| :--- | :--- |
| A：共用格式函式，在每個顯示點呼叫（選定） | 一處定義格式規則 |
| B：每個顯示點各自寫 `f"{n:,}"` | 小數與整數規則分散 |
| C：對最終訊息字串做正規表達式替換 | 會改壞時間戳記與 ID |

- 選 A：整數與小數格式只定義一次，所有顯示點一致。
- 排除 B：小數去除尾隨零的規則要在多處重複。
- 排除 C：`<t:{unix}:R>`、custom_id、玩家 ID fallback 也是數字，會被誤加逗號。

## Key Assumptions

- 玩家閱讀加逗號的數字比未加逗號快。
- 沒有玩家或外部工具從 Bot 訊息文字解析數字。

## Clarifications

<!-- Q: 等級（Lv）達到 1000 以上也加逗號嗎？ / A: 是，所有顯示數字一致，例如 Lv1,024。 — resolved during idea stage -->
<!-- Q: 新分支從哪裡開？ / A: 疊在 PR #16 分支 2026-11-05-remove-building-upgrade-notification 上，PR 目標為 main。 — resolved during idea stage -->

## MVP Scope / Not Doing

MVP Scope:

- 所有玩家可見數字加千分位逗號，包含等級。

Not Doing:

- 不加逗號的值依 `docs/discord/ui-renderer.md`「數字格式」。
- 不改 log 輸出。
- 不改數值縮寫（不使用 萬、K、M）。

## Architecture Decisions

- 新增 `fmt_num(value: int | float) -> str` 於 `src/cogs/ui_renderer.py`。
  - `int` 回傳 `f"{value:,}"`，例如 `1234567` -> `1,234,567`。
  - `float` 回傳 `f"{value:,g}"`，例如 `10.0` -> `10`、`0.05` -> `0.05`、`1234.5` -> `1,234.5`。
  - `src/` 內沒有既有的數字格式函式（grep `:,}`、`def fmt`、`def format_` 無結果）。
  - `ui_renderer.py` 已是 `notification.py` 與 `actions.py` 匯入顯示常數的來源，格式函式放在同一處。
  - 鐵齒加成顯示既有 `:g` 規則（去除尾隨零），`,g` 保留此規則。
- 每個顯示點直接呼叫 `fmt_num`，不對最終字串做後處理。
- 不加逗號的值依 `docs/discord/ui-renderer.md`「數字格式」的排除清單。
- 正常運作下不會達到 1,000 的顯示點不呼叫 `fmt_num`：自動工具小時選單（上限 `AUTO_TOOL_MAX_HOURS`）、`affix_extracted`/`affix_cleared` 通知（詞條數值 1..5）。
- `trial_target_select` 的 option label 改為 `fmt_num(target)`，value 維持 `str(target)`。
- 數字格式規則由 `docs/discord/ui-renderer.md` 的「數字格式」擁有；`docs/discord/notification.md` 引用該節。

## Tasks

Dependency graph:

```
Task 1 (ui_renderer.py: fmt_num + village/main/trial/action menus)
├── Task 2 (ui_renderer.py: gear/affix/auto-tool/admin/ranking)
├── Task 3 (notification.py)
└── Task 4 (actions.py sacrifice modal)
```

Tasks 2、3、4 互相獨立，可平行執行。

- [x] Task 1: Add `fmt_num` and format the village, main, trial target, and action menu displays
  - Files: `src/cogs/ui_renderer.py`, `tests/test_discord_commands.py`, `tests/test_discord_notifications.py`.
  - Parallel: none.
  - Scope: `fmt_num`, trial status line, `build_trial_target_embed`, `build_trial_target_components`, village section (stage, resources, building levels and cap, villager action counts), personal section (efficiency output and pct, tool levels, materials, AP, trial contribution), action and building target dropdowns.
  - Acceptance criteria:
    - `fmt_num(999) == "999"`, `fmt_num(1234567) == "1,234,567"`, `fmt_num(10.0) == "10"`, `fmt_num(0.05) == "0.05"`, `fmt_num(1234.5) == "1,234.5"`.
    - Village embed with stage progress `156618`, target `750000`, food `12345`, level cap `1000` contains `156,618 / 750,000`, `🌾 12,345`, `等級上限：Lv1,000`; the deadline still renders as `<t:{unix}:R>` with no comma.
    - Active trial line with progress `156618` and target `750000` contains `🏆 試煉 156,618 / 750,000`.
    - Trial target options show label `250,000` with value `250000`; the embed shows `最大目標：1,000,000` for a max target of `1000000`.
    - Building target option shows `Lv1,024` and `XP: 1,234/1,025,000` for level `1024`, xp `1234`, `BUILDING_XP_PER_LEVEL=1000`.
    - Existing assertions on these displays in `tests/test_discord_commands.py` and `tests/test_discord_notifications.py` expect comma-formatted values, for example `1,200 / 5,000`; the trial target option assertion checks label `fmt_num(int(value))`.
    - Personal section with tool level `1500`, materials `12345`, universal `2000`, trial contribution `156618` contains `1,500`, `12,345`, `🌟 2,000`, `🏆 試煉貢獻：156,618`; with stage and facility bonus 0 in the test env (`BASE_OUTPUT=20`, `GEAR_BONUS_PER_LEVEL=0.05`), the efficiency part for tool level `1500` is `1,520(+7,500%)`.
    - `uv run python -m pytest` passes.
- [ ] Task 2: Format gear, affix, auto-affix, auto-tool, admin, and ranking displays
  - Files: `src/cogs/ui_renderer.py`, `tests/test_discord_commands.py`.
  - Depends on: Task 1.
  - Parallel: with Task 3 and Task 4.
  - Scope: `build_gear_embed` (levels, rates, pity, risky bonus, cost, holdings, AP, cap, affix totals, sacrifice and result lines), tool type dropdown descriptions in `build_gear_components` and `build_affix_components`, affix summary, group list, affix management embed and group dropdown, auto-affix embed, auto-tool embed, `build_manager_embed`, resource admin embed and delta button labels, `build_ranking_text`.
  - Acceptance criteria:
    - Gear embed for level `1024`, material cost `1025`, holdings `12345`, universal `2000`, `risky_failed_levels` `150000`, `risky_bonus_pct` `1500.0` contains `Lv1,024 → Lv1,025`, `+ 1,025 個`, `持有素材：12,345 個 ｜ 🌟 萬能素材：2,000 個`, `鐵齒率：150,000 x 0.01% = 1,500%`.
    - Tool type dropdown descriptions in `build_gear_components` and `build_affix_components` for level `1024` with `GEAR_BONUS_PER_LEVEL=0.05` contain `+5,120% → +5,125%`.
    - Affix management embed and `build_auto_affix_embed` with holdings `12345` contain `持有素材：12,345 個`.
    - Existing assertions on these displays in `tests/test_discord_commands.py` expect comma-formatted values.
    - Auto-tool embed with tool material `1500` contains `素材可撐 1,500 小時`.
    - Manager embed with materials `12345` and `risky_failed_levels` `150000` shows `12,345` and `150,000`.
    - Resource admin embed with amount `1234567` shows `1,234,567`; delta buttons for `1000` show `+1,000` and `-1,000`.
    - Ranking text for level `1024` contains `- Lv1,024: {name}`.
    - `uv run python -m pytest` passes.
- [ ] Task 3: Format all Public notification numbers
  - Files: `src/core/notification.py`, `tests/test_discord_notifications.py`.
  - Depends on: Task 1.
  - Parallel: with Task 2 and Task 4.
  - Scope: every `_format_event` branch: `upgrade_stage_clear`, `overtime`, `gear_success`, `gear_fail`, `gear_batch`, `affix_auto_batch`, `affix_auto_extracted`, `trial_start`, `trial_success`, `trial_fail`.
  - Acceptance criteria:
    - `trial_success` with target `750000`, 12 participants, `total_awarded` `7505`, and a participant with contribution `156618`, reward `1331`, name `𝕯𝖔𝖑𝖆` renders these exact lines:
      - `🎉 村莊試煉達成！目標 750,000 點行動產出已完成`
      - `共 12 位玩家瓜分了 7,505 個 🌟萬能素材（25% 平均分配、75% 依貢獻度）：`
      - `貢獻 156,618 (1,331 素材)：𝕯𝖔𝖑𝖆`
    - `trial_start` with target `750000` and reward pool `7500` shows `花費 750,000 個`, `累積 750,000 點`, `共 7,500 個`; `<t:{deadline_unix}:R>` has no comma.
    - `trial_fail` with target `750000` and progress `123456` shows `（進度：123,456/750,000）`.
    - `overtime` with progress `156618` and target `750000` shows `已超過 86,400 秒` and `目前進度：156,618 / 750,000`.
    - `upgrade_stage_clear` with caps `1000`/`1005` and next target `1250000` shows `Lv1,000 變成 Lv1,005` and `目標需求：1,250,000`.
    - `gear_success`, `gear_fail`, `gear_batch` with level `1024` and failure count `1203` show `Lv1,024 -> Lv1,025（總失敗次數：1,203）`.
    - `affix_auto_extracted` and `affix_auto_batch` with attempts `1500` and spent `3000` show `抽選次數1,500 (3,000工具素材)`.
    - Existing assertions on notification text in `tests/test_discord_notifications.py` expect comma-formatted values, for example `貢獻 3,000`.
    - `uv run python -m pytest` passes.
- [ ] Task 4: Format the sacrifice modal holdings
  - Files: `src/cogs/actions.py`, `tests/test_discord_commands.py`.
  - Depends on: Task 1.
  - Parallel: with Task 2 and Task 3.
  - Acceptance criteria:
    - With holdings `12345`, the sacrifice modal label contains `（持有：12,345）` and the placeholder is `1 ~ 12,345`.
    - `uv run python -m pytest` passes.

## Plan Review Issues

- [x] Plan Issue 1: Task 1 的建設目標 AC `XP: 1,234/2,048`（level `1024`）無法成立。`next_req = (blevel + 1) * BUILDING_XP_PER_LEVEL`（`src/cogs/ui_renderer.py:454`），level `1024` 的需求必為 `1025` 的倍數；測試環境 `BUILDING_XP_PER_LEVEL=1000`。修正：AC 改為 level `1024`、xp `1234` 顯示 `Lv1,024` 與 `XP: 1,234/1,025,000`。
- [x] Plan Issue 2: Task 1 的 Files 漏列 `tests/test_discord_notifications.py`。`tests/test_discord_notifications.py:858` 斷言 `update_dashboard` 的試煉行含 `"1200 / 5000"`，Task 1 改 `_build_trial_line` 後變成 `1,200 / 5,000`，pytest AC 會失敗。修正：Task 1 Files 加入 `tests/test_discord_notifications.py`，並更新該斷言。
- [x] Plan Issue 3: 「Modal 輸入欄位的預設值」排除項描述不存在的行為。`src/` 內 16 個 `TextInput` 都沒有設定 `value=`。修正：從 Not Doing、Architecture Decisions 與 `docs/discord/ui-renderer.md`「數字格式」的排除清單刪除此項。
- [x] Plan Issue 4: Task 4 AC「Submitting `12345` in that modal still sacrifices 12345 materials」無法因本變更失敗。送出路徑讀玩家輸入 `int(raw)`（`src/cogs/actions.py:857`），本變更不碰它；`tests/test_discord_commands.py:2823` 已覆蓋送出。修正：刪除此 AC。
- [x] Plan Issue 5: Task 2 AC「Every custom_id and `SelectOption.value` built by these functions contains no comma」無法失敗。Task 2 函式的 custom_id 與 value 數字只有小時（上限 `AUTO_TOOL_MAX_HOURS=24`）與詞條數值（`AFFIX_VALUE_MAX=5`），其餘為字串 ID。修正：刪除此 AC。
- [x] Plan Issue 6: 部分顯示點的數字在正常運作下不會達到 1,000，加 `fmt_num` 不改變輸出。自動工具小時選單 label 上限 24（`.env.example:61`）；`affix_extracted`、`affix_cleared` 通知只有 `{value}`，範圍 1..5（`src/managers/affix_manager.py:26-27`）。修正：從 Task 2 Scope 刪除 hour dropdown labels，從 Task 3 Scope 刪除 `affix_extracted` 與 `affix_cleared`。
- [x] Plan Issue 7: 排除清單與格式規則寫在多處。擁有者是 `docs/discord/ui-renderer.md`「數字格式」，本文件的 Not Doing 與 Architecture Decisions 各重寫一次；`ui-renderer.md` 內「本文件與 `discord/notification.md` 範本中的數字欄位...」又重述「範圍」一項。修正：Architecture Decisions 的「以下值維持原樣」清單改為一行指向 `ui-renderer.md`「數字格式」；Not Doing 只留該節沒有的項目（例外與錯誤回覆、log、數值縮寫）；刪除 `ui-renderer.md` 的「本文件與 `discord/notification.md` 範本...」一項。
- [x] Plan Issue 8: 獻祭輸入超過持有量時，玩家看到未加逗號的持有數。`src/cogs/actions.py:857-862` 把 `gear_manager.sacrifice_material` 的 `ValueError` 文字放進 `result["error"]`，`build_gear_embed` 顯示為 `⚠️ 操作失敗：Insufficient materials: need 20000, have 12345`（`src/managers/gear_manager.py:100-101`）。玩家在 Modal 輸入大於持有量的數字即觸發，屬正常操作；Not Doing 的「manager `ValueError` 文字」排除項讓此數字留在四個 Task 之外，違反「所有顯示的數字」。修正：Not Doing 刪除「manager `ValueError` 文字」，只留 `player_manager_cog` 輸入錯誤回顯；`fmt_num` 改放 `src/core/utils.py`（managers 已匯入 `core.utils`，沒有 manager 匯入 `cogs`），Task 1 Files 加入 `src/core/utils.py`；Task 4 Files 加入 `src/managers/gear_manager.py`，`sacrifice_material` 的錯誤訊息以 `fmt_num` 格式化 `amount` 與 `materials`；Task 4 新增 AC：持有 `12345` 時送出 `20000`，Embed 含 `have 12,345`。
  - Rejected: 輸入超過持有量是失敗路徑，不是正常運作；Modal placeholder 已顯示加逗號的範圍 `1 ~ {holdings}`。manager `ValueError` 文字是例外訊息，格式化它需要 manager 依賴顯示格式，超出目標。例外訊息維持在 `docs/discord/ui-renderer.md`「數字格式」的排除清單。
- [x] Plan Issue 9: Task 3 沒有任何 AC 涵蓋 `overtime` 通知的 `{overtime_secs}`。`src/core/notification.py:117` 輸出 `第 {stage_n} 關已超過 {overtime_secs} 秒`，`STAGE_OVERTIME_SECONDS=86400`（`.env.example`、`tests/support.py:199`），每次逾時通知都會顯示 `86400`。Task 3 的 overtime AC 只檢查進度與目標，漏格式化 `86400` 時 AC 不會失敗。修正：Task 3 的 overtime AC 加入 `已超過 86,400 秒`。
- [x] Plan Issue 10: 「例外與錯誤回覆」排除項只寫在本文件 Not Doing，`docs/discord/ui-renderer.md`「數字格式」沒有。該節寫「所有玩家可見的數字」加 `,`，但 `build_gear_embed` 的 `⚠️ 操作失敗：{result['error']}`（`src/cogs/ui_renderer.py:625`）與 `player_manager_cog` 輸入錯誤回覆都是玩家可見且不加 `,`，實作後該節描述與行為不符，排除規則也分屬兩處。修正：`ui-renderer.md`「數字格式」的排除清單加一項「例外訊息與錯誤回覆中的數字（`⚠️ 操作失敗：` 後的 manager 錯誤文字、管理員輸入錯誤回覆）」；Not Doing 刪除「不改例外訊息與錯誤回覆中回顯的原始輸入」一項。
- [x] Plan Issue 11: Task 2 的「an unresolved name still shows the raw `user_id`」與 Task 3 的「An unresolved trial participant still shows the raw `user_id` with no comma」無法因本變更失敗。`user_id` 是 `TEXT`（`src/database/schema.py:70`），fallback 顯示的是字串；對字串套 `fmt_num` 會直接拋 `ValueError: Cannot specify ',' with 's'.`，不可能輸出加逗號的 `user_id`。`tests/test_discord_notifications.py:502`、`:1026`、`:1062` 已覆蓋 fallback 顯示。修正：刪除這兩條 AC。
- [x] Plan Issue 12: Task 1 與 Task 3 漏列會被本變更打破的既有斷言，只列了 `tests/test_discord_notifications.py:858`。Task 1 改 `_build_trial_line`、`build_village_embed`、試煉目標選單後失敗：`tests/test_discord_commands.py:170`（`300 / 1000`）、`:381`（`500 / 2000`）、`:559`（`🏆 試煉 2000 / 5000 (40%)`）、`:638-639`（label `25000`、`300000`）、`:640`（`option.label == option.value`）、`:678`（embed 含 `650000`）。Task 3 改 `_format_event` 後失敗：`tests/test_discord_notifications.py:430-431`（`150000`）、`:479`（`5000`）、`:486-487`、`:502`、`:924`、`:960-961`、`:1026-1027`、`:1062-1063`、`:1099`（`貢獻 3000`/`2000`/`5000`）、`:532`（`3200/5000`）。修正：Task 1 列出 commands 測試這 7 處並改為加 `,` 的期望值，`:640` 改為斷言 label 為 `fmt_num(int(value))`；Task 3 Files 已含 `tests/test_discord_notifications.py`，列出上述斷言並改為加 `,` 的期望值。
  - Resolved without per-line lists: each task now carries one AC that existing assertions on its displays expect comma-formatted values.
- [x] Plan Issue 13: 三個 scope 內、正常運作會達到 1,000 的顯示點沒有 AC，漏格式化時 AC 不會失敗。Task 1：`📊 效率` 的 `{output}(+{pct}%)`（`src/cogs/ui_renderer.py:327`），`.env.example` 的 `GEAR_BONUS_PER_LEVEL=0.03` 下工具 Lv334 起 pct 超過 1,000；現有個人區 AC 只檢查 `1,500`、`12,345`、`🌟 2,000`、試煉貢獻。Task 2：`build_auto_affix_embed` 的 `持有素材：{materials} 個`（`:905`），以及 `build_affix_components` 自己的 `gear_description`（`:795-802`），Scope「gear type dropdown descriptions」沒有點名後者，AC 只檢查 `build_gear_components`。修正：Task 1 個人區 AC 加入「工具等級 `1500`（測試環境 `GEAR_BONUS_PER_LEVEL=0.05`、`BASE_OUTPUT=20`、關卡與設施 0）顯示 `1,520(+7,500%)`」；Task 2 Scope 點名 `build_gear_components` 與 `build_affix_components` 的工具類型選單，AC 加入「`build_affix_components` 工具類型選單 description 在 level `1024`、每級 1% 時含 `+1,024% → +1,025%`」與「`build_auto_affix_embed` 持有 `12345` 時含 `持有素材：12,345 個`」。
  - Tool type description AC uses the test env `GEAR_BONUS_PER_LEVEL=0.05`: `+5,120% → +5,125%`; the earlier 1% example could not hold in tests.

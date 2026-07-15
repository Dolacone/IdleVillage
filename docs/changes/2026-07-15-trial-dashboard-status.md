---
title: "村莊 Dashboard 隨時顯示試煉狀態"
status: Issues-confirmed
created: 2026-07-15
doc_type: change
last_reviewed: 2026-07-15
source_paths:
  - src/cogs/ui_renderer.py
  - docs/discord/ui-renderer.md
  - tests/test_discord_commands.py
scope: "Tracks making the village Dashboard trial line always visible (active/openable/insufficient-resources/cooldown), from design through review."
---

## Problem Statement

目前村莊 Dashboard 的試煉列（`🏆 試煉 ...`）僅在 `trial_state.is_active` 為真時顯示，其餘狀態下整行省略（見 `docs/discord/ui-renderer.md` 「試煉進度列」小節）。使用者希望 Dashboard 隨時顯示試煉狀態，讓所有人不需開啟 `/idlevillage` 主介面也能看到目前是否能開啟試煉、或要等到何時才能開啟。

## Recommended Direction

`🏆 試煉` 這一行固定顯示於 Dashboard，內容依當下狀態切換為以下四態之一（沿用既有 `🏆 試煉` 前綴，不新增行數，維持與其他 Dashboard 列一致的單行風格）：

1. 進行中（`is_active=1`）：沿用現有格式 `{progress} / {target} ({pct}%)` + 進度條 + `⏰ 期限: <t:{deadline}:R>`（不變更）。
2. 可開啟（`is_active=0`，冷卻已過，且三種資源至少一種 `>= TRIAL_TARGET_AMOUNT`）：`✅ 可開啟試煉`。
3. 資源不足（`is_active=0`，冷卻已過，但三種資源皆 `< TRIAL_TARGET_AMOUNT`）：`⚠️ 資源不足，尚無法開啟`。
4. 冷卻中（`is_active=0` 且 `ended_at` 存在且 `now - ended_at < TRIAL_COOLDOWN_SECONDS`）：`⏳ 可於 {absolute_time} 後開啟`，其中 `{absolute_time}` 為 `<t:{deadline}:t>`（Discord 短時間格式，顯示固定時刻如 `12:34 AM`，而非倒數的相對時間），`deadline = ended_at + TRIAL_COOLDOWN_SECONDS`。

判斷優先序：`is_active` → 冷卻中 → 資源不足 → 可開啟（與 `trial-manager.md`／`ui-renderer.md` 既有的 `open_trial_start` 按鈕 disabled 判斷條件一致，只是從「兩態：可按/不可按」拆成「四態文字說明」）。

資料需求：Dashboard 資料擷取層（`notification.py._fetch_village_dashboard_data`）需額外取得村莊三種資源存量（判斷是否 `>= TRIAL_TARGET_AMOUNT`）與 `ended_at`，用於計算冷卻/資源不足/可開啟三態。三種資源存量該函式目前已查詢（供「公用資源」列顯示），可直接複用，不需新增查詢。

`ui_renderer.py` 的 `_build_village_section`／`build_village_embed` 新增判斷邏輯：`trial_data` 需額外攜帶 `resources`（三種資源現值，或直接複用既有的 `get_eligible_resource_types` 邏輯之於 UI 側的等價判斷）與 `ended_at`，用於推導上述四態。

### 排除的替代方案

- 狀態文字 + 條件細節行（`🏆 試煉狀態：{狀態}` 固定標題行，細節另起一行）：與使用者確認的樣式不符（使用者選擇單一 `🏆 試煉` 列、內容隨狀態切換，而非固定「狀態：」文字前綴），且會讓 Dashboard 多一行，不必要地增加篇幅。
- 冷卻中改用相對時間 `<t:{deadline}:R>`（與試煉期限的相對時間格式一致）：使用者明確要求冷卻時間需為固定時刻（如 `12:34`），而非「3 小時後」的相對倒數，故排除。
- 資源不足併入「可開啟試煉」文字、不獨立顯示：使用者確認資源不足應為獨立第四態，明確顯示「資源不足，尚無法開啟」，讓觀察 Dashboard 的人知道具體卡在哪個條件，而非籠統的「不可開啟」。

## Clarifications

<!-- Q: 三種狀態（進行中/可開啟/冷卻中）要用哪種呈現格式？ / A: 沿用現有 🏆 試煉 開頭、同一行位置永遠顯示，內容依狀態切換（單一列方案）。 — resolved during refine stage -->
<!-- Q: 冷卻中的時間顯示要用相對時間還是固定時間？ / A: 固定時間（如 12:34），不要相對時間（如「3 小時後」）。 — resolved during refine stage -->
<!-- Q: 資源不足以開啟試煉（三種資源皆低於 TRIAL_TARGET_AMOUNT，但已過冷卻）算不算獨立第四種狀態？ / A: 是，獨立顯示「⚠️ 資源不足，尚無法開啟」。 — resolved during refine stage -->

## MVP Scope / Not Doing

- 範圍內：
  - Dashboard `🏆 試煉` 列固定顯示（不再於非進行中時整行省略），依進行中／可開啟／資源不足／冷卻中四態切換文字。
  - 冷卻中狀態顯示固定時刻（`<t:{deadline}:t>`），非相對倒數時間。
  - `docs/discord/ui-renderer.md` 更新對應格式規格與判斷優先序。
- 範圍外：
  - `/idlevillage` 主介面（Ephemeral）的顯示邏輯不變：該介面已有「🏆 開啟試煉」按鈕本身的 disabled 狀態，不在本次變更範圍內重複加上文字狀態說明。
  - 不新增/變更任何試煉核心邏輯（`trial_manager.py` 完全不動）。
  - 不變更試煉「進行中」狀態本身的顯示格式（沿用既有進度條/期限格式）。

## Key Assumptions

- 冷卻中固定時刻採 Discord `<t:{unix}:t>`（短時間格式，如 `12:34 AM`），會依觀看者當地時區自動轉換顯示但不含相對倒數字樣；此假設依「固定時間(12:34)」的使用者原話推論為最貼近的 Discord timestamp style，上線後應與使用者確認顯示樣式是否符合預期（例如是否需要改用 `<t:{unix}:f>` 附帶日期，避免冷卻跨日時看不出是「今天 12:34」還是「明天 12:34」）。

## Architecture Decisions

1. **不新增任何資料查詢，僅修改 `ui_renderer.py` 的顯示邏輯**：實際檢視 `src/cogs/ui_renderer.py` 後確認 `_build_village_section(stage_data, resources, buildings, action_counts, trial_data)` 已經同時收到 `resources`（食物/木頭/知識現值，用於既有「公用資源」列）與 `trial_data`（`SELECT * FROM trial_state WHERE id=1` 的完整列，含 `is_active`／`ended_at`／`progress`／`target`／`started_at`）。四態判斷（進行中／可開啟／資源不足／冷卻中）所需的全部欄位都已在場，不需要修改 `notification.py`／`actions.py`／`general.py` 的資料擷取層或新增查詢。範圍縮小為 `ui_renderer.py` 單檔。
2. **四態判斷邏輯內嵌於 `_build_village_section`，不獨立成 helper 函式**：目前僅有一個呼叫點組裝 `trial_line`（同時供 `build_village_embed` 使用），邏輯複雜度低（四個 if/elif 分支），抽出獨立函式對可讀性無明顯助益，比照現有 `is_active` 單分支的既有寫法直接擴充為 if/elif/elif/else。
3. **冷卻中固定時刻使用 `<t:{unix}:t>`（Discord 短時間格式）**：既有「進行中」的期限使用 `<t:{unix}:R>`（相對時間），使用者明確要求冷卻時間改為固定時刻，`:t` 為 Discord timestamp style 中最接近「僅顯示時刻」的格式（如 `12:34 AM`），見 Key Assumptions 中對此假設的保留意見。
4. **判斷優先序：`is_active` → 冷卻中 → 資源不足 → 可開啟**：與既有 `build_main_components()` 的 `open_trial_start` 按鈕 disabled 判斷條件（`docs/discord/ui-renderer.md` 「開啟試煉」小節）完全一致的檢查順序，確保 Dashboard 文字說明與按鈕實際可否點擊的邏輯不會互相矛盾。

## Tasks

- [x] Task 1: `ui_renderer.py` 試煉列四態顯示
  - Files: `src/cogs/ui_renderer.py`（另需同步更新 `docs/discord/ui-renderer.md` 對應章節，非 source/logic 檔不計入限制）
  - Tests: 更新 `tests/test_discord_commands.py`，涵蓋：(a) 進行中時維持現有格式不變（既有測試 `test_embed_shows_trial_line_when_active` 應維持通過）；(b) 冷卻已過且至少一種資源足夠時顯示 `✅ 可開啟試煉`；(c) 冷卻已過但三種資源皆不足 `TRIAL_TARGET_AMOUNT` 時顯示 `⚠️ 資源不足，尚無法開啟`；(d) 冷卻中（`ended_at` 存在且未滿 `TRIAL_COOLDOWN_SECONDS`）時顯示 `⏳ 可於 <t:{deadline}:t> 後開啟`，且 `deadline = ended_at_unix + TRIAL_COOLDOWN_SECONDS`；(e) 更新既有 `test_embed_omits_trial_line_when_inactive`／`test_embed_omits_trial_line_when_trial_data_not_provided` 兩個測試，反映「不再整行省略、而是顯示四態之一」的新行為（`test_announcement_dashboard_embed_shows_active_trial` 等既有進行中測試不受影響）
  - Depends on: 無
  - Acceptance: `_build_village_section`／`build_village_embed` 在任何 `trial_data`／`resources` 組合下皆輸出四態之一的 `🏆 試煉` 列（不再省略整行）；判斷優先序與 `open_trial_start` 按鈕 disabled 條件一致；`docs/discord/ui-renderer.md` 「試煉進度列」章節更新為四態格式規格並更新 `last_reviewed`；既有測試套件全數通過

### 平行任務標記

僅一個任務，無平行需求。

## Review Issues
- [ ] Issue 1: [Major] `_build_village_section` is shared by both `build_village_embed` (public Dashboard) and `build_main_embed` (Ephemeral `/idlevillage` main UI, `src/cogs/ui_renderer.py:200,214`). The new inactive-state branches (`src/cogs/ui_renderer.py:138-152`) are embedded inside this shared helper, so `build_main_embed` now also renders `🏆 試煉 ⚠️/✅/⏳ ...` whenever no trial is active — contradicting the change document's stated MVP exclusion ("範圍外: `/idlevillage` 主介面（Ephemeral）的顯示邏輯不變... 不在本次變更範圍內重複加上文字狀態說明"). Verified by direct invocation: `build_main_embed({}, {}, {}, [], {'action': None, '_ap': 0})` produces `🏆 試煉 ⚠️ 資源不足，尚無法開啟` in the description. No test exercises this — `test_embed_omits_trial_contribution_when_inactive` (tests/test_discord_commands.py:631) only asserts `"試煉貢獻"` is absent, not the `🏆 試煉` village-section line, so it still passes despite the regression.
- [ ] Issue 2: [Minor] Architecture Decision 2 (change doc) states "目前僅有一個呼叫點組裝 `trial_line`（同時供 `build_village_embed` 使用）", which is internally inconsistent (says "only one call point" then names a second consumer) and factually incomplete — `_build_village_section` has two callers, `build_village_embed` (`src/cogs/ui_renderer.py:200`) and `build_main_embed` (`src/cogs/ui_renderer.py:214`), which is the root cause of Issue 1.
- [ ] Issue 3: [Minor] `docs/discord/ui-renderer.md`'s 主介面 Embed section (lines 90-104) was not updated to document that the main interface's village status block now also shows the 3 new inactive-trial states (per Issue 1); it still only documents the pre-existing "試煉貢獻" line's active/inactive behavior.

---
title: "村莊 Dashboard 隨時顯示試煉狀態"
status: Draft
created: 2026-07-15
doc_type: change
last_reviewed: 2026-07-15
source_paths: []
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

（於 plan 階段補充）

## Tasks

（於 plan 階段補充）

---
title: "idlevillage-manager 統一管理介面"
status: Issues-confirmed
created: 2026-05-15
doc_type: change
last_reviewed: 2026-05-15
source_paths:
  - src/cogs/player_manager_cog.py
  - src/cogs/ui_renderer.py
  - docs/discord/command-handler.md
  - docs/discord/ui-renderer.md
  - tests/test_player_manager_cog.py
scope: "將 /idlevillage-manager 的五個 sub-command 整合為單一介面，透過點選操作完成所有管理動作。"
---

## Problem Statement

管理員使用 `/idlevillage-manager` 時需記憶並輸入五個不同 sub-command（`player-view`、`player-gear`、`player-material`、`player-pity`、`player-risky`），指令繁多且難以記憶，修改同一玩家多個欄位時需重複輸入多次指令。

## Recommended Direction

將五個 sub-command 整合為單一 `/idlevillage-manager` 指令（無需 sub-command 參數）。觸發後以 ephemeral 訊息呈現 Discord 使用者選擇器；選定玩家後顯示該玩家的完整數據面板，面板包含所有欄位的當前數值與各自的 `[編輯]` 按鈕；點擊 `[編輯]` 後彈出 Modal 輸入新值並即時更新。

互動流程：
1. `/idlevillage-manager` → ephemeral 回應 + 選擇玩家 Dropdown
2. 選定玩家 → 顯示玩家數據面板（embed）+ 各欄位編輯按鈕
3. 點擊 `[編輯工具等級]`、`[編輯素材]`、`[編輯保底]`、`[編輯鐵齒]` → Modal 輸入數值
4. 提交 Modal → 更新數值、刷新面板

## Key Assumptions

- [x] 舊的五個 sub-command 將被完全移除，不保留相容性入口
- [x] 面板為 ephemeral（僅管理員可見），不需要公開顯示
- [x] Discord user select menu 可正確列舉伺服器成員（非 Bot 帳號）
- [x] 工具類型（gear_type）有四種：gathering、building、combat、research，各自需要獨立的工具等級與素材編輯
- [x] 編輯工具/素材時，Modal 內直接呈現四個工具類型的欄位，一次輸入全部數值

## MVP Scope

**做**
- 移除五個舊 sub-command 的定義
- 新增單一 `/idlevillage-manager` slash command（無參數）
- 第一步：Discord user select menu 讓管理員選擇目標玩家
- 第二步：顯示玩家完整數據面板（採集/建設/戰鬥/研究各工具等級、素材數、保底計數、鐵齒累積）
- 各欄位旁的 `[編輯]` 按鈕（工具類型共用一個「編輯工具/素材」入口，再用 dropdown 選類型）
- Modal 輸入新值並呼叫現有的 player_manager 寫入函式

**不做**
- 批次編輯多位玩家
- 操作歷史記錄 / 復原功能
- 非管理員玩家看到的只讀版面板

## Tasks

- [x] Task 1: 在 ui_renderer.py 新增 `build_manager_embed()` 與 `build_manager_components()` 純渲染函式
- [x] Task 2: 重構 PlayerManagerCog — 移除五個 sub-command，新增無參數的 `/idlevillage-manager` 指令（回傳含 user select menu 的 ephemeral 訊息）及 `player_select` 互動 handler（顯示玩家面板）
- [x] Task 3: 在 PlayerManagerCog 實作各 `[編輯]` 按鈕的 Modal 彈出與 `on_modal_submit` handler，提交後更新面板
- [x] Task 4: 更新 docs/discord/command-handler.md 與 docs/discord/ui-renderer.md，反映新的指令結構與 UI 元件

---

## Review Issues

- [ ] Issue 1 (Important — Security): `src/cogs/player_manager_cog.py` line 177 — `on_modal_submit` uses `await inter.response.defer()` without `ephemeral=True`. In disnake, modal interactions default to `with_message=True, ephemeral=False`, so `edit_original_response()` will post a **public** message, exposing player data and admin operations to all channel members. Fix: change to `await inter.response.defer(ephemeral=True)`. Add a test asserting `defer(ephemeral=True)` is called in the modal submit handler.

- [ ] Issue 2 (Nit — Documentation): `docs/discord/command-handler.md` line 63 — route description says `player_manager.set_pity_count()` but the actual API is `player_manager.set_pity()`. This will mislead future maintainers. Fix: update to `set_pity()`.

- [ ] Issue 3 (Nit — Architecture): `src/cogs/player_manager_cog.py` lines 58–92 and 225–262 duplicate the same player SELECT + row unpack + `player_data` dict construction logic. Not a behavior error, but consider extracting a private `_fetch_player_data(db, user_id)` helper to reduce risk of divergence when fields change.

---

## Task Detail

### Task 1: 新增 ui_renderer 渲染函式

**Description:**
在 `src/cogs/ui_renderer.py` 新增兩個純函式，不含業務邏輯、不存取資料庫，所有資料以參數傳入。

`build_manager_embed(target_user_display_name: str, player_data: dict) -> disnake.Embed`
- Embed title：`玩家管理：{target_user_display_name}`
- Color：`disnake.Color.orange()`
- Fields（各自 inline=False）：
  - 工具等級：`採集 {gear_gathering} ｜ 建設 {gear_building} ｜ 戰鬥 {gear_combat} ｜ 研究 {gear_research}`
  - 素材數量：`採集 {materials_gathering} ｜ 建設 {materials_building} ｜ 戰鬥 {materials_combat} ｜ 研究 {materials_research}`
  - 保底計數：`採集 {pity_gathering} ｜ 建設 {pity_building} ｜ 戰鬥 {pity_combat} ｜ 研究 {pity_research}`
  - 鐵齒失敗累積：`{risky_failed_levels}`

`build_manager_components(target_user_id: str) -> list`
- Row 1：四個按鈕 `[編輯工具等級]` `[編輯素材]` `[編輯保底]` `[編輯鐵齒]`
  - custom_id 規則：`mgr_edit_gear:{target_user_id}`、`mgr_edit_material:{target_user_id}`、`mgr_edit_pity:{target_user_id}`、`mgr_edit_risky:{target_user_id}`
  - Style：全部 `ButtonStyle.secondary`

**Acceptance criteria:**
- [ ] `build_manager_embed()` 回傳 `disnake.Embed`，標題含 display_name，四個欄位值對應 player_data 欄位
- [ ] `build_manager_components()` 回傳含一個 ActionRow（四個按鈕）的 list，custom_id 皆含 target_user_id

**Verification:**
- [ ] `uv run python -m pytest tests/test_player_manager_cog.py -k "embed or component" -v` 通過
- [ ] 手動確認 `build_manager_embed` 與 `build_manager_components` 可正常匯入

**Dependencies:** 無

**Files likely touched:**
- `src/cogs/ui_renderer.py`
- `tests/test_player_manager_cog.py`（新增渲染函式單元測試）

**Estimated scope:** Small (1-2 files)

---

### Task 2: 重構 PlayerManagerCog — 新指令 + player_select handler

**Description:**
重構 `src/cogs/player_manager_cog.py`：

1. 移除五個 sub-command（`player_view`、`player_gear`、`player_material`、`player_pity`、`player_risky`）及其 `@manager.sub_command` 裝飾器，並移除 `@commands.slash_command(name="idlevillage-manager")` 的空 `pass` parent handler。

2. 新增有內容的 `/idlevillage-manager` slash command（無子指令）：
   - guild/admin 雙重檢查
   - `await inter.response.defer(ephemeral=True)`
   - 回傳含 `disnake.ui.UserSelect(custom_id="mgr_player_select", placeholder="選擇玩家...")` 的 ephemeral 訊息（content：`請選擇要管理的玩家：`）

3. 新增 `on_dropdown` listener（或在現有 listener 中加入路由），處理 `custom_id == "mgr_player_select"`：
   - guild/admin 雙重檢查
   - `await inter.response.defer()`
   - 取得 `inter.values[0]`（selected user id）
   - 查詢 DB 取得玩家數據（若玩家不存在則回傳 content 提示並停止）
   - 呼叫 `build_manager_embed()` 和 `build_manager_components()` 渲染面板
   - `await inter.edit_original_response(embed=embed, components=components)`

注意：`PlayerManagerCog` 目前只有 slash command 沒有 listener。需新增 `on_dropdown` listener 或改用獨立 listener。

**Acceptance criteria:**
- [ ] `/idlevillage-manager` 指令（無子指令）成功呼叫：回傳含 `UserSelect` 的 ephemeral 訊息
- [ ] `mgr_player_select` dropdown 觸發後，若玩家存在，`edit_original_response` 以 embed + components 呼叫
- [ ] `mgr_player_select` 觸發後，若玩家不存在，回傳 `尚未加入遊戲` 訊息
- [ ] 舊有五個 sub-command 均已移除
- [ ] 非 admin 或錯誤 guild 的請求在兩處均被拒絕

**Verification:**
- [ ] `uv run python -m pytest tests/test_player_manager_cog.py -v` 通過（舊測試可能需更新，因 sub-command 已移除）
- [ ] 確認 `/idlevillage-manager` 指令有對應的實作（非 pass）

**Dependencies:** Task 1（需要 `build_manager_embed`、`build_manager_components`）

**Files likely touched:**
- `src/cogs/player_manager_cog.py`
- `tests/test_player_manager_cog.py`（更新舊測試、新增 slash command 與 player_select 測試）

**Estimated scope:** Medium (2 files)

---

### Task 3: 實作編輯按鈕的 Modal 與 submit handler

**Description:**
在 `PlayerManagerCog` 新增 `on_button_click` listener，處理 `mgr_edit_*` 系列按鈕。

各按鈕對應的 Modal（standard disnake modal，`send_modal`）：

| 按鈕 custom_id | Modal title | TextInput fields |
|---|---|---|
| `mgr_edit_gear:{uid}` | `編輯工具等級` | 採集、建設、戰鬥、研究（各自 `label` 為工具名稱，`custom_id` 為 `gear_gathering` 等，`required=True`，`style=short`） |
| `mgr_edit_material:{uid}` | `編輯素材數量` | 採集、建設、戰鬥、研究（`custom_id` 為 `mat_gathering` 等） |
| `mgr_edit_pity:{uid}` | `編輯保底計數` | 採集、建設、戰鬥、研究（`custom_id` 為 `pity_gathering` 等） |
| `mgr_edit_risky:{uid}` | `編輯鐵齒失敗累積` | 單一欄位（`custom_id=risky_failed_levels`） |

Modal `custom_id` 規則（用於 submit handler 識別）：
- `mgr_modal_gear:{target_user_id}`
- `mgr_modal_material:{target_user_id}`
- `mgr_modal_pity:{target_user_id}`
- `mgr_modal_risky:{target_user_id}`

`on_modal_submit` listener，處理前綴 `mgr_modal_`：
1. guild/admin 雙重檢查
2. 解析 `inter.custom_id` 取得 modal 類型與 target_user_id
3. 解析 `inter.text_values`，每個欄位強制轉換成非負整數（驗證失敗回傳錯誤訊息）
4. 呼叫對應的 `player_manager.set_*` 函式並 `await db.commit()`
5. 重新查詢玩家數據，呼叫 `build_manager_embed()` + `build_manager_components()` 刷新面板
6. `await inter.edit_original_response(embed=embed, components=components)`

**Acceptance criteria:**
- [ ] 各 `mgr_edit_*` 按鈕觸發時正確呼叫 `send_modal`，Modal 含對應欄位
- [ ] `mgr_modal_gear` submit：四個 gear level 皆寫入 DB，面板刷新
- [ ] `mgr_modal_material` submit：四個素材皆寫入 DB，面板刷新
- [ ] `mgr_modal_pity` submit：四個保底計數皆寫入 DB，面板刷新
- [ ] `mgr_modal_risky` submit：risky_failed_levels 寫入 DB，面板刷新
- [ ] 任意欄位輸入負數或非整數 → 回傳錯誤訊息，不寫入 DB
- [ ] 非 admin 的 button/modal submit 被拒絕

**Verification:**
- [ ] `uv run python -m pytest tests/test_player_manager_cog.py -v` 通過
- [ ] DB 資料確認（各欄位更新後重新查詢驗證）

**Dependencies:** Task 1、Task 2

**Files likely touched:**
- `src/cogs/player_manager_cog.py`
- `tests/test_player_manager_cog.py`（新增 Modal 觸發與 submit 測試）

**Estimated scope:** Medium (2 files)

---

### Task 4: 更新 SSOT 文件（command-handler.md、ui-renderer.md）

**Description:**
依照新實作更新兩份 SSOT 文件，不修改任何 source code。

`docs/discord/command-handler.md`：
- Slash Commands 表：將五個 `player-*` sub-command 列改為單一 `/idlevillage-manager`（無參數），描述其互動流程
- 互動元件路由新增「玩家管理員介面」段落，記錄：
  - `mgr_player_select`：user select → 顯示玩家面板
  - `mgr_edit_gear:{uid}` / `mgr_edit_material:{uid}` / `mgr_edit_pity:{uid}` / `mgr_edit_risky:{uid}`：按鈕 → 彈出 Modal
  - `mgr_modal_gear:{uid}` / `mgr_modal_material:{uid}` / `mgr_modal_pity:{uid}` / `mgr_modal_risky:{uid}`：Modal submit → 寫入 DB + 刷新面板
- Changelog 加一筆：`2026-05-15: Replaced five /idlevillage-manager sub-commands with a single unified interface driven by user select + modal edits.`

`docs/discord/ui-renderer.md`：
- 新增「玩家管理員介面 Embed（/idlevillage-manager，Ephemeral）」段落，說明：
  - Embed title 格式、fields 格式
  - 四個按鈕的 custom_id 規則
- Changelog 加一筆：`2026-05-15: Added build_manager_embed() and build_manager_components() for the unified manager interface.`

**Acceptance criteria:**
- [ ] `command-handler.md` 不再列出五個 sub-command，改列單一 `/idlevillage-manager` 入口
- [ ] `command-handler.md` 的互動元件路由包含所有 `mgr_*` custom_id
- [ ] `ui-renderer.md` 包含 `build_manager_embed` 與 `build_manager_components` 的格式說明

**Verification:**
- [ ] 人工比對文件與 Task 1–3 的實作，確認描述一致

**Dependencies:** Task 1、Task 2、Task 3（文件需反映最終實作）

**Files likely touched:**
- `docs/discord/command-handler.md`
- `docs/discord/ui-renderer.md`

**Estimated scope:** Small (2 doc files)

---
title: "強化工具與詞條管理 Dropdown 初始無預設選項"
status: Ready-to-implement
created: 2026-06-27
doc_type: change
last_reviewed: 2026-06-27
source_paths:
  - src/cogs/ui_renderer.py
  - src/cogs/actions.py
  - tests/test_discord_commands.py
scope: "調整強化工具和詞條管理介面，使兩個 Dropdown 在初始開啟時不顯示預設選中項，與行動選擇 Dropdown 行為一致。"
---

## Problem Statement

強化工具介面開啟時，工具類型 Dropdown 自動預選「採集工具」，強化模式 Dropdown 自動預選「標準」；詞條管理介面開啟時，工具類型 Dropdown 自動預選當前工具類型。玩家還沒做任何選擇時就看到預選項，行為與行動選擇 Dropdown（`pending_action=None` 時不預選）不一致。

## Recommended Direction

A（採用）：開啟介面時傳遞 `gear_type=None, mode=None`，利用現有 `default=(gear_type == g)` 邏輯在 None 比對時恆為 False，不需新增 flag 或 placeholder option。與 action dropdown 的 `pending_action=None` 模式對稱。

B（排除）：插入一個 disabled 空白 SelectOption 作為 default。需修改 options 結構，Discord UI 語義複雜，且 disabled option 在 StringSelect 中行為不一致。

C（排除）：傳入 `initial=True` flag 到多個 render 函數。侵入性高於 None 模式。

## Clarifications

## MVP Scope / Not Doing

MVP 包含：
- `open_gear_upgrade` 開啟時 gear_type=None、mode=None（兩個 dropdown 不預選）
- `open_affix_mgmt:{gear_type}` 開啟時 gear_type=None（gear dropdown 不預選）
- 工具類型選定後，模式 dropdown 仍不自動預選（維持 None 直到使用者選擇）
- 工具類型或模式為 None 時，強化、獻祭、詞條管理按鈕均 disabled

Not doing：
- 改變選擇後的重繪行為（選擇工具類型後自動帶入 "normal" 模式 ← 保留現有行為）
- 修改 embed 內容格式

## Architecture Decisions

### gear_type=None 的 render 路徑

`_render_gear(inter, None)` 分為兩條路徑：
- `gear_type is None`：只查 player 的 gear 等級與 gear_cap（building），不呼叫 `gear_manager.get_upgrade_info`，直接用 blank embed + 全 disabled components
- `gear_type is not None`：沿用現有邏輯，`effective_mode = mode or "normal"` 用於 DB 查詢

### 按鈕 custom_id sentinel

當 gear_type=None 時，Python f-string 格式化 `None` 會產生字串 `"None"`（大寫 N），所以 custom_id 實際為：
- `upgrade_mode_select:None` → handler 驗證 `gear_type in _VALID_GEAR_TYPES` 失敗 → 忽略
- `attempt_upgrade:None:normal` → 同上
- `sacrifice_material:None` → 同上
- `open_affix_mgmt:None` → 同上
- `back_to_gear:None` → handler 改為轉跳至 blank gear 狀態（不再直接 return）

為避免混淆，在 `build_gear_components` 和 `build_affix_components` 中使用 `_gt = gear_type or "none"` 顯式轉為小寫 `"none"` sentinel，不依賴 f-string 的 None 轉換。

### mode=None 的 attempt 按鈕 disabled 條件

`build_gear_components` 中 attempt 按鈕：`disabled = not can_attempt or mode is None`

### 詞條管理 back 按鈕在 blank 狀態

gear_type=None 時，`build_affix_components` 的 back 按鈕使用 `back_to_gear:none`；`back_to_gear` handler 當 gear_type 無效時改呼叫 `_render_gear(inter, None)`。

## Tasks

- [x] Task 1: `build_gear_embed` 和 `build_gear_components` 接受 `gear_type: str | None` 與 `mode: str | None`，並在 None 時回傳 blank 狀態
- [x] Task 2: `build_affix_embed` 和 `build_affix_components` 接受 `gear_type: str | None`，並在 None 時回傳 blank 狀態
- [ ] Task 3: `actions.py` 修改：
  - `_render_gear(gear_type: str | None, mode: str | None = None)`：當 `gear_type is None` 時只查 player gear 等級與 gear_cap，不呼叫 `get_upgrade_info`，直接傳 blank embed + components；當 `gear_type is not None` 時，在進入 `get_upgrade_info` 前做 `effective_mode = mode or "normal"` 轉換，避免 `None` 傳入引發 ValueError
  - `open_gear_upgrade` handler：改為 `await self._render_gear(inter, None)`
  - `open_affix_mgmt:{gear_type}` handler：改為 `await self._render_affix(inter, None)`（不傳 gear_type）
  - `back_to_gear:{gear_type}` handler：當 gear_type 不在 `_VALID_GEAR_TYPES` 時，改呼叫 `await self._render_gear(inter, None)` 再 return（移除原本的直接 return）
  - `_render_affix(gear_type: str | None)`：當 `gear_type is None` 時只查 player gear 等級與 gear_cap，不呼叫 `get_upgrade_info`

## Review Issues

## Plan Review Issues

- [x] Issue 1 (Critical): `_render_gear` 在接受 `gear_type=None` 後必須分叉 DB 查詢路徑，跳過 `gear_manager.get_upgrade_info`（`actions.py:155`）；Task 3 未描述這個分叉邏輯，實作者會直接傳 `None` 進 `get_upgrade_info`，引發 runtime crash。需在 Task 3 明確指定：當 `gear_type is None` 時，只查 player gear 總覽與 gear_cap，不呼叫 `get_upgrade_info`。
- [x] Issue 2 (Major): `mode=None` 傳入 `get_upgrade_info` 會觸發 `ValueError`（`gear_manager.py:137`：`if mode not in UPGRADE_MODES: raise ValueError`）。Architecture Decisions 提到 `effective_mode = mode or "normal"` 的轉換，但沒有任何 Task 指定這個轉換的位置（應在進入 `get_upgrade_info` 之前）。需在 Task 3 明確列出此轉換點。
- [x] Issue 3 (Major): `back_to_gear` handler 修正（當 `gear_type` 無效時改呼叫 `_render_gear(inter, None)` 而非 `return`）在 Task 3 描述中僅以「`back_to_gear` handler 修正」帶過，沒有明確說明行為變更。需在 Task 3 子任務中說明：移除 `return`，改呼叫 `_render_gear(inter, None)`。
- [x] Issue 4 (Minor): 計畫中描述 sentinel 為小寫 `"none"`（例如 `upgrade_mode_select:none`），但 Python f-string 格式化 `None` 產生的是 `"None"`（大寫 N，即 `upgrade_mode_select:None`）。雖然兩者行為均安全（皆不在 `_VALID_GEAR_TYPES`），文件描述應更正為 `"None"` 以避免實作者誤解。

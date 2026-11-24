---
title: "選單變動不重設其他選單"
status: Draft
created: 2026-11-24
doc_type: change
last_reviewed: 2026-11-24
source_paths:
  - "docs/README.md"
  - "docs/discord/command-handler.md"
  - "docs/discord/ui-renderer.md"
  - "src/cogs/ui_renderer.py"
  - "src/cogs/actions.py"
scope: "Tracks this change from design through review."
---

## Problem Statement

> command checkbox 單一項目的變動不會把其他 checkbox reset
> 例：改動工具類型的時候，`鐵齒`與`無限`選項應該維持不變

改動一個選單時，同畫面其他已選的選單被清空。

```
工具強化：選 建設工具 → 鐵齒 → 無限 → 改選 採集工具
  工具類型：🌾 採集工具
  強化模式：（未選）
  執行次數：（未選）

自動工具：選 建設 → 3 小時 → 改選 加工廠
  建設目標：加工廠
  時數：（未選）
```

`docs/discord/command-handler.md` 的 `gear_type_select` 已寫「保留當前模式」，實作不符。

## Recommended Direction

選單保留已選的值，直到玩家改動它，或它的選項因其他選單改變而重建。

```
工具強化：選 建設工具 → 鐵齒 → 無限 → 改選 採集工具
  工具類型：🌾 採集工具
  強化模式：鐵齒
  執行次數：無限

自動工具：選 建設 → 3 小時 → 改選 加工廠
  建設目標：加工廠
  時數：3 小時

鐵齒 + 無限 → 🩸 獻祭素材 100 個
  強化模式：鐵齒
  執行次數：無限

鐵齒 + 無限 → 🔮 詞條管理 → ✨ 自動抽取 → 返回詞條管理 → ← 返回
  強化模式：鐵齒
  執行次數：無限
```

- 工具強化：改工具類型時保留強化模式與執行次數。
- 自動工具：改建設目標時保留時數。
- 獻祭素材後回到工具強化畫面，保留強化模式與執行次數。
- 從詞條管理（含自動抽取設定）返回工具強化畫面，保留強化模式與執行次數。

### Alternatives

| 方向 | 結果 |
| :--- | :--- |
| A：custom_id 攜帶其他選單的值（選定） | 沿用既有慣例 |
| B：從訊息現有元件的 default 讀回其他選單的值 | 詞條管理返回時讀不到 |
| C：Cog 內以玩家 ID 暫存選擇 | 與 custom_id 狀態混用 |

- 選 A：`upgrade_mode_select:{gear_type}:{count}`、`auto_affix_*:{gear}:{target}:{value}:{source}:{scope}` 已用 custom_id 攜帶選單狀態。
- 排除 B：詞條管理畫面沒有工具強化的選單，`back_to_gear` 無處讀回模式與次數。
- 排除 C：Bot 重啟後遺失。同一玩家開多個 Ephemeral 介面時互相覆寫。同一畫面出現兩種狀態來源。

## Key Assumptions

- 玩家換工具類型時，多數沿用同一強化模式與執行次數。
- 玩家獻祭或管理詞條後，多數回到原本的強化模式與執行次數繼續強化。

## Clarifications

<!-- Q: 自動工具改建設目標時清掉時數，是否一併修？ / A: 是，兩個畫面都修。 — resolved during idea stage -->
<!-- Q: 獻祭素材與詞條管理返回後清掉模式與次數，是否納入？ / A: 納入。 — resolved during idea stage -->

## MVP Scope / Not Doing

MVP Scope:

- 工具強化畫面改工具類型保留強化模式與執行次數。
- 自動工具畫面改建設目標保留時數。
- 獻祭素材、詞條管理返回後保留強化模式與執行次數。

Not Doing:

- 自動工具改工具時，建設目標與時數選單依新工具重建。
  - 選項依工具是否運行中與可加時數而變。
- 主介面改行動時，建設目標選單依行動顯示或隱藏。
- 詞條管理改工具類型時，詞條分組選單依新工具重建。
- 從主介面開啟工具強化，以及開啟詞條管理，維持不預設選中。
- 不改 renderer 已不產生的舊路由 `extract_affix:`、`clear_affix:`。

## Architecture Decisions

- 選單狀態放在 custom_id，沿用 `upgrade_mode_select:{gear_type}:{count}` 與 `auto_affix_*` 的慣例。
- 工具強化的 `{mode}:{count}` 一律接在既有 custom_id 結尾，未選為 `none`。
  - 新格式：`gear_type_select:{mode}:{count}`、`sacrifice_material:{gear_type}:{mode}:{count}`、`modal_sacrifice:{gear_type}:{mode}:{count}`、`open_affix_mgmt:{gear_type}:{mode}:{count}`。
  - 詞條管理：`affix_gear_select`、`affix_slot_select:{gear_type}`、`affix_clear:{gear_type}:{affix_type}:{value}`、`affix_extract:{gear_type}`、`open_auto_affix:{gear_type}`、`back_to_gear:{gear_type}` 結尾加 `:{mode}:{count}`。
  - 自動抽取：`auto_affix_target/value/material/scope:{gear}:{target}:{value}:{source}:{scope}`、`auto_affix_run:{gear}:{target}:{value}:{source}:{scope}:{expected_slot}:{token}`、`back_to_affix:{gear}` 結尾加 `:{mode}:{count}`。
  - 最長 custom_id 為 `auto_affix_run:gathering:upgrade_material_refund:5:universal:all:24:abcdefgh:normal:none`，88 字元，低於 Discord 上限 100。
- `actions.py` 新增一個 `{mode}:{count}` 解析函式，所有路由共用。
  - `mode` 必須在 `_VALID_UPGRADE_MODES | {"none"}`，`count` 必須在 `_VALID_UPGRADE_COUNTS | {"none"}`。
  - 不合法時忽略該互動，與既有不合法 custom_id 的處理一致。
- `gear_type_select`、`affix_gear_select` 從 `_OWN_DROPDOWNS` 移到 `_OWN_DROPDOWN_PREFIXES`（`gear_type_select:`、`affix_gear_select:`）。
- 部署前渲染、仍是舊格式的 custom_id 一律忽略，比照 2026-10-07 `affix_clear` 改格式的處理。
- `_render_gear` 在 `gear_type is None` 時也把 `mode`、`count` 傳給 `build_gear_components`，讓 `back_to_gear:none:{mode}:{count}` 保留兩者。
- `_render_affix`、`_render_auto_affix` 新增 `mode`、`count` 參數，原樣傳給 renderer。
- 自動工具：`auto_tool_target_select:{tool}:{delta}`，`delta` 為已選有號時數或 `none`。
  - handler 以 `int()` 解析 `delta`，失敗時忽略該互動，與 `auto_tool_add_select` 一致。
  - 範圍檢查沿用 renderer 既有的確認按鈕 disabled 規則。

## Tasks

Dependency graph:

```
Task 1 (gear screen: gear_type_select + sacrifice)
└── Task 3 (affix screen round trip)
    └── Task 4 (auto-affix screen round trip)
Task 2 (auto-tool target keeps delta)
```

所有 Task 都改 `src/cogs/ui_renderer.py` 與 `src/cogs/actions.py`，依序執行。Task 2 邏輯上與其他 Task 獨立。

- [ ] Task 1: Keep mode and count when changing tool type or sacrificing
  - Files: `src/cogs/ui_renderer.py`, `src/cogs/actions.py`, `tests/test_discord_commands.py`.
  - Scope: `build_gear_components` (`gear_type_select`, `sacrifice_material`), `_render_gear` (`gear_type is None` path), `_OWN_DROPDOWNS`/`_OWN_DROPDOWN_PREFIXES`, the `{mode}:{count}` parser, `gear_type_select:` dropdown route, `sacrifice_material:` button route, `modal_sacrifice:` modal route.
  - Acceptance criteria:
    - `build_gear_components("building", "risky", ..., count="inf")` renders `gear_type_select:risky:inf` and `sacrifice_material:building:risky:inf`; with no mode and count it renders `gear_type_select:none:none`.
    - `on_dropdown` with `gear_type_select:risky:inf` and value `gathering` renders the 鐵齒 option and the 無限 option as default and renders `attempt_upgrade:gathering:risky:inf`.
    - `on_dropdown` with `gear_type_select:none:none` and value `gathering` renders no default mode or count option.
    - `on_dropdown` with `gear_type_select:bogus:inf` does not render.
    - Clicking `sacrifice_material:building:risky:inf` opens a modal with custom_id `modal_sacrifice:building:risky:inf`.
    - Submitting `modal_sacrifice:building:risky:inf` with a valid amount renders `attempt_upgrade:building:risky:inf` and the 鐵齒 and 無限 options as default.
    - `uv run python -m pytest` passes.
- [ ] Task 2: Keep the selected hours when changing the auto-tool build target
  - Files: `src/cogs/ui_renderer.py`, `src/cogs/actions.py`, `tests/test_discord_commands.py`.
  - Parallel: logically independent of Tasks 1, 3, 4; runs sequentially because the files overlap.
  - Scope: `build_auto_tool_components` target select custom_id, `auto_tool_target_select:` dropdown route.
  - Acceptance criteria:
    - `build_auto_tool_components` for an idle `building` tool with `selected_delta=3` renders `auto_tool_target_select:building:3`; with no delta it renders `auto_tool_target_select:building:none`.
    - `on_dropdown` with `auto_tool_target_select:building:3` and value `workshop` renders the `3 小時` option as default and renders `auto_tool_confirm:building:3:workshop` enabled.
    - `on_dropdown` with `auto_tool_target_select:building:none` and value `workshop` renders no default hours option and a disabled `auto_tool_confirm:none`.
    - `on_dropdown` with `auto_tool_target_select:building:abc` does not render.
    - `uv run python -m pytest` passes.
- [ ] Task 3: Carry mode and count through the affix management screen
  - Files: `src/cogs/ui_renderer.py`, `src/cogs/actions.py`, `tests/test_discord_commands.py`.
  - Depends on: Task 1.
  - Scope: `build_gear_components` (`open_affix_mgmt`), `build_affix_components` (all six custom_ids), `_render_affix`, routes `open_affix_mgmt:`, `affix_gear_select:`, `affix_slot_select:`, `affix_extract:`, `affix_clear:`, `back_to_gear:`; route `open_auto_affix:` accepts `open_auto_affix:{gear_type}:{mode}:{count}`.
  - Acceptance criteria:
    - `build_affix_components("gathering", ..., mode="risky", count="inf")` renders `affix_gear_select:risky:inf`, `affix_slot_select:gathering:risky:inf` (when affixes exist), `affix_clear:gathering:none:none:risky:inf`, `affix_extract:gathering:risky:inf`, `open_auto_affix:gathering:risky:inf`, `back_to_gear:gathering:risky:inf`.
    - Round trip: `open_affix_mgmt:building:risky:inf` → `affix_gear_select:risky:inf` value `gathering` → `affix_extract:gathering:risky:inf` → `back_to_gear:gathering:risky:inf`, each step dispatched with the custom_id rendered by the previous step, ends on a gear screen with the 鐵齒 and 無限 options as default and `attempt_upgrade:gathering:risky:inf`.
    - `back_to_gear:none:risky:inf` renders a gear screen with no tool type selected and the 鐵齒 and 無限 options as default.
    - `affix_clear:gathering:efficiency:3:risky:inf` clears the highest slot of that group, as before.
    - `back_to_gear:gathering:bogus:inf` does not render.
    - `uv run python -m pytest` passes.
- [ ] Task 4: Carry mode and count through the auto-affix screen
  - Files: `src/cogs/ui_renderer.py`, `src/cogs/actions.py`, `tests/test_discord_commands.py`.
  - Depends on: Task 3.
  - Scope: `build_auto_affix_components` (`state_id`, confirm ID, `back_to_affix`), `_render_auto_affix`, routes `open_auto_affix:`, `auto_affix_target/value/material/scope:`, `auto_affix_run:` (every render path), `back_to_affix:`.
  - Acceptance criteria:
    - `build_auto_affix_components` with `mode="risky"`, `count="inf"` renders `auto_affix_target:gathering:none:none:none:none:risky:inf`, `back_to_affix:gathering:risky:inf`, and a confirm ID ending in `:{expected_slot}:{token}:risky:inf`.
    - Round trip: `open_auto_affix:gathering:risky:inf` → `auto_affix_target:...:risky:inf` value `any` → `back_to_affix:gathering:risky:inf` → `back_to_gear:gathering:risky:inf`, each step dispatched with the custom_id rendered by the previous step, ends on a gear screen with the 鐵齒 and 無限 options as default.
    - A completed `auto_affix_run` with `:risky:inf` renders an affix screen whose `back_to_gear` is `back_to_gear:gathering:risky:inf`.
    - The registered confirmation ID still has to match exactly; a run ID with a changed `{mode}` is rejected like any other altered ID.
    - `uv run python -m pytest` passes.

## Review Issues

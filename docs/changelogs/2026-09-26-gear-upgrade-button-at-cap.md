---
title: "工具滿級時主介面強化工具按鈕維持可用"
status: Draft
created: 2026-09-26
doc_type: change
last_reviewed: 2026-09-26
source_paths:
  - src/cogs/ui_renderer.py
  - tests/test_discord_commands.py
  - docs/discord/ui-renderer.md
scope: "Tracks keeping the main gear upgrade button enabled at gear cap, from design through review."
---

## Problem Statement

四種工具都達研究所等級上限時，主介面 `🔨 強化工具`（`open_gear_upgrade`）被 disabled。工具強化子選單是 `🔮 詞條管理` 與 `🩸 獻祭素材` 的唯一入口，因此滿級玩家無法抽取或清除詞條，也無法獻祭素材。

程式 `src/cogs/ui_renderer.py` 的 `all_gear_at_cap` 條件與 `docs/discord/ui-renderer.md` 的「強化工具」禁用條件一致。問題出在規格：兩條規則合併後鎖死入口。

## Recommended Direction

移除主介面 `🔨 強化工具` 的滿級禁用條件，按鈕永遠可點。子選單的 `🎲 強化工具` 保留自身「已達上限」禁用條件，工具類型 Dropdown 也顯示 `已達等級上限 Lv{cap}`，玩家不會誤以為能強化。

排除在主介面 Row 1 新增 `🔮 詞條管理` 按鈕：需新增 handler 與流程，入口變成兩處，且 `🩸 獻祭素材` 仍被鎖。

排除將主按鈕改為「滿級且無詞條槽時才 disabled」：條件更複雜，獻祭素材仍可能被鎖，收益低。

## Clarifications
<!-- Q: 採用哪個方向？ / A: 主按鈕永遠可用；子選單 🎲 強化工具 維持滿級 disabled。 — resolved during bug analysis -->

## MVP Scope / Not Doing

範圍內：

- 移除主介面 `open_gear_upgrade` 按鈕的滿級禁用條件。
- 更新 `docs/discord/ui-renderer.md` 的禁用條件描述。
- 將滿級測試改為斷言按鈕可用。

範圍外：

- 不修改子選單 `🎲 強化工具`、`🩸 獻祭素材`、`🔮 詞條管理` 的禁用條件。
- 不新增主介面按鈕。

## Key Assumptions

- 滿級玩家開啟子選單後，能從禁用的 `🎲 強化工具` 與 Dropdown 描述理解已達上限，不會回報為新 bug。
- 滿級玩家確實有使用詞條管理與獻祭素材的需求。

## Architecture Decisions

## Tasks

## Review Issues

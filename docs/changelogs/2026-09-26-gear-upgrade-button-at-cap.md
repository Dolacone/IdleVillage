---
title: "工具滿級時主介面強化工具按鈕維持可用"
status: In-Progress
created: 2026-09-26
doc_type: change
last_reviewed: 2026-09-26
source_paths:
  - src/cogs/ui_renderer.py
  - tests/test_discord_commands.py
  - src/cogs/actions.py
  - docs/discord/ui-renderer.md
scope: "Tracks keeping the main gear upgrade button enabled at gear cap, from design through review."
---

## Problem Statement

四種工具都達研究所等級上限時，主介面 `🔨 強化工具`（`open_gear_upgrade`）被 disabled。工具強化子選單是 `🔮 詞條管理` 與 `🩸 獻祭素材` 的唯一入口，因此滿級玩家無法抽取或清除詞條，也無法獻祭素材。

程式 `src/cogs/ui_renderer.py` 的 `all_gear_at_cap` 條件與 `docs/discord/ui-renderer.md` 的「強化工具」禁用條件一致。問題出在規格：兩條規則合併後鎖死入口。

## Recommended Direction

移除主介面 `🔨 強化工具` 的滿級禁用條件，按鈕永遠可點。子選單的 `🎲 強化工具` 保留自身「已達上限」禁用條件，工具類型 Dropdown 也顯示 `已達等級上限 Lv{cap}`。

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
- 不修改 `build_gear_embed` 滿級預覽：選定滿級工具時仍顯示 `Lv{cap} → Lv{cap+1}` 與成功率。任一工具滿級、其他未滿時，玩家現在已能看到這個畫面，不是本變更引入的行為，另開變更處理。

## Key Assumptions

- 滿級玩家開啟子選單後，能從禁用的 `🎲 強化工具` 與 Dropdown 描述 `已達等級上限 Lv{cap}` 理解已達上限；embed 的 `Lv{cap} → Lv{cap+1}` 預覽不會被回報為新 bug。
- 滿級玩家確實有使用詞條管理與獻祭素材的需求。

## Architecture Decisions

- 只改 renderer：`src/cogs/actions.py` 的 `open_gear_upgrade` handler 沒有滿級防護，直接呼叫 `_render_gear`，不需修改。
- 滿級強化有兩層防護，皆維持原樣：`gear_manager.get_upgrade_info` 在滿級時回傳 `can_attempt=False`，使子選單 `🎲 強化工具` disabled；`gear_manager.attempt_upgrade` 在滿級時 raise ValueError。

## Tasks

```
Task 1 (renderer + test)  -- 無相依，單一 task
```

- [x] Task 1: 移除 `build_main_components` 的 `all_gear_at_cap` 計算與 `open_gear_upgrade` 按鈕的 `disabled` 參數；測試 `test_gear_upgrade_enabled_when_all_gear_at_cap` 斷言滿級時按鈕可用。
  - Files: `src/cogs/ui_renderer.py`, `tests/test_discord_commands.py`
  - 新增 `TestRendererGearComponents` 測試：四種工具 Lv5、`gear_cap=5`、`can_attempt=False`、`max_slots=1`、`materials=3`，選定 `gathering` 與 `normal` 時 `🎲 強化工具` disabled，`🩸 獻祭素材` 與 `🔮 詞條管理` enabled。
  - 移除 `test_gear_upgrade_enabled_when_all_gear_at_cap` 的 `currently fails due to bug` 註解。
  - Acceptance: `uv run python -m pytest tests/test_discord_commands.py -k "gear_upgrade or GearComponents" -q` 全部通過；全套測試通過。

## Review Issues

## Plan Review Issues

- [x] `Architecture Decisions` 稱子選單按鈕是「唯一的滿級強化防護」，但 `src/managers/gear_manager.py` 的 `get_upgrade_info` 會在滿級時設定 `can_attempt=False`，`attempt_upgrade` 也會拒絕滿級強化；修正防護層描述。
- [x] 選定滿級工具後，`build_gear_embed` 仍顯示 `Lv{cap} → Lv{cap+1}`、成功率與升級消耗，與計畫「玩家不會誤以為能強化」的假設衝突；決定滿級預覽的顯示規則，並將對應驗證列入 Task 1。
- [x] Task 1 的滿級測試使用 Lv2，尚未解鎖詞條槽，且只檢查主按鈕；加入已解鎖詞條槽且持有素材的滿級情境，驗證選定工具後 `🎲 強化工具` 禁用、`🩸 獻祭素材` 與 `🔮 詞條管理` 可用。
- [x] `tests/test_discord_commands.py` 的未提交測試含 `currently fails due to bug` 註解；Task 1 完成後此敘述失效，須將移除該註解列入任務。

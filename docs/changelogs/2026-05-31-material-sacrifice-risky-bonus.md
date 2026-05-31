---
title: "素材獻祭換取永久成功率加成"
status: Ready-to-implement
created: 2026-05-31
doc_type: change
last_reviewed: 2026-05-31
source_paths:
  - src/managers/gear_manager.py
  - tests/test_gear_manager.py
  - docs/managers/gear-manager.md
scope: "新增按鈕讓玩家直接消耗素材換取 risky_failed_levels，效果等同於鐵齒失敗的永久成功率加成，不消耗 AP，不發送公告。"
---

## Problem Statement

`risky_failed_levels` 永久成功率加成目前只能透過鐵齒強化失敗取得，代價是工具等級歸零。玩家若不願冒工具歸零風險，完全無法主動累積此加成。需要一條無風險路徑讓玩家以素材換取永久成功率。

## Recommended Direction

在工具強化子選單新增「🩸 獻祭素材」按鈕。玩家選定素材類型後，輸入投入數量（1 ~ 持有上限），確認後：

- 消耗所選類型素材 N 個
- `risky_failed_levels += N`（效果等同於在任意等級鐵齒失敗 N 次各 1 級的加成總和）
- 不消耗 AP
- 不發送 Public 通知，僅更新個人介面

選方向 A（1 材料 = +1 risky_failed_levels）而非等效等級模擬或固定批次，因為直接換算最透明，玩家能完全預測「花多少得多少」。材料稀缺性（僅靠週期結算掉落）天然限制濫用。

選「自由選擇任一素材類型」而非四種等量消耗，因為玩家可能四種素材庫存不均衡，不應因某種素材不足而卡住。

## Clarifications

Q: 素材類型選擇？
A: 自由選擇任一類型。

Q: 投入數量如何輸入？
A: 透過 Discord Modal 彈出輸入框，玩家輸入 1~持有數量的整數。

## MVP Scope / Not Doing

做：
- 工具強化子選單新增「🩸 獻祭素材」按鈕
- 點擊後彈出 Modal（選素材類型 + 輸入數量）
- 驗證素材足夠後扣除素材、`risky_failed_levels += N`
- 介面回饋：更新強化子選單 embed（含新 risky_failed_levels 數值）
- 無 AP 消耗、無 Public 通知

不做：
- 多種素材同時投入（單次選一種）
- 獻祭歷史記錄
- 獻祭量上限或每日限制

## Key Assumptions

- Discord Modal 最多 5 個 TextInput，本需求只需 1 個（數量），素材類型透過當前選擇的 gear_type 決定（玩家先切換工具類型再點獻祭）

## Architecture Decisions

1. **新增 `sacrifice_material(db, user_id, gear_type, amount, now)`** 於 `gear_manager.py`：
   - 驗證 amount >= 1 且 materials[gear_type] >= amount，否則 raise ValueError
   - 扣除 materials[gear_type] by amount
   - 呼叫既有 `_add_risky_failed_levels(db, user_id, amount, now)`
   - 回傳 `{"type": "sacrifice", "sacrificed": amount, "gear_type": gear_type, "risky_failed_levels_after": int}`
   - 不消耗 AP，不觸發任何 notification event

2. **按鈕放置**：在 `build_gear_components()` Row 3 加入 `🩸 獻祭` 按鈕（與 🎲 強化、← 返回 同列）。custom_id: `sacrifice_material:{gear_type}`。禁用條件：materials == 0。

3. **Modal 流程**：
   - 點擊按鈕 → 查詢 DB 取得持有量 → `inter.response.send_modal()`（不可 defer）
   - Modal title: `🩸 獻祭素材`，TextInput label: `投入 {mat_label}（持有：{holdings}）`，placeholder: `1 ~ {holdings}`
   - custom_id: `modal_sacrifice:{gear_type}`
   - `on_modal_submit` listener 加入 `actions.py`（沿用 general.py 的前綴過濾模式）

4. **Embed 結果顯示**：`build_gear_embed()` 在 `result["type"] == "sacrifice"` 時附加：`\n🩸 獻祭完成！消耗 {n} 個 {mat_label}，鐵齒加成 +{bonus}%`

5. **素材類型選擇 via 現有 UI**：玩家在工具類型 Dropdown 選擇目標工具後點獻祭，素材類型與所選工具一致。不需要新 Dropdown，符合「自由選擇任一類型」（切換工具即切換素材類型）。

## Tasks

- [x] Task 1: `gear_manager.py` — 新增 `sacrifice_material()` 公開函式，加入 `tests/test_gear_manager.py` 三個測試（正常扣除、素材不足拒絕、risky_failed_levels 正確累加）；更新 `docs/managers/gear-manager.md` 操作介面區段
  - Files: `src/managers/gear_manager.py`, `tests/test_gear_manager.py`, `docs/managers/gear-manager.md`
  - Acceptance: 函式存在；扣除素材；increment risky_failed_levels；ValueError on insufficient；AP 不變；三個測試通過

- [ ] Task 2: `ui_renderer.py` — `build_gear_components()` Row 3 新增 `🩸 獻祭` 按鈕（disabled when materials==0）；`build_gear_embed()` 新增 sacrifice 結果顯示分支；更新 `docs/discord/ui-renderer.md`；在 `tests/test_discord_commands.py` 或新增 `tests/test_ui_renderer.py` 測試 materials=0 時按鈕 disabled
  - Files: `src/cogs/ui_renderer.py`, `docs/discord/ui-renderer.md`
  - Depends on: Task 1（result dict 結構）
  - Acceptance: 按鈕出現於 Row 3；materials=0 時禁用；result 為 sacrifice 時顯示正確訊息；至少一個測試驗證 disabled 行為

- [ ] Task 3: `actions.py` — 新增 `sacrifice_material:{gear_type}` 到 `_OWN_BUTTON_PREFIXES`；`on_button_click` 處理 sacrifice 按鈕（查 DB 取 holdings → send_modal）；新增 `on_modal_submit` listener 處理 `modal_sacrifice:{gear_type}`（呼叫 gear_manager.sacrifice_material → _render_gear with result，非整數輸入 / 素材不足均以 error result 回應）；在 `tests/test_discord_commands.py` 補充 modal submit 邏輯測試
  - Files: `src/cogs/actions.py`
  - Depends on: Task 1, Task 2
  - Acceptance: 點按鈕彈 Modal；提交 Modal 扣素材並刷新 gear embed；無 AP 消耗；無 announcement；非整數 / 素材不足以 error 顯示；至少一個測試驗證 modal submit 路徑

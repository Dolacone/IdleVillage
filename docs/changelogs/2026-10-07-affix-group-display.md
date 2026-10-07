---
title: "詞條分組顯示"
status: Draft
created: 2026-10-07
doc_type: change
last_reviewed: 2026-10-07
source_paths:
  - src/cogs/ui_renderer.py
  - src/cogs/actions.py
  - tests/test_discord_commands.py
  - docs/discord/ui-renderer.md
  - docs/discord/command-handler.md
  - docs/README.md
scope: "Tracks this change from design through review."
---

## Problem Statement

詞條管理畫面的槽位下拉每個現存詞條一個選項。Discord 下拉上限 25 個選項；工具有 26 條以上詞條時，Discord 拒絕整個畫面更新，玩家停在「請選擇工具類型」，無法進入該工具的詞條管理。正式環境 2026-10-07 快照有 4 把工具剛好 26 條詞條。逐槽清單同時讓玩家看到每個槽號與每個空槽，詞條多時畫面很長。

## Recommended Direction

詞條管理畫面改以「類型 + 數值」分組顯示，玩家不再看到槽號與逐槽空槽：

```
詞條槽（14/24）
週期縮短（+5%） x 10
週期縮短（+4%） x 1
週期縮短（+3%） x 3
空槽 x 10
```

清除下拉改為每組一個選項，選定一組後清除該組其中一條詞條。

替代方向：

- 分頁：每頁 25 個槽位選項，加翻頁按鈕，比照試煉目標選單。保證不超過上限，但保留槽號，詞條多時要翻頁，畫面也沒變短。不採用，原因是使用者要求移除槽號與逐槽項目。
- 兩層下拉：先選類型、再選數值。保證不超過上限，但每次清除多一次選擇並多佔一列元件。不採用，原因是正式環境每把工具最多 2 組，分組加截斷已足夠。

選擇分組的原因：槽位彼此可互換，抽取只填第一個空槽，清除同組任一條效果相同；分組同時修好 bug 並縮短畫面。

## Clarifications

- Q: 「詞條合計」區塊要保留嗎？ / A: 保留，與分組清單並列。
- Q: 分組超過 25 組時怎麼辦？ / A: 下拉依數值由低到高取前 25 組，placeholder 提示未列出的組數。
- Q: 分組清單排序？ / A: 依詞條名稱對照表的類型順序，同類型數值由高到低；空槽排最後。
- Q: 空槽名稱用「空格」還是「空槽」？ / A: 沿用「空槽」。

## MVP Scope / Not Doing

MVP Scope:

- 詞條管理 Embed 的逐槽清單改為分組清單，`詞條槽（{used}/{max_slots}）` 標頭保留。
- 槽位下拉改為分組下拉，超過 25 組時截斷。
- 清除按鈕與 handler 改以分組識別要清除的詞條。
- 即將清除提示改用分組格式，不顯示槽號。
- 更新 `docs/discord/ui-renderer.md` 與 `docs/discord/command-handler.md`。

Not Doing:

- 一次清除多條詞條。
- 工具強化子選單：已只顯示合計，不含槽號，維持不變。
- Public 通知：不含槽號，維持不變。
- `gear_affixes` 資料表與 `slot_index` 欄位：內部仍以槽位儲存。

## Key Assumptions

- 實際分組數遠低於 25；正式環境 2026-10-07 每把工具最多 2 組。截斷只是防線，上線後需確認沒有玩家碰到截斷。
- 玩家不需要知道槽號；抽取與清除行為不因看不到槽號而改變判斷。

## Architecture Decisions

- 分組鍵為 `(affix_type, value)`，以字串 `{affix_type}:{value}` 放進下拉選項 value 與清除按鈕 custom_id。7 種類型皆不含 `:`，可安全切分。
- 分組與排序由 `ui_renderer.py` 的單一 helper 產生，Embed 分組清單與下拉共用，避免兩處排序不一致。排序：`AFFIX_TYPE_LABELS` 順序，同類型 `value` 由高到低。
- 下拉截斷：分組數大於 25 時，以 `(value, 類型順序)` 由小到大取前 25 組，再依分組清單順序輸出；placeholder 顯示未列出組數。
- renderer 參數 `selected_slot: int | None` 改為 `selected_group: tuple[str, int] | None`，`build_affix_embed` 與 `build_affix_components` 一致。
- 清除時由 handler（`actions.py`）以 `affix_manager.get_affixes` 找出符合分組、`slot_index` 最大的一條，再呼叫既有 `affix_manager.clear_affix(slot_index)`。affix-manager 介面與 `gear_affixes` 資料表不變。取最大槽號讓下一次抽取填回同一位置之前的空槽，不影響玩家可見行為。
- 分組不存在（按鈕過期、已被清除）時 handler 不清除、不發通知，只重新渲染。
- `affix_slot_select` 與 `affix_clear` 的 custom_id 前綴不變，`_OWN_BUTTON_PREFIXES` / `_OWN_DROPDOWN_PREFIXES` 不需調整。

## Tasks

依賴關係：

```
Task 1 (ui_renderer.py) -> Task 2 (actions.py)
```

兩個 task 依序執行，不可平行：Task 2 呼叫 Task 1 改名後的 `selected_group` 參數。

- [ ] Task 1: renderer 改為分組顯示（`src/cogs/ui_renderer.py`，測試 `tests/test_discord_commands.py`）
  - 新增分組 helper；`_build_affix_section` 輸出 `詞條槽（{used}/{max_slots}）`、分組行 `{affix_label}（+{value}%） x {count}`、有空槽時最後一行 `空槽 x {empty}`；不再輸出 `槽 {n}:`。
  - `build_affix_embed` / `build_affix_components` 的 `selected_slot` 改為 `selected_group`；即將清除提示為 `即將清除：{affix_label}（+{value}%）`。
  - 分組下拉選項 label `{affix_label}（+{value}%） x {count}`、value `{affix_type}:{value}`、無 description；選定分組時該選項 default。超過 25 組依 Architecture Decisions 截斷並設定 placeholder。
  - 清除按鈕 custom_id 為 `affix_clear:{gear}:{affix_type}:{value}`，未選定時 `affix_clear:{gear}:none:none` 且 disabled。
  - AC：26 條同類型同數值詞條時，下拉只有 1 個選項 `週期縮短（+5%） x 26`（工作區既有未 commit 的測試 `test_affix_components_with_26_filled_slots_fit_discord_select_limit` 須保留並通過）。
  - AC：範例 10/1/3 條週期縮短 +5/+4/+3、24 槽時，Embed 依序含 `週期縮短（+5%） x 10`、`週期縮短（+4%） x 1`、`週期縮短（+3%） x 3`、`空槽 x 10`，且不含 `槽 `。
  - AC：30 組分組時下拉剛好 25 個選項，不含 5 組數值最高的分組，placeholder 為 `選擇要清除的詞條...（另有 5 組未列出）`。
  - AC：既有斷言槽號格式的測試改為新格式。
- [ ] Task 2: handler 改以分組清除（`src/cogs/actions.py`，測試 `tests/test_discord_commands.py`）
  - `_render_affix` 參數改為 `selected_group`。
  - `affix_slot_select` 解析 `{affix_type}:{value}`；類型不在 `_VALID_AFFIX_TYPES` 或數值不是 1-5 整數時忽略。
  - `affix_clear` 解析 `affix_clear:{gear}:{affix_type}:{value}`；不合法時忽略；合法時在 `_execute_clear_affix` 找出該分組槽號最大的一條並呼叫 `affix_manager.clear_affix`。
  - AC：同分組有槽 0、3、5 三條時，按清除後只剩槽 0、3，並發出一次 `affix_cleared` 事件，內容為該分組的類型與數值。
  - AC：分組已不存在時不清除、不扣素材、不發事件，畫面重新渲染。
  - AC：既有 `affix_clear:gathering:0` 格式的 handler 測試改為分組格式。
- [ ] Task 3: 端對端驗證
  - 以本地 bot 載入正式環境快照 `bak/village.db.26100715`，開啟 26 條詞條工具的詞條管理畫面，記錄畫面成功開啟與分組清單內容。
  - 若無法在本地連 Discord，改用快照資料呼叫 `_render_affix` 等價流程產生的 embed/components payload，並記錄無法端對端的原因。

## Plan Review Issues

- [ ] Issue 1: 舊路由 `clear_affix:{gear_type}:{slot_index}`（`actions.py` 第 582 行，在 `_OWN_BUTTON_PREFIXES`，有 `test_clear_affix_dispatches_affix_cleared_event` 與 `test_clear_affix_no_dispatch_on_failure` 兩個測試）也呼叫 `_execute_clear_affix(inter, gear_type, slot_index)`。Task 2 把分組查找放進 `_execute_clear_affix` 會破壞這條路由，計畫完全沒提。修正：Architecture Decisions 寫明 `_execute_clear_affix` 維持以 `slot_index` 清除、舊路由不變；分組轉槽號放在 `affix_clear` 分支（或新 helper，與清除共用同一個 DB 連線）；Task 2 加 AC「`clear_affix:gathering:0` 兩個既有測試不修改仍通過」。
- [ ] Issue 2: Task 1 第二條 AC 要求 Embed 含 `空槽 x 10` 又要求「不含 `槽 `」，但 `空槽 x 10` 本身含子字串 `槽 `，AC 無法同時成立。修正：改為「不符合正規式 `槽 \d`，且不含 `即將清除：槽`」。
- [ ] Issue 3: Task 1 第一條 AC 的選項 `週期縮短（+5%） x 26` 與它引用的未 commit 測試 fixture 不一致：該測試用 `efficiency` 數值 1，預期 label 是 `行動效率（+1%） x 26`，且該測試只斷言選項數不超過 25。修正：AC 改為 `行動效率（+1%） x 26`，並要求在該測試補斷言「分組下拉剛好 1 個選項、label 為 `行動效率（+1%） x 26`、value 為 `efficiency:1`」。
- [ ] Issue 4: Task 1 截斷 AC「不含 5 組數值最高的分組」在同數值平手時不確定，也沒檢查輸出順序。修正：指定 fixture 為 7 種類型各有數值 1-4（28 組）加 `efficiency:5`、`material_drop:5`（共 30 組）；AC 斷言下拉 25 個選項、排除 `efficiency:5`、`material_drop:5`、`upgrade_ap_refund:4`、`upgrade_material_refund:4`、`cycle_time_reduce:4`、選項順序與分組清單相同（類型順序，同類型數值由高到低）、placeholder 為 `選擇要清除的詞條...（另有 5 組未列出）`。
- [ ] Issue 5: Task 1 把 renderer 參數改名為 `selected_group`，但 `actions.py` 的 `_render_affix` 仍傳 `selected_slot=`；Task 1 commit 後每次開詞條管理畫面都會 `TypeError`。所有 handler 測試都 patch `_render_affix`，沒有測試跑真實的 `_render_affix`，兩個 task 的測試都抓不到參數接線錯誤。修正：Task 2 加 AC「以 mock 的 DB 與 manager 執行真實 `_render_affix(inter, "gathering", selected_group=("efficiency", 3))`，斷言輸出的清除按鈕 custom_id 為 `affix_clear:gathering:efficiency:3` 且未 disabled」；或讓 Task 1 同時改 `_render_affix` 的轉傳（仍在 2 個 source 檔上限內）。
- [ ] Issue 6: Task 3 端對端不可照寫執行：快照裡 26 條詞條的工具屬於其他玩家的 `user_id`，本地測試帳號開不到該工具；直接用 `bak/village.db.26100715` 清除詞條會改寫快照；也沒有清除流程的可觀察輸出。修正：步驟寫明「複製快照到 scratch 路徑，`DATABASE_PATH` 指向副本，在副本中把一把 26 條詞條工具的 `gear_affixes` 與 `players` 列改到測試帳號的 `user_id`」；每條 AC 一個可觀察輸出：畫面成功開啟並顯示分組清單、選一組按清除後該組數量減 1 且 Public 通知出現 `清除詞條：{affix_label}（+{value}%）`。fallback 必須呼叫真實 `_render_affix`（不是等價流程），斷言下拉選項數不超過 25，並註明「Discord 是否接受 payload 未驗證」。
- [ ] Issue 7: `docs/discord/command-handler.md` 的 `affix_clear` 列沒寫不合法輸入的處理，與同表 `affix_slot_select` 列及 Task 2「不合法時忽略」不一致；`none:none` 與部署前舊格式 `affix_clear:{gear}:{slot}` 都會走到這裡。修正：該列補「類型不在合法類型或數值不是 1-5 整數時（含 `none:none` 與舊格式）忽略」。

## Review Issues

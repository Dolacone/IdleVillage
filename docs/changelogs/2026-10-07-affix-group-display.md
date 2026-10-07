---
title: "詞條分組顯示"
status: Reviewed
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
- 兩層下拉：先選類型、再選數值。保證不超過上限，但每次清除多一次選擇並多佔一列元件。不採用，原因是正式環境 26 條詞條的工具各 2 組、全部工具最多 8 組，分組加截斷已足夠。

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

- 實際分組數遠低於 25；正式環境 2026-10-07 26 條詞條的工具各 2 組，全部工具最多 8 組。截斷只是防線，上線後需確認沒有玩家碰到截斷。
- 玩家不需要知道槽號；抽取與清除行為不因看不到槽號而改變判斷。

## Architecture Decisions

- 分組鍵為 `(affix_type, value)`，以字串 `{affix_type}:{value}` 放進下拉選項 value 與清除按鈕 custom_id。7 種類型皆不含 `:`，可安全切分。
- 分組與排序由 `ui_renderer.py` 的單一 helper 產生，Embed 分組清單與下拉共用，避免兩處排序不一致。排序：`AFFIX_TYPE_LABELS` 順序，同類型 `value` 由高到低。
- 下拉截斷：分組數大於 25 時，以 `(value, 類型順序)` 由小到大取前 25 組，再依分組清單順序輸出；placeholder 顯示未列出組數。
- renderer 參數 `selected_slot: int | None` 改為 `selected_group: tuple[str, int] | None`，`build_affix_embed` 與 `build_affix_components` 一致。
- 清除時由 `affix_clear` 分支以 `affix_manager.get_affixes` 找出符合分組、`slot_index` 最大的一條，再呼叫既有 `_execute_clear_affix(inter, gear_type, slot_index)`。`_execute_clear_affix` 維持以 `slot_index` 清除，舊路由 `clear_affix:{gear_type}:{slot_index}` 行為不變。affix-manager 介面與 `gear_affixes` 資料表不變。同組詞條可互換，清除哪一條不影響玩家可見行為。
- 分組不存在（按鈕過期、已被清除）時 handler 不清除、不發通知，只重新渲染。
- `affix_slot_select` 與 `affix_clear` 的 custom_id 前綴不變，`_OWN_BUTTON_PREFIXES` / `_OWN_DROPDOWN_PREFIXES` 不需調整。

## Tasks

依賴關係：

```
Task 1 (ui_renderer.py + _render_affix 轉傳 + affix_slot_select) -> Task 2 (affix_clear 路由) -> Task 3 (端對端)
```

三個 task 依序執行，不可平行：Task 2 使用 Task 1 改名後的 `selected_group` 參數；Task 3 驗證前兩者。

- [x] Task 1: renderer 改為分組顯示（`src/cogs/ui_renderer.py`、`src/cogs/actions.py` 的 `_render_affix` 轉傳與 `affix_slot_select` 分支，測試 `tests/test_discord_commands.py`）
  - 新增分組 helper；`_build_affix_section` 輸出 `詞條槽（{used}/{max_slots}）`、分組行 `{affix_label}（+{value}%） x {count}`、有空槽時最後一行 `空槽 x {empty}`；不再輸出 `槽 {n}:`。
  - `build_affix_embed` / `build_affix_components` 的 `selected_slot` 改為 `selected_group`；即將清除提示為 `即將清除：{affix_label}（+{value}%）`。
  - `actions.py` 的 `_render_affix` 參數同步改為 `selected_group` 並轉傳給 renderer，避免 Task 1 commit 後畫面 `TypeError`。
  - `on_dropdown` 的 `affix_slot_select` 分支解析 `{affix_type}:{value}`；類型不在 `_VALID_AFFIX_TYPES` 或數值不是 1-5 整數時忽略；合法時以 `selected_group=(affix_type, int(value))` 呼叫 `_render_affix`。
  - 選定分組不在現存詞條中時，Embed 不顯示 `即將清除` 提示。
  - 分組下拉選項 label `{affix_label}（+{value}%） x {count}`、value `{affix_type}:{value}`、無 description；選定分組時該選項 default。超過 25 組依 Architecture Decisions 截斷並設定 placeholder。
  - 清除按鈕 custom_id 為 `affix_clear:{gear}:{affix_type}:{value}`，未選定時 `affix_clear:{gear}:none:none` 且 disabled。
  - AC：工作區既有未 commit 的測試 `test_affix_components_with_26_filled_slots_fit_discord_select_limit`（26 條 `efficiency` 數值 1）須保留並通過，並補斷言分組下拉剛好 1 個選項、label 為 `行動效率（+1%） x 26`、value 為 `efficiency:1`。
  - AC：範例 10/1/3 條週期縮短 +5/+4/+3、24 槽時，Embed 依序含 `週期縮短（+5%） x 10`、`週期縮短（+4%） x 1`、`週期縮短（+3%） x 3`、`空槽 x 10`，且不符合正規式 `槽 \d`。
  - AC：fixture 為 7 種類型各有數值 1-4（28 組）加 `efficiency:5`、`material_drop:5`（共 30 組）。下拉剛好 25 個選項，排除 `efficiency:5`、`material_drop:5`、`upgrade_ap_refund:4`、`upgrade_material_refund:4`、`cycle_time_reduce:4`；選項順序與分組清單相同（類型順序，同類型數值由高到低）；placeholder 為 `選擇要清除的詞條...（另有 5 組未列出）`。
  - AC：選定分組時 Embed 含 `即將清除：{affix_label}（+{value}%）` 且不含 `即將清除：槽`。
  - AC：`selected_group=("efficiency", 5)` 且 affixes 無該組時，Embed 不含 `即將清除`。
  - AC：以 mock 的 DB 與 manager 執行真實 `_render_affix(inter, "gathering", selected_group=("efficiency", 3))`，斷言輸出的清除按鈕 custom_id 為 `affix_clear:gathering:efficiency:3` 且未 disabled。
  - AC：`affix_slot_select:gathering` 選項值 `efficiency:3` 時，`_render_affix` 以 `selected_group=("efficiency", 3)`（數值為 int）被呼叫一次；選項值 `0`、`bogus:3`、`efficiency:6`、`efficiency:x` 時 `_render_affix` 未被呼叫。
  - AC：既有斷言槽號格式的測試改為新格式。
- [x] Task 2: `affix_clear` 改以分組清除（`src/cogs/actions.py`，測試 `tests/test_discord_commands.py`）
  - `affix_clear` 解析 `affix_clear:{gear}:{affix_type}:{value}`；類型不合法或數值不是 1-5 整數時（含 `none:none` 與舊格式 `affix_clear:{gear}:{slot}`）忽略；合法時在 `affix_clear` 分支找出該分組槽號最大的一條，再呼叫 `_execute_clear_affix(inter, gear_type, slot_index)`。
  - AC：同分組有槽 0、3、5 三條時，按清除後只剩槽 0、3，並發出一次 `affix_cleared` 事件，內容為該分組的類型與數值。
  - AC：分組已不存在時不清除、不扣素材、不發事件，畫面重新渲染。
  - AC：既有 `affix_clear:gathering:0` 格式的 handler 測試改為分組格式。
  - AC：舊路由 `clear_affix:gathering:0` 的兩個既有測試（`test_clear_affix_dispatches_affix_cleared_event`、`test_clear_affix_no_dispatch_on_failure`）不修改仍通過。
- [x] Task 3: 端對端驗證（不改 source）
  - 本地 `.env` 的 `DISCORD_TOKEN` 是正式 bot token（Dockerfile 把 `.env` 打包進映像檔）。本地啟動 bot 會與正式 bot 同時接收玩家互動，因此不在本地連 Discord。
  - 複製 `bak/village.db.26100715` 到 scratch 路徑，`DATABASE_PATH` 指向副本，不改動快照本身。
  - 用副本資料與 mock interaction 呼叫真實 `Actions._render_affix`，目標為一把 26 條詞條的工具（快照中 `user_id` 1209024021207982101 的 `gathering`）。可觀察輸出：embed description 含分組清單、每個下拉選項數不超過 25。
  - 再以 `affix_clear:{gear}:{affix_type}:{value}` 走真實 `on_button_click` 分支一次（`notification.dispatch_events` 以 mock 擷取事件）。可觀察輸出：該組數量減 1，擷取到一個 `affix_cleared` 事件，其類型與數值等於所選分組。
  - 在 change document 記錄：Discord 是否接受 payload 未驗證，需上線後人工確認。
  - 執行結果（2026-10-07）：
    - 指令：`uv run python <scratchpad>/e2e/run.py`（腳本在 scratch，不在 repo；`DATABASE_PATH` 與 `schema.DB_PATH` 指向快照副本，其餘設定取 `tests.support.ALL_TEST_ENV`，未啟動 bot、未連 Discord）。
    - 分組清單：`詞條槽（26/26）`、`素材掉落（+5%） x 8`、`週期縮短（+5%） x 18`。
    - 下拉選項數：`affix_gear_select options = 4`、`affix_slot_select:gathering options = 2`，皆不超過 25。
    - 清除前：`cycle_time_reduce` 5 共 18 條，`material_drop` 5 共 8 條（合計 26）。兩組數值皆為 5，選定 `cycle_time_reduce:5`。
    - 事件：`{'type': 'affix_cleared', 'user_display_name': 'tester', 'gear_type': 'gathering', 'affix_type': 'cycle_time_reduce', 'value': 5}`，僅 1 個。
    - 清除後：`cycle_time_reduce` 5 共 17 條（減 1），`material_drop` 5 仍 8 條；Embed 顯示 `週期縮短（+5%） x 17`、`空槽 x 1`。
    - Discord 是否接受 payload 未驗證，需上線後人工確認。

## Plan Review Issues

- [x] Issue 1: 舊路由 `clear_affix:{gear_type}:{slot_index}`（`actions.py` 第 582 行，在 `_OWN_BUTTON_PREFIXES`，有 `test_clear_affix_dispatches_affix_cleared_event` 與 `test_clear_affix_no_dispatch_on_failure` 兩個測試）也呼叫 `_execute_clear_affix(inter, gear_type, slot_index)`。Task 2 把分組查找放進 `_execute_clear_affix` 會破壞這條路由，計畫完全沒提。修正：Architecture Decisions 寫明 `_execute_clear_affix` 維持以 `slot_index` 清除、舊路由不變；分組轉槽號放在 `affix_clear` 分支（或新 helper，與清除共用同一個 DB 連線）；Task 2 加 AC「`clear_affix:gathering:0` 兩個既有測試不修改仍通過」。
- [x] Issue 2: Task 1 第二條 AC 要求 Embed 含 `空槽 x 10` 又要求「不含 `槽 `」，但 `空槽 x 10` 本身含子字串 `槽 `，AC 無法同時成立。修正：改為「不符合正規式 `槽 \d`，且不含 `即將清除：槽`」。
- [x] Issue 3: Task 1 第一條 AC 的選項 `週期縮短（+5%） x 26` 與它引用的未 commit 測試 fixture 不一致：該測試用 `efficiency` 數值 1，預期 label 是 `行動效率（+1%） x 26`，且該測試只斷言選項數不超過 25。修正：AC 改為 `行動效率（+1%） x 26`，並要求在該測試補斷言「分組下拉剛好 1 個選項、label 為 `行動效率（+1%） x 26`、value 為 `efficiency:1`」。
- [x] Issue 4: Task 1 截斷 AC「不含 5 組數值最高的分組」在同數值平手時不確定，也沒檢查輸出順序。修正：指定 fixture 為 7 種類型各有數值 1-4（28 組）加 `efficiency:5`、`material_drop:5`（共 30 組）；AC 斷言下拉 25 個選項、排除 `efficiency:5`、`material_drop:5`、`upgrade_ap_refund:4`、`upgrade_material_refund:4`、`cycle_time_reduce:4`、選項順序與分組清單相同（類型順序，同類型數值由高到低）、placeholder 為 `選擇要清除的詞條...（另有 5 組未列出）`。
- [x] Issue 5: Task 1 把 renderer 參數改名為 `selected_group`，但 `actions.py` 的 `_render_affix` 仍傳 `selected_slot=`；Task 1 commit 後每次開詞條管理畫面都會 `TypeError`。所有 handler 測試都 patch `_render_affix`，沒有測試跑真實的 `_render_affix`，兩個 task 的測試都抓不到參數接線錯誤。修正：Task 2 加 AC「以 mock 的 DB 與 manager 執行真實 `_render_affix(inter, "gathering", selected_group=("efficiency", 3))`，斷言輸出的清除按鈕 custom_id 為 `affix_clear:gathering:efficiency:3` 且未 disabled」；或讓 Task 1 同時改 `_render_affix` 的轉傳（仍在 2 個 source 檔上限內）。
- [x] Issue 6: Task 3 端對端不可照寫執行：快照裡 26 條詞條的工具屬於其他玩家的 `user_id`，本地測試帳號開不到該工具；直接用 `bak/village.db.26100715` 清除詞條會改寫快照；也沒有清除流程的可觀察輸出。修正：步驟寫明「複製快照到 scratch 路徑，`DATABASE_PATH` 指向副本，在副本中把一把 26 條詞條工具的 `gear_affixes` 與 `players` 列改到測試帳號的 `user_id`」；每條 AC 一個可觀察輸出：畫面成功開啟並顯示分組清單、選一組按清除後該組數量減 1 且 Public 通知出現 `清除詞條：{affix_label}（+{value}%）`。fallback 必須呼叫真實 `_render_affix`（不是等價流程），斷言下拉選項數不超過 25，並註明「Discord 是否接受 payload 未驗證」。
- [x] Issue 7: `docs/discord/command-handler.md` 的 `affix_clear` 列沒寫不合法輸入的處理，與同表 `affix_slot_select` 列及 Task 2「不合法時忽略」不一致；`none:none` 與部署前舊格式 `affix_clear:{gear}:{slot}` 都會走到這裡。修正：該列補「類型不在合法類型或數值不是 1-5 整數時（含 `none:none` 與舊格式）忽略」。
- [x] Issue 8: Key Assumptions 與 Recommended Direction 的兩層下拉替代方向都寫「正式環境 2026-10-07 每把工具最多 2 組」，與快照不符。`bak/village.db.26100715` 以 `count(distinct affix_type||value)` 統計，`276190956712230912` 的 `combat` 有 8 組，`1302997409470877700` 與 `151517260622594048` 的 `building` 各 6 組；最多 2 組只對 26 條詞條的 4 把工具成立。修正：兩處改為「26 條詞條的工具各 2 組，全部工具最多 8 組」；「遠低於 25」的結論不變。
- [x] Issue 9: Task 1 修改 `actions.py` 的 `_render_affix` 轉傳，但驗證這段接線的 AC（執行真實 `_render_affix(inter, "gathering", selected_group=("efficiency", 3))`，斷言清除按鈕 custom_id）放在 Task 2，而 Task 2 不改 `_render_affix`。Task 1 commit 時沒有任何測試覆蓋它對 `actions.py` 的改動。修正：把該 AC 移到 Task 1。
- [x] Issue 10: 選定分組已不在現存詞條中時（例如舊訊息的下拉、或另一則訊息已清空該組），Task 1 與 `docs/discord/ui-renderer.md` 都沒定義 Embed 行為；`ui-renderer.md` 寫「選定分組後，Embed 最後一行為 `即將清除：...`」，會讓實作對不存在的分組顯示提示。現行 `build_affix_embed` 以 `if a:` 只在槽位存在時顯示。修正：Task 1 與 `ui-renderer.md` 寫明「選定分組不在現存詞條中時不顯示 `即將清除` 提示」，Task 1 加 AC：`selected_group=("efficiency", 5)` 且 affixes 無該組時，Embed 不含 `即將清除`。
- [x] Issue 11: `on_dropdown` 的 `affix_slot_select` 分支（`actions.py` 第 826 行）呼叫 `self._render_affix(inter, gear_type, selected_slot=slot_index)`。Task 1 把 `_render_affix` 參數改名為 `selected_group` 且「不改路由解析」，Task 1 commit 後玩家選下拉就 `TypeError`。Task 2 改寫這個分支卻沒有任何 AC，現有測試也沒有 `affix_slot_select` handler 測試；把數值以字串傳入（`("efficiency", "3")`）會讓下拉 default 與 `即將清除` 提示靜默失效，測試抓不到。修正：把 `affix_slot_select` 解析移到 Task 1（同為 `actions.py`，仍在 2 個 source 檔內），Task 2 只改 `affix_clear`；Task 1 加 AC「選項值 `efficiency:3` 時 `_render_affix` 以 `selected_group=("efficiency", 3)`（數值為 int）被呼叫一次；選項值 `0`、`bogus:3`、`efficiency:6`、`efficiency:x` 時 `_render_affix` 未被呼叫」。

## Review Issues

- [x] [Minor] `tests/test_discord_commands.py:573-574`: 註解仍寫 `currently fails due to bug in src/cogs/ui_renderer.py`，修正後該測試已通過，註解過時。
- [x] [Minor] `src/cogs/actions.py:720`: `affix_clear` 以寫死的 `("1", "2", "3", "4", "5")` 驗證數值，同檔 `affix_slot_select`（`src/cogs/actions.py:826`）用 `_VALID_AUTO_AFFIX_VALUES`；同一個 1-5 規則有兩份定義。
- [ ] [Minor] `src/cogs/actions.py:724-729`: 分組查找與 `_execute_clear_affix` 在兩個不同 DB 連線執行，清除時不再確認該槽仍屬所選分組；查找與清除之間若該槽被清空又被自動抽取填入，會清除到另一個詞條。實務機率低。 保留：修正會改變行為，不在 refactor 範圍。
- [x] [Minor] `src/cogs/ui_renderer.py:365` 與 `src/cogs/ui_renderer.py:438`: 類型順序 `type_order` 在 `_group_affixes` 與截斷邏輯各建一次，與 Architecture Decisions「分組與排序由單一 helper 產生」不完全一致。
- [x] [Minor] `docs/discord/ui-renderer.md:311-312`: 第 311 行寫空槽為「最後一行」，第 312 行寫選定分組時 `即將清除` 為「Embed 最後一行」；兩者同時出現時第 311 行不成立，需改為「分組清單最後一行」。
- [x] [Minor] `docs/changelogs/2026-10-07-affix-group-display.md:123`: 寫「選定 `cycle_time_reduce:5`」，但依 `AFFIX_TYPE_LABELS` 順序（`src/cogs/ui_renderer.py:55-63`）`material_drop:5` 排第一，同段第 121 行的分組清單輸出也是 `素材掉落` 在前。

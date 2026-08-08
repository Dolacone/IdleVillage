---
title: "試煉達成通知改用玩家名稱取代 mention"
status: Ready-to-implement
created: 2026-08-08
doc_type: change
last_reviewed: 2026-08-08
source_paths:
  - src/core/notification.py
  - docs/discord/notification.md
scope: "Tracks changing the 試煉達成 (trial_success) notification's participant list from Discord `<@{user_id}>` mentions to resolved display names."
---

## Problem Statement

村莊試煉達成時的 Public 通知，參與者清單目前用 `<@{user_id}>` mention 標示每位玩家（`docs/discord/notification.md` 試煉達成範本、`src/core/notification.py` 的 `trial_success` 分支）。需求：達成通知不再使用 mention 標示玩家，原本 mention 的位置改為顯示玩家名稱即可。

## Recommended Direction

在 `notification.dispatch_events(bot, events)` 內（此函式已是 async，且已透過 `channel = bot.get_channel(channel_id)` 取得 channel/guild 物件），對 `trial_success` 事件的每位 `participant`，用 `channel.guild.fetch_member(int(user_id))` 即時解析出 `display_name`，組成 `name_map: dict[str, str]`；找不到（`fetch_member` 拋例外，例如玩家已離開 guild）時 fallback 顯示 `user_id`。組好的 `name_map` 傳入 `_format_event(event, name_map)`，`_format_event` 維持同步、可單元測試，`trial_success` 分支改用 `name_map.get(p['user_id'], p['user_id'])` 取代 `<@{p['user_id']}>`。

此手法完全比照現有 `/idlevillage-ranking` 指令已經在用的機制（`src/cogs/actions.py:316-321`）：`await inter.guild.fetch_member(int(uid))`，成功取 `display_name`，`except Exception` fallback 成 `uid`，並透過 `name_map: dict[str, str]` 傳給純渲染函式（ranking 是 `build_ranking_text(sliced, name_map)`；此處對應 `_format_event(event, name_map)`）。不新增任何資料表欄位，不改變 `trial_manager.py`/`settlement.py`/`engine.py` 的資料結構（`participants` 仍只含 `user_id`/`contribution`/`reward`）。

### 排除的替代方案

- **在貢獻發生當下（settlement.py 結算時）就存 `display_name`**：需要在 `trial_contributions` 新增欄位，並讓每個呼叫 `add_progress()` 的路徑多傳一個名稱參數。但自動工具背景結算沒有 `inter.user` 可用，會出現「純靠自動工具貢獻的玩家從未被記錄過名稱」的缺口，且徒增排程與人工操作兩種資料來源的分岔邏輯。試煉達成通知只在「達成當下」印一次，沒有理由把名稱解析提前綁在貢獻發生的時間點。
- **新增 `players.display_name` 持久化欄位，於所有指令 handler 內 upsert**：影響面遠大於本次需求（需 schema migration + 逐一修改多個指令 handler），且系統目前完全沒有這個機制的雛形，不符合「小改動達成明確需求」的比例原則。
- **`guild.get_member()`（同步、走本地 member cache）**：`player_manager_cog.py` 確有使用此模式，理論上零 API 呼叫成本更低；但若目標玩家不在 gateway member cache 中（例如 intent 未涵蓋、bot 剛啟動快取未填滿）會直接查無，且專案目前唯一「多人名稱批次解析」的既有先例（ranking）選擇的是 `fetch_member`，故本次比照該先例以維持一致性，不引入第三種名稱解析手法。

## Clarifications

<!-- Q: 要用哪種方式解析玩家名稱？ / A: 比照現有 /idlevillage-ranking 的做法（fetch_member + name_map 傳入純渲染函式），不新增資料表欄位、不比照 gear 事件在指令當下存 user_display_name 的做法。 — resolved during refine stage -->
<!-- Q: 自動工具背景貢獻的玩家，沒有指令情境可用，名稱要怎麼處理？ / A: 不受影響——名稱解析發生在試煉達成、組訊息的當下，與貢獻是手動行動還是自動工具產生的完全無關。 — resolved during refine stage -->
<!-- Q: fetch_member 找不到玩家（例如已離開 guild）時怎麼辦？ / A: fallback 顯示 user_id，比照 ranking 既有的 except Exception 處理。 — resolved during refine stage -->

## MVP Scope / Not Doing

- 範圍內：
  - `src/core/notification.py`：`dispatch_events` 新增 `trial_success` 事件的 name_map 解析邏輯；`_format_event` 簽章新增可選參數 `name_map=None`，`trial_success` 分支改用解析後的名稱取代 `<@{user_id}>` mention。
  - `docs/discord/notification.md`：更新試煉達成範本與說明文字，反映新格式與名稱解析來源；新增 Changelog 條目。
  - 測試：更新 `tests/test_discord_notifications.py` 既有 `test_format_trial_success`/`test_format_trial_success_truncates_long_participant_list`，改傳入 `name_map`；新增 `dispatch_events` 對 `trial_success` 事件正確組出 `name_map` 並傳入 `_format_event` 的測試（含 `fetch_member` 拋例外時 fallback user_id 的情境）。
- 範圍外：
  - `trial_start`／`trial_fail` 通知（皆已無 mention 或無參與者清單，不受影響）。
  - `trial_manager.py`／`settlement.py`／`engine.py`（資料結構不變，`participants` 仍只含 `user_id`/`contribution`/`reward`）。
  - 新增任何資料表欄位或玩家名稱持久化機制。
  - gear/affix 等其他既有事件的名稱顯示方式（本次不動）。

## Key Assumptions

- `channel = bot.get_channel(channel_id)`（`dispatch_events` 既有邏輯）取得的 channel 物件在正常執行環境下帶有可用的 `.guild` 屬性，可呼叫 `fetch_member()`；此為 disnake guild text channel 的既有行為，非新假設，但上線後應留意 DM/非 guild 頻道等邊界情況（目前系統設計上通知頻道恆為 guild 頻道，不支援 DM）。
- 參與者人數不多時（依 `TRIAL_TARGET_AMOUNT`/`TRIAL_REWARD_DIVISOR` 預設值與現有截斷邏輯，清單本身已限制在 1900 字元內），逐一 `fetch_member` 的即時 API 呼叫次數可接受，比照 ranking 現有規模假設。

## Architecture Decisions

1. **名稱解析發生在 `dispatch_events`，不改 `_format_event` 以外的組裝層**：`trial_success` 事件本身（由 `trial_manager.py`/`settlement.py` 組裝）維持只含 `user_id`/`contribution`/`reward`，不夾帶名稱。名稱解析屬於「呈現層」關注點，而 `dispatch_events` 是唯一同時擁有 `bot`（可 `get_channel`/取得 `guild`）與事件清單的函式，因此在此組出 `name_map` 後傳給純渲染函式 `_format_event`，維持 `trial_manager`/`settlement`/`engine` 完全不變（比照 Recommended Direction 排除的替代方案理由）。
2. **`_format_event` 簽章新增 `name_map: dict[str, str] | None = None`，預設值維持向後相容**：其餘 8 種既有事件（`gear_success` 等）不使用 `name_map`，呼叫端不傳入時行為不變；只有 `trial_success` 分支讀取 `name_map`。現有測試呼叫 `_format_event(ev)`（不帶 `name_map`）需要改為明確傳入 `name_map` 才能驗證新行為，`trial_success` 分支在 `name_map` 為 `None` 時 fallback 使用 `p['user_id']`（等同「查無此人」的 fallback 路徑），不得拋錯。
3. **`name_map` 的組裝邏輯獨立成 `dispatch_events` 內的一個迴圈，只在事件類型為 `trial_success` 時執行**：其餘事件類型不需要 guild 查詢，避免不必要的 API 呼叫。`fetch_member` 的例外處理比照 `src/cogs/actions.py:315-322` 既有 ranking 邏輯：`try: member = await channel.guild.fetch_member(int(uid)); name_map[uid] = member.display_name; except Exception: name_map[uid] = uid`。
4. **不新增 guild-none 的專屬防呆分支**：`channel.guild` 在現行系統設計下恆為非 None（通知頻道固定是 guild text channel，見 Key Assumptions），若未來需要支援 DM 頻道應在該功能自己的 change document 處理，本次不做超出範圍的防禦式程式碼。

## Tasks

- [x] Task 1: `src/core/notification.py` — `dispatch_events` 新增 `trial_success` 事件的 `name_map` 解析；`_format_event` 新增 `name_map` 參數並套用於 `trial_success` 分支
  - Files: `src/core/notification.py`
  - Tests: 更新 `tests/test_discord_notifications.py`：
    - (a) `test_format_trial_success` 改傳入 `name_map={"u1": "Alice", "u2": "Bob"}`，斷言輸出含 `Alice：貢獻 3000，獲得 25 個`/`Bob：貢獻 2000，獲得 25 個`，且 `assertNotIn("<@", text)`
    - (b) 新增 `test_format_trial_success_without_name_map_falls_back_to_user_id`：不傳 `name_map`（或傳 `None`），斷言輸出含 `u1：貢獻 ...`（純 user_id，非 mention）
    - (c) `test_format_trial_success_truncates_long_participant_list` 改傳入對應 `name_map`（可全部 fallback 成 user_id 或給定簡單名稱），確認截斷邏輯不受影響
    - (d) 新增 `test_dispatch_events_resolves_trial_success_participant_names`：mock `bot.get_channel()` 回傳一個帶 `guild.fetch_member`（`AsyncMock`）的假 channel，驗證 `dispatch_events` 對 `trial_success` 事件會呼叫 `fetch_member` 並將解析出的名稱正確傳入最終發送的訊息文字
    - (e) 新增 `test_dispatch_events_trial_success_fetch_member_failure_falls_back_to_user_id`：`fetch_member` 對其中一位參與者拋例外（模擬已離開 guild），驗證該員在最終訊息顯示 user_id 而非中斷整個通知
    - (f) 新增 `test_dispatch_events_mixed_batch_only_resolves_trial_success_names`：`events` 同時包含 `building_upgrade` 與 `trial_success` 兩種事件（比照 `docs/discord/notification.md`「同一 settlement 內的通知順序」實際會混合發送的情境），斷言 `fetch_member` 只被呼叫於 `trial_success` 的參與者、`building_upgrade` 訊息內容與呼叫次數不受影響、兩則訊息皆正確送出
  - Depends on: 無
  - Acceptance: `trial_success` 訊息不再包含 `<@`；`name_map` 命中時顯示解析出的 `display_name`，未命中或 `fetch_member` 拋例外時 fallback 顯示 `user_id`；其餘 8 種既有事件格式與既有測試不受影響且全數通過；`trial_manager.py`/`settlement.py`/`engine.py` 完全未變動（`git diff` 確認）

- [ ] Task 2: `docs/discord/notification.md` 更新試煉達成範本與說明
  - Files: `docs/discord/notification.md`
  - Tests: 無（文件變更）
  - Depends on: Task 1（需與實作後的實際格式一致）
  - Acceptance: 試煉達成範本改為 `{display_name}：貢獻 {contribution}，獲得 {reward} 個`（移除 `<@{user_id}>`）；新增一段說明名稱解析機制（比照 ranking 的 `fetch_member` + fallback user_id，不新增資料表欄位、與貢獻來源（手動/自動工具）無關）；`last_reviewed` 更新為實作當日日期；新增 Changelog 條目說明此次變更與理由

### 平行任務標記（僅供未來參考，目前循序執行）

- 無可平行任務：Task 2 依賴 Task 1 完成後的實際格式。

## Plan Review Issues

- [x] Issue 1: Recommended Direction 引用 ranking 前例的行號有誤（已修正為 `src/cogs/actions.py:316-321`）。
- [x] Issue 2: Task 1 測試清單缺少「混合事件批次」情境（已新增 (f) `test_dispatch_events_mixed_batch_only_resolves_trial_success_names`）。
- [x] Issue 3: `source_paths` 已補上 `src/core/notification.py`、`docs/discord/notification.md`。
- [x] Issue 4: 無阻擋性邏輯錯誤，`status` 於本次 plan 階段結束時更新為 `Ready-to-implement`。

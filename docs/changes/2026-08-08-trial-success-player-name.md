---
title: "試煉達成通知改用玩家名稱取代 mention"
status: Refactored
created: 2026-08-08
doc_type: change
last_reviewed: 2026-08-08
source_paths:
  - src/core/notification.py
  - docs/discord/notification.md
  - tests/test_discord_notifications.py
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

- [x] Task 2: `docs/discord/notification.md` 更新試煉達成範本與說明
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

## Review Issues

- [x] Issue 1: [Major] `src/core/notification.py:270-278` — `dispatch_events` 對 `trial_success` 的每位參與者串行 `await channel.guild.fetch_member(int(uid))`，且截斷後不會顯示的參與者也照樣被查詢。人數多時（`_format_event` 截斷測試已驗證清單可到 200 人）會在送出通知前累積成數十次串行 REST 呼叫，可能觸發 Discord rate limit 或拖慢 watcher/settlement 流程。Codex 重現：20 位參與者、每次 `fetch_member` 延遲 10ms 的 fake guild，`dispatch_events` 耗時 0.220s（串行），遠高於平行執行應有的 ~0.01s。change document 的 Key Assumptions 已承認此取捨，但未設參與者人數上限或平行化，仍構成可觀測的效能風險，列為 finding。
- [x] Issue 2: [Major] `src/core/notification.py:222-223` — `display_name = name_map.get(...)` 直接嵌入訊息文字且未跳脫，`channel.send` 呼叫未帶 `allowed_mentions` 限制。若參與者的伺服器暱稱本身是 `@everyone`／`@here`／身分組 mention 字串，且 bot 有對應權限，訊息會被 Discord 解析成一次主動 mention（mention injection）。舊版 `<@{user_id}>` 只會 mention 該固定 snowflake，不受暱稱內容影響；新版把使用者可控的自由文字直接寫進訊息本文，擴大了此路徑的攻擊面。Codex 重現：`name_map={"111": "@everyone"}` 傳入 `_format_event` 後，輸出文字仍原樣包含 `@everyone`。註：`src/cogs/ui_renderer.py` 的 `build_ranking_text`／`src/cogs/actions.py` 既有 ranking 功能已有相同的未跳脫模式，本次比照複製了既有缺口，非本次獨有引入的新設計，但風險已隨這次改動擴散到 trial_success 路徑，建議兩處一併修正（跳脫或設定 `allowed_mentions=disnake.AllowedMentions.none()`）。
- [x] Issue 3: [Minor] `src/core/notification.py:274,277` — `except Exception` 完整比照 `src/cogs/actions.py:318-320` 既有 ranking 前例，屬有意的一致性選擇（change document Architecture Decisions #3 已明確記錄），但兩處都會把 `AttributeError`／`TypeError` 等非「玩家已離開 guild」的程式錯誤一併吞掉並 fallback 顯示 user_id，不會留下任何錯誤紀錄。建議未來一併收斂為只捕捉 `disnake.NotFound`／`disnake.HTTPException`，但不阻擋本次合併。
- [x] Issue 4: [Minor] `source_paths`（frontmatter）只列出 `src/core/notification.py`、`docs/discord/notification.md`，未列出同一批次實際修改的 `tests/test_discord_notifications.py`（`git diff main...HEAD --stat` 顯示該檔 +142/-11）。建議補上以符合「source_paths 對應實際建立/修改檔案」的要求。

## Verification Notes

- 測試套件：`uv run python -m pytest -q` — 572 passed, 3 subtests passed，全數通過。
- Tasks 勾選狀態：Task 1、Task 2 於文件中皆已標記 `[x]`，符合實作內容（已核對 `git diff main...HEAD` 對應檔案）。
- `docs/discord/notification.md` 的 `last_reviewed` 已更新為 `2026-08-08`（與今日日期一致）。
- `int(uid)` 安全性：`src/managers/trial_manager.py` 的 `participants` 資料來源與既有 ranking 功能一致，皆為 Discord snowflake 數字字串，未發現非數字格式的 `user_id`，`int(uid)` 對現有資料不會拋例外。
- `_format_event` 簽章相容性：全文搜尋確認呼叫端只有 `dispatch_events`（傳入 `name_map`）與既有測試（未傳或明確傳入 `name_map`），`name_map` 預設 `None`，其餘 8 種事件分支未讀取 `name_map`，未發現回歸。
- `source_paths` 對照 `git diff main...HEAD --stat`：實際變更 4 檔（`src/core/notification.py`、`docs/discord/notification.md`、`tests/test_discord_notifications.py`、本文件自身），frontmatter 缺 `tests/test_discord_notifications.py`（見 Issue 4）。

## Post-Review Fixes (2026-08-08)

- Issue 1（序列 `fetch_member` 效能風險）：改用 `asyncio.gather` 平行呼叫所有參與者的 `fetch_member`，取代原本逐一 `await` 的迴圈。
- Issue 2（mention injection）：`dispatch_events` 的 `channel.send` 一律加上 `allowed_mentions=disnake.AllowedMentions.none()`，玩家暱稱即使包含 `@everyone`/mention 語法也不會觸發實際 ping；全文搜尋確認其餘事件分支皆未使用 `<@...>` mention 語法，套用此參數對其餘 8 種事件無副作用。新增測試 `test_dispatch_events_suppresses_mentions_from_malicious_display_name` 與既有測試補上 `allowed_mentions` 斷言。
- Issue 3（`except Exception` 過寬）：改為只捕捉 `disnake.NotFound`/`disnake.HTTPException`，其餘例外（例如程式錯誤）不再被靜默吞掉。
- Issue 4（`source_paths` 缺漏）：補上 `tests/test_discord_notifications.py`。
- `docs/discord/notification.md` 同步更新說明文字（平行解析、`allowed_mentions`、例外類型收斂）。

驗證：`uv run python -m pytest -q` → 全數通過（見下方重新驗證結果）。

## Review Issues (Round 2)

- [x] Issue 1: [Major] `src/core/notification.py:270-283` — `asyncio.gather` 包裝的 `_resolve` 協程雖然平行 await，但 disnake 2.12 的 `HTTPClient.request` 依 `Route.bucket` 對每個 request 上鎖（`.venv/lib/python3.11/site-packages/disnake/http.py` `HTTPClient.request`：`lock = self._locks.get(bucket)` -> `await lock.acquire()`，網路請求完成才釋放）。`Route.bucket` 的定義是 `f"{channel_id}:{guild_id}:{path}"`（`disnake/http.py` `Route.bucket`），其中 `path` 是未代入參數前的樣板字串 `/guilds/{guild_id}/members/{member_id}`（`Route.__init__` 的 `self.path: str = path` 保留原始樣板，未含 `member_id` 實際值）。因此同一 guild 內所有 `fetch_member` 呼叫共用同一把 `asyncio.Lock`，即使透過 `asyncio.gather` 同時發起，底層 HTTP 請求仍會被序列化處理，實測每個請求須等前一個回應完畢才能取得鎖並發出下一個請求。Round 1 Issue 1（序列 `fetch_member` 效能風險）宣稱已用平行化解決，實際上參與者人數 N 時整體耗時仍約為 N 次序列 round-trip 的總和，與修正前的 `for` 迴圈效果相近，未達成文件宣稱的效能改善。建議改用 member cache（`guild.get_member`）優先查詢、必要時才 fallback `fetch_member`，或限制單次解析人數上限，才能真正降低序列 REST 呼叫次數。

## Verification Notes (Round 2)

- `asyncio.gather` 平行化（Round 1 Issue 1）：程式碼確認已改用 `asyncio.gather`（`src/core/notification.py:281`），`name_map = dict(zip(uids, resolved))` 的鍵值對應正確——`asyncio.gather` 回傳順序保證與傳入的 awaitable 順序一致，不受實際完成順序影響，故 `zip(uids, resolved)` 不會錯配 `uid`。但實測 disnake 底層 rate-limit bucket 鎖仍序列化實際 HTTP 請求，效能改善名不符實，見上方 Issue 1。
- `allowed_mentions=disnake.AllowedMentions.none()`（Round 1 Issue 2）：`src/core/notification.py:287` 確認唯一的 `channel.send` 呼叫已加上此參數；全文搜尋 `src/core/notification.py` 未發現其餘 `<@` mention 語法或其他 `channel.send`/`message.edit` 呼叫需要同步修正。`AllowedMentions.none()` 實測回傳 `everyone=False`、`users=False`、`roles=False`，測試 `test_dispatch_events_resolves_trial_success_participant_names`、`test_dispatch_events_suppresses_mentions_from_malicious_display_name` 皆有對應斷言，且後者使用真實惡意暱稱 `@everyone` 情境，能在缺少此參數時失敗。
- 例外收斂（Round 1 Issue 3）：`src/core/notification.py:277` 確認已改為 `except (disnake.NotFound, disnake.HTTPException)`。查 `disnake/errors.py`：`Forbidden`、`NotFound`、`DiscordServerError` 皆為 `HTTPException` 子類，`fetch_member` 文件標註的三種例外（`NotFound`/`Forbidden`/`HTTPException`）皆被涵蓋，未發現遺漏的合法「查無成員」例外類型。測試 `test_dispatch_events_trial_success_fetch_member_failure_falls_back_to_user_id` 使用真實 `disnake.NotFound` 實例，能在例外類型窄化錯誤時失敗，非空泛測試。
- `source_paths`（Round 1 Issue 4）：frontmatter 列出 `src/core/notification.py`、`docs/discord/notification.md`、`tests/test_discord_notifications.py`，與 `git diff main...HEAD --stat` 顯示的三個原始碼/測試檔案一致（變更文件自身不需自我列舉）。
- 新增測試檢視：`tests/test_discord_notifications.py` 本輪新增/修改的斷言（`allowed_mentions` 檢查、`disnake.NotFound` 真實例外）皆具備可證偽性，未發現空泛或恆真測試；新增 `import disnake`（第 15 行）為新增例外類型與測試所需，非未使用匯入。
- 任務狀態：Task 1、Task 2 與所有 Review Issues（含 Round 1 四項）皆已勾選 `[x]`；`last_reviewed` 為 `2026-08-08`，與今日日期一致。
- 測試套件：`uv run python -m pytest -q` → 573 passed, 3 subtests passed，全數通過。

## Post-Review Fixes Round 2 (2026-08-08)

- Round 2 Issue 1（`asyncio.gather` 未真正解決序列化問題）：改為「快取優先」策略——每位 participant 先呼叫同步、零網路成本的 `channel.guild.get_member(int(uid))`（走 gateway member cache），命中直接取 `display_name`；只有未命中時才 fallback `await channel.guild.fetch_member(int(uid))`。`asyncio.gather` 保留（讓多個 fallback 呼叫至少能併發啟動，即使底層仍受 disnake rate-limit bucket 限制），但實際降低延遲與 REST 呼叫次數的手段是 `get_member` 快取命中路徑，而非平行化本身。文件與程式碼註解已更正先前對 `asyncio.gather` 效能改善的誇大宣稱。
- 新增測試 `test_dispatch_events_uses_member_cache_without_network_call`：驗證命中 member cache 時完全不呼叫 `fetch_member`（`AsyncMock(side_effect=AssertionError(...))` 若被呼叫會讓測試失敗）。
- 既有 `dispatch_events` 相關測試（`test_dispatch_events_resolves_trial_success_participant_names`、`test_dispatch_events_suppresses_mentions_from_malicious_display_name`、`test_dispatch_events_trial_success_fetch_member_failure_falls_back_to_user_id`、`test_dispatch_events_mixed_batch_only_resolves_trial_success_names`）的假 guild 物件補上 `get_member=lambda uid: None`（模擬快取未命中），確保這些測試仍實際驗證 `fetch_member` fallback 路徑，而非被新的快取優先邏輯繞過。
- `docs/discord/notification.md` 同步更新說明文字，明確區分「`get_member` 快取命中＝零成本」與「`fetch_member` 序列化限制」。

驗證：`uv run python -m pytest -q` → 全數通過（見下方 Round 2 重新驗證）。

## Review Issues (Round 3)

- [x] Issue 1: [Major] `src/core/notification.py:274-282` — cache-miss fallback 的 `except (disnake.NotFound, disnake.HTTPException)` 只涵蓋 Discord API 回應層級的例外，不涵蓋傳輸層例外（例如 `OSError`／連線重置、`asyncio.TimeoutError`）。這些例外會由 disnake `HTTPClient.request` 在重試耗盡後直接拋出（`.venv/lib/python3.11/site-packages/disnake/http.py` `except OSError as e: ... raise`），不是 `HTTPException` 子類。因為 `_resolve` 沒有攔截，`asyncio.gather(*(_resolve(uid) for uid in uids))`（`src/core/notification.py:284`）會直接向上拋出例外，中止整個 `dispatch_events` 迴圈，導致該次呼叫傳入的所有事件（不只是名稱解析失敗的那個 participant）都不會送出，且試煉已完成、事件不會重播，通知永久遺失。Codex 重現：fake guild 的 `fetch_member` 以 `side_effect=OSError("connection reset")` 模擬暫時性網路錯誤，`await notification.dispatch_events(bot, [event])` 直接拋出 `OSError`，`channel.send` 完全未被呼叫。此問題並非本輪新增（`except Exception` 收斂為 `except (disnake.NotFound, disnake.HTTPException)` 是 Round 1 Issue 3 / Round 1-2 fix 的既有結果），但 Round 1、Round 2 審查皆未涵蓋此路徑，本輪新增/修改 `_resolve` 時一併發現，故列為本輪 finding。建議至少再攔截 `OSError`（或改用 `except disnake.HTTPException` 之外，額外 `except Exception` 記錄錯誤後 fallback 顯示 user_id，取捨「靜默吞掉程式錯誤」與「通知永久遺失」的優先序）。

## Verification Notes (Round 3)

- Cache-first 邏輯核對：`src/core/notification.py:275-282` 確認 `channel.guild.get_member(int(uid))` 先於 `fetch_member` 執行，`if cached is not None` 使用身分判斷而非真值判斷，`display_name` 為空字串等 falsy-but-valid 值不會被誤判為未命中；`fetch_member` 僅在 `get_member` 回傳 `None`（快取未命中）時才被呼叫。`allowed_mentions=disnake.AllowedMentions.none()`（`src/core/notification.py:290`）與窄化例外類型（`disnake.NotFound`／`disnake.HTTPException`，`src/core/notification.py:281`）皆維持不變，`name_map = dict(zip(uids, resolved))`（`src/core/notification.py:285`）鍵值對應正確，未發現錯位。
- 測試核對：`test_dispatch_events_uses_member_cache_without_network_call`（`tests/test_discord_notifications.py:700`）以 `fetch_member=AsyncMock(side_effect=AssertionError(...))` 確保命中快取時完全不觸發網路呼叫，並以 `guild.fetch_member.assert_not_awaited()` 佐證；`test_dispatch_events_resolves_trial_success_participant_names`、`test_dispatch_events_suppresses_mentions_from_malicious_display_name`、`test_dispatch_events_trial_success_fetch_member_failure_falls_back_to_user_id`、`test_dispatch_events_mixed_batch_only_resolves_trial_success_names` 皆補上 `get_member=lambda uid: None` 強制快取未命中，實際測試路徑仍會走到 `fetch_member` fallback，未被新邏輯繞過（以 `test_dispatch_events_mixed_batch_only_resolves_trial_success_names` 的 `guild.fetch_member.assert_awaited_once_with(int("111"))` 為證）。未發現恆真或未實際驗證行為的測試。
- 本輪 diff 新增程式碼僅 `src/core/notification.py:275-278`（4 行），未發現死碼或未使用變數。
- Round 1/2 既有修正未回歸：mention injection 防護（`allowed_mentions`）、窄化例外類型、`zip` 鍵值對應皆維持正確，見上方核對。
- `codex exec review --base main` 另回報 `docs/changes/` 目錄與 `AGENTS.md` 所述 `docs/changelogs/` 不一致；但檢視 `docs/changes/` 目錄下已有 11 份既有變更文件（如 `2026-07-20-auto-tool-hourly-material.md`），本文件路徑與既有慣例一致，非本次引入的問題，不列為 finding。
- `source_paths`：`src/core/notification.py`、`docs/discord/notification.md`、`tests/test_discord_notifications.py` 與 `git diff main...HEAD --stat` 一致。
- Tasks 與 Round 1、Round 2 Review Issues 皆已勾選 `[x]`；`last_reviewed` 為 `2026-08-08`，與今日日期一致。
- 測試套件：`uv run python -m pytest -q` → 574 passed, 3 subtests passed，全數通過。

## Post-Review Fixes Round 3 (2026-08-08)

- Round 3 Issue 1（傳輸層例外會中止整批 `dispatch_events`）：`_resolve` 的 `except (disnake.NotFound, disnake.HTTPException)` 之後新增 `except Exception`，記錄 `logger.exception` 後同樣 fallback 顯示 `user_id`，不再讓單一參與者的非預期例外（例如 `OSError`）中止整個 `asyncio.gather` 呼叫、拖累同批次其他事件的發送。取捨依 Round 3 審查建議：「靜默吞掉程式錯誤」優先於「通知永久遺失」，但改用 `logger.exception` 而非完全靜默，錯誤仍留有紀錄可追查。
- 新增測試 `test_dispatch_events_trial_success_transport_error_falls_back_without_aborting_batch`：模擬 `fetch_member` 拋出 `OSError`，驗證該參與者 fallback 顯示 user_id、其餘參與者與整個事件仍正常送出，不中止批次。
- `docs/discord/notification.md` 補充說明非預期例外的處理方式。

驗證：`uv run python -m pytest -q` → 全數通過（見下方 Round 3 重新驗證）。

## Review Issues (Round 4)

No new issues found.

## Verification Notes (Round 4)

- 例外順序核對：`src/core/notification.py:274-281` 確認 `except (disnake.NotFound, disnake.HTTPException)` 位於 `except Exception:` 之前；Python 依序比對 except 子句，特定例外類別必須排在 `Exception` 之前才會生效，此排序正確，`except Exception` 未使前者變成無法觸及的死碼。
- 新測試核對：`tests/test_discord_notifications.py:834` 的 `test_dispatch_events_trial_success_transport_error_falls_back_without_aborting_batch` 以 `fetch_member` 的 `side_effect` 對 `uid == "111"` 拋出真正的 `OSError("connection reset")`（非 `disnake.NotFound`/`disnake.HTTPException`，不會被窄化的 except 子句攔截）；斷言 `channel.send.assert_awaited_once()` 且文字同時含 `111：貢獻 3000，獲得 25 個`（fallback 顯示 user_id）與 `Bob：貢獻 2000，獲得 25 個`（另一位參與者正常解析）。若移除本輪新增的 `except Exception:` 子句，`OSError` 會直接從 `_resolve` 拋出，經 `asyncio.gather`（`src/core/notification.py:284`，預設 `return_exceptions=False`）向上傳播，導致 `dispatch_events` 對整批事件的迴圈中止、`channel.send` 完全不會被呼叫，測試會失敗（`assert_awaited_once` 落空且例外向上拋出中止整個 test coroutine）。確認非恆真測試。
- `dispatch_events`（`src/core/notification.py:255-291`）內 `asyncio.gather(*(_resolve(uid) for uid in uids))` 前後沒有額外 try/except 包裹，`_resolve` 是唯一的例外防線；此點與 Round 3 finding 描述的風險位置一致，本輪修正確實補上該防線。
- `BaseException` 子類（例如 `asyncio.CancelledError`、`KeyboardInterrupt`）不會被 `except Exception:` 攔截（`asyncio.CancelledError.__mro__` 確認繼承 `BaseException` 而非 `Exception`，disnake 2.12.0 環境下核對）；`CancelledError` 向上傳播是 asyncio task 取消的正常語意（例如 bot shutdown 或外部呼叫方主動取消整個 `dispatch_events` 呼叫），任由其傳播是預期行為，非本次需要修正的缺口，維持 out of scope。
- 全 diff 重新核對（`git diff main...HEAD`）：
  - mention injection 防護：`channel.send(text, allowed_mentions=disnake.AllowedMentions.none())`（`src/core/notification.py:293`）維持不變，唯一的 `channel.send` 呼叫點。
  - 例外窄化：`except (disnake.NotFound, disnake.HTTPException)`（`src/core/notification.py:274`）維持 Round 2 修正結果，本輪只在其後新增 `except Exception:`，未改動窄化範圍本身。
  - cache-first 邏輯：`channel.guild.get_member(int(uid))` 使用 `is not None` 身分判斷（`src/core/notification.py:272-273`）維持不變，未發現回歸。
  - dict 鍵值對應：`name_map = dict(zip(uids, resolved))`（`src/core/notification.py:285`）維持 `asyncio.gather` 回傳順序與輸入順序一致的既有結論，未發現錯位風險。
  - 文件核對：`docs/discord/notification.md` 已於 Round 3 fix 補充非預期例外的處理說明（「其他非預期例外（例如底層連線錯誤）同樣 fallback 顯示 `user_id`，但會記錄 log」），與本輪程式碼行為（`logger.exception` + fallback `user_id`）一致，未發現文件與程式碼不符之處。
- 使用 `codex exec` 進行第二意見審查（因 codex-cli 0.146.1 的 `--base` 與自訂 prompt 參數無法併用，改為要求 codex 自行於 repo 內執行 `git diff main...HEAD` 取得變更範圍）：結論為「沒有發現新的問題」，涵蓋例外順序、測試有效性、`CancelledError` 不受影響、mention 防護/快取優先/字典鍵值/文件一致性等項目，與本輪自行核對結果一致。
- `source_paths`：`src/core/notification.py`、`docs/discord/notification.md`、`tests/test_discord_notifications.py`，與 `git diff main...HEAD --stat` 一致（本文件自身不需自我列舉）。
- Tasks（Task 1、Task 2）與 Round 1-3 所有 Review Issues 皆已勾選 `[x]`；`last_reviewed` 為 `2026-08-08`，與今日日期一致。
- 測試套件：`uv run python -m pytest -q` → 575 passed, 3 subtests passed，全數通過。

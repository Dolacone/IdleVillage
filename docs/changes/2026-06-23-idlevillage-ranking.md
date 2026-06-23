---
title: "/idlevillage-ranking slash command"
status: Ready-to-implement
created: 2026-06-23
doc_type: change
last_reviewed: 2026-06-23
source_paths: []
scope: "Tracks the implementation of a new /idlevillage-ranking slash command that displays per-tool-type top-3 rankings."
---

## Problem Statement

目前沒有任何指令可以讓玩家查看各工具等級的排行榜，無法了解自己和其他玩家的相對水準。

## Recommended Direction

方向 A：直接 DB 查詢 + Discord member lookup

- 查 `players` 表的四個 `gear_*` 欄位，對每個類型找出前三名等級的玩家
- 透過 Discord guild member cache 取得 display name
- Ephemeral content（純文字，非 embed），格式如下：
  ```
  {emoji}採集工具:
  - Lv23: {player name}
  - Lv23: {player name}
  - Lv22: {player name}
  {emoji}建設工具:
  ...
  ```
- 同等級全部列入；若同等級玩家組合超過三名，依然全部列出
- 若無任何玩家，顯示「（尚無玩家）」

## Clarifications

<!-- Q: [question] / A: [answer] — resolved during refine stage -->

## MVP Scope / Not Doing

- 每個工具類型若無玩家，顯示「- （尚無玩家）」；不需空白訊息或跳過該區
- 不做持久訊息或快取
- 不做跨頻道公開排行

## Architecture Decisions

- Slash command 放在 `actions.py`：ranking 屬於玩家公開資訊查詢，與現有個人介面一致，不需新 cog 檔案
- `get_gear_rankings(db)` 加在 `player_manager.py`：回傳原始 `dict[str, list[tuple[str, int]]]`（level DESC, user_id ASC 穩定排序），level == 0 過濾；`slice_top_levels(entries, top_n=3)` 同在 `player_manager.py`，**依等級數截斷**：回傳前 top_n 個不同等級的所有 entry（同等級全部列入，不設條目上限），裁切邏輯屬 data-shaping 而非 UI，符合放在 manager 的職責
- Player name 解析在 cog 層（`actions.py`）：`guild.get_member(int(user_id))` 取 display_name，缺失時 fallback `user_id`，產生 `dict[str, str]` name_map 傳給 renderer
- `build_ranking_text(sliced_rankings, name_map)` 加在 `ui_renderer.py`：接收已裁切資料與 name_map（純 dict），renderer 只做字串格式化，符合「無外部查詢」契約

依賴關係：Task 1 → Task 2 → Task 3 → Task 4（循序）

## Tasks

- [x] Task 1: 在 `src/managers/player_manager.py` 新增 `get_gear_rankings(db)` 與 `slice_top_levels(entries, top_n=3)`
  - `get_gear_rankings`: 查詢所有 players 四個 gear_* 欄位，回傳 `dict[str, list[tuple[str, int]]]`，每類型依 level DESC, user_id ASC 排序，過濾 level == 0
  - `slice_top_levels`: 接受 `list[tuple[str, int]]`，依等級數截斷，回傳前 top_n 個不同等級的所有 entry（同等級全部列入，不設條目上限）
  - 驗收：正確排序、level==0 過濾、同等級全列（不截斷）、第 top_n+1 個不同等級的 entry 不出現；測試覆蓋：以上所有情況

- [x] Task 2: 在 `src/cogs/ui_renderer.py` 新增 `build_ranking_text(sliced_rankings, name_map)`
  - 接受 `dict[str, list[tuple[str, int]]]` 與 `dict[str, str]` name_map，回傳格式化字串
  - 工具類型順序：gathering → building → combat → research；emoji 使用 `ACTION_EMOJIS`；工具名稱使用 `GEAR_LABELS`（例：`GEAR_LABELS["combat"]` = 「狩獵工具」，非 `ACTION_LABELS`）
  - 格式：`{emoji}{GEAR_LABELS[type]}:\n- Lv{n}: {name}\n...`；某類型無玩家時顯示 `- （尚無玩家）`
  - 驗收：輸出符合規格；測試覆蓋：標準前三名、同等級多名、某類型無玩家

- [x] Task 3: 在 `src/cogs/actions.py` 新增 `/idlevillage-ranking` slash command
  - guild 檢查、呼叫 `get_gear_rankings()` 與 `slice_top_levels()`，解析 name_map，呼叫 `build_ranking_text()`
  - 若輸出超過 1900 字元，截斷並附加 `\n（排行過長，部分內容已省略）`
  - 以 Ephemeral content 回傳（不用 embed）
  - 驗收：guild 檢查存在；長度超限時有截斷文案；tests 覆蓋正常路徑與超長路徑

- [ ] Task 4: 更新 SSOT 文件
  - `docs/discord/command-handler.md`：新增 `/idlevillage-ranking` 至 Slash Commands 表
  - `docs/managers/player-manager.md`：新增 `get_gear_rankings()` 與 `slice_top_levels()` 至操作介面
  - `docs/discord/ui-renderer.md`：新增 `build_ranking_text()` 格式規範
  - 更新 change document `source_paths`
  - 驗收：三份文件均已更新

## Key Assumptions

- Discord guild member cache 通常有玩家資料；若快取缺失則 fallback 顯示 user_id
- 排行只計算有紀錄的玩家（players 表中存在的）
- 玩家 gear level = 0 時不參與排行（過濾 level == 0）

## Review Issues

## Plan Review Issues

- [x] `build_ranking_text(rankings, guild)` 讓 `ui_renderer.py` 接收 Discord guild 物件並呼叫 `guild.get_member()`，違反現有 renderer 契約（純渲染、無外部狀態查詢、資料以 plain dict/list 傳入）。應在 command/cog 層完成 user_id -> display_name 解析，或改為傳入純資料/解析 callback，renderer 只負責格式化。
- [x] 「前三名等級、同等級全列」是排名裁切規則，不只是字串呈現；放在 `ui_renderer.py` 會把業務選擇邏輯混入 renderer。應明確規劃由 `player_manager.get_gear_rankings()` 或 command/cog 層產生已裁切的 ranking groups，再交給 renderer 顯示。
- [x] 同等級玩家的排序未定義；若 DB 只依 level 降序，同 level 輸出順序可能不穩定，測試與使用者看到的排行可能抖動。需指定穩定次排序（例如 user_id 或已解析 display_name）。
- [x] 同等級全部列入可能讓單一等級人數過多，超過 Discord message/embed description 長度限制；計畫缺少截斷、分頁或最大顯示數策略。
- [x] 計畫缺少 SSOT 文件更新任務；新增 slash command、player-manager API、renderer 輸出格式時，至少應更新 `docs/discord/command-handler.md`、`docs/managers/player-manager.md`、`docs/discord/ui-renderer.md`，並補齊 change document 的 `source_paths`。
- [x] 截斷邊界未定義：「同等級全部列入」與「每類型最多 20 筆」規則衝突；若第三名等級有 25 人，計畫會在第 20 筆截斷，但未規劃截斷提示（例如「另 N 名」），使用者會誤以為名單完整。需明確截斷語意：以條目數截斷，或以等級數截斷，並規劃溢出文案。
- [x] 空狀態輸出不一致：MVP Scope 寫「無玩家時顯示空訊息」，Recommended Direction / Task 2 寫每類型顯示 `- （尚無玩家）`。兩者是不同輸出格式，需統一為同一個規格。
- [x] 工具名稱來源未指定：Task 2 未說明各工具類型的顯示名稱要取自 `ACTION_LABELS` 還是 `GEAR_LABELS`；兩者對 `combat` 的值分別是「戰鬥」與「狩獵工具」，排行標題應使用工具名稱，計畫需明確指定來源以避免輸出行動名稱。
- [x] `slice_top_levels()` 改為「前三個 distinct levels、同級全列、不設 entry cap」後，仍未解決 Discord 回覆長度限制；若任一工具類型前三個等級涵蓋大量玩家，`build_ranking_text()` 仍可能產生無法送出的 ephemeral embed/message。需規劃明確的輸出上限、分頁、或溢出摘要文案，且測試需覆蓋超長排行情境。
- [x] Recommended Direction 第 21 行寫「Ephemeral embed」，與 Task 3「Ephemeral content（不用 embed）」衝突，已修正為「Ephemeral content（純文字，非 embed）」。
- [x] 檔案路徑：`docs/changes/` 與 AGENTS.md `docs/changelogs/` 描述不一致 — 依 /feature skill template 規定，change documents 放在 `docs/changes/`，且前次 change document 也在此目錄，路徑正確，非問題。

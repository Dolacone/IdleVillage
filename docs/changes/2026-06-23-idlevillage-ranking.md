---
title: "/idlevillage-ranking slash command"
status: Draft
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
- Ephemeral embed，格式如下：
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

- 只顯示有玩家的情況（無玩家時顯示空訊息）
- 不做持久訊息或快取
- 不做跨頻道公開排行

## Architecture Decisions

- 新增一個 `ranking_cog.py` 或直接在現有 cog 中加 command
  - 考量：四個現有 cog 皆有其職責範圍；ranking 屬於 general 資訊查詢，可加入 `actions.py`（個人介面所在）或建立新 cog
  - 決定：加在 `actions.py`，因為現有個人介面也在此，且 ranking 是玩家可見的公開資訊
- Player name 解析：使用 `inter.guild.get_member(int(user_id))` 從快取取得，fallback 為 `user_id` 字串
- 排行邏輯：純 Python 排序，不在 DB 層做，保持 query 簡單

## Tasks

- [ ] Task 1: 新增 `get_rankings()` query function 至 database layer，回傳各 gear type 的 (user_id, level) 列表（依 level 降序）
  - 驗收：函式存在且回傳正確排序資料；測試覆蓋：有玩家、無玩家、同等級
- [ ] Task 2: 新增 `build_ranking_text()` 至 ui_renderer，接收排行資料與 guild 物件，回傳格式化字串
  - 驗收：輸出格式符合規格；測試覆蓋：前三名、同等級超過三名、無玩家
- [ ] Task 3: 在 `actions.py` 新增 `/idlevillage-ranking` slash command，呼叫 Task 1/2 並回傳 Ephemeral
  - 驗收：指令可正常執行；guild 檢查存在；測試覆蓋：正常執行路徑

## Key Assumptions

- Discord guild member cache 通常有玩家資料；若快取缺失則 fallback 顯示 user_id
- 排行只計算有紀錄的玩家（players 表中存在的）
- 玩家 gear level = 0 時不參與排行（過濾 level == 0）

## Review Issues

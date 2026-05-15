---
title: "idlevillage-manager：玩家數據調整指令"
status: Ready-to-implement
created: 2026-05-15
doc_type: change
last_reviewed: 2026-05-15
source_paths:
  - src/cogs/player_manager_cog.py
  - src/main.py
  - docs/discord/command-handler.md
  - tests/test_player_manager_cog.py
scope: "Tracks this change from design through review."
---

## Problem Statement

管理員目前無法直接調整個別玩家的數據（裝備等級、素材數量、保底計數、鐵齒失敗累積值），導致測試和遊戲管理時只能直接操作資料庫，風險高且不便。

**How Might We** 讓管理員透過 Discord slash command 安全地查看與修改任意玩家的個人數據？

## Recommended Direction

新增 `/idlevillage-manager` slash command，包含以下子指令：

- `player-gear <user> <gear_type> <level>` — 設定玩家裝備等級
- `player-material <user> <gear_type> <amount>` — 設定玩家素材數量
- `player-pity <user> <gear_type> <count>` — 設定玩家保底計數
- `player-risky <user> <value>` — 設定玩家鐵齒失敗累積值
- `player-view <user>` — 查看玩家所有數據（操作前確認現值）

所有子指令限管理員使用（沿用 `is_admin()` 檢查），以絕對值設定（非 delta），操作後回覆含舊值→新值的確認訊息（ephemeral）。

以絕對值設定而非加減，因為管理員通常需要知道確切目標值，避免累加錯誤。

## Key Assumptions

- [x] 以絕對值設定（非 delta）是正確的 UX：管理員明確知道目標值，不需要相對調整
- [x] 設定裝備等級不做上限驗證（gear_cap）：管理員有意繞過限制是合理需求
- [x] 設定值下限為 0（整數欄位，負值無意義）

## MVP Scope / Not Doing

**MVP（此次做）：**
- `player-view`、`player-gear`、`player-material`、`player-pity`、`player-risky` 五個子指令
- 操作後回覆舊值→新值確認（ephemeral）
- 操作對象不存在時回報錯誤

**Not Doing：**
- 不做 bulk 修改（一次改多個玩家）— 需求未提及，MVP 不需要
- 不做 delta 調整（+/-N）— 絕對值更安全
- 不做操作 audit log — 可在未來版本加入
- 不驗證 gear_level ≤ gear_cap — 管理員可能有意調超過上限做測試

## Architecture Decisions

- 新 cog 放在 `src/cogs/player_manager_cog.py`，沿用現有 `GeneralCog` 的 guild/admin 雙重檢查模式。
- 子指令用 disnake `@<parent>.sub_command()`，`gear_type` 參數使用 `commands.option_enum` 限制為四種類型。
- 設定操作直接呼叫 `player_manager` 的 setter（`set_gear_level`、`set_pity`）及直接 SQL（素材、鐵齒），保持與現有 manager 層一致。
- `player-view` 回傳 Embed，其餘子指令以文字確認訊息回應（均 ephemeral）。

## Tasks

- [x] Task 1: 實作 cog、register in main.py、更新 command-handler.md SSOT
  - 新增 `src/cogs/player_manager_cog.py`：`/idlevillage-manager player-view / player-gear / player-material / player-pity / player-risky`
  - `src/main.py`：`initial_extensions` 加入 `"cogs.player_manager_cog"`
  - `docs/discord/command-handler.md`：補充五個新子指令
  - **AC**：管理員可在 Discord 執行五個子指令；非管理員或非指定 Guild 均被拒絕；值 < 0 回報錯誤；玩家不存在回報錯誤；操作成功顯示舊值→新值
- [x] Task 2: 新增測試 `tests/test_player_manager_cog.py`（依賴 Task 1）
  - 覆蓋：guild 檢查、admin 檢查、玩家不存在、各 setter 正確寫入 DB、負值被拒、`player-view` 資料正確
  - 使用 `DatabaseTestCase` + `AsyncMock` 模式（沿用既有測試慣例）
  - **AC**：`uv run python -m pytest tests/test_player_manager_cog.py` 全過

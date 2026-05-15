---
title: "idlevillage-manager：玩家數據調整指令"
status: Draft
created: 2026-05-15
doc_type: change
last_reviewed: 2026-05-15
source_paths: []
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

## Tasks

- [ ] Task 1: 新增 `src/cogs/player_manager_cog.py`，實作 `/idlevillage-manager` 及五個子指令
- [ ] Task 2: 在 `src/main.py` 載入新 cog
- [ ] Task 3: 新增對應測試 `tests/test_player_manager_cog.py`

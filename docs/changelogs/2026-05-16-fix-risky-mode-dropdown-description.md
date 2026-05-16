---
title: "Fix: 鐵齒模式 Dropdown 描述與現況不符"
status: Ready-to-review
created: 2026-05-16
doc_type: change
last_reviewed: 2026-05-16
source_paths:
  - src/cogs/ui_renderer.py
  - docs/discord/ui-renderer.md
scope: "修正鐵齒模式 Dropdown 描述字串，使其與實際遊戲邏輯一致。"
---

## Problem Statement

強化介面的鐵齒模式 Dropdown 描述仍顯示 `成功無保底時 +1~+3`，但此功能已於 2026.05.15 移除（鐵齒成功現固定 +1）。描述亦未說明失敗時工具等級歸零的風險，可能讓玩家低估失敗代價。

## Recommended Direction

更新 `src/cogs/ui_renderer.py` 中鐵齒模式的 Dropdown 描述字串，移除 `成功無保底時 +1~+3`，並補充失敗時工具等級歸零的說明。同步更新 `docs/discord/ui-renderer.md` 中的對應說明。

## Clarifications

<!-- 無需釐清，根源明確。 -->

## MVP Scope / Not Doing

**Scope：**
- 修正 `ui_renderer.py:409` 的鐵齒 Dropdown 描述字串
- 同步更新 `docs/discord/ui-renderer.md` 中的鐵齒描述

**Not Doing：**
- 不更動任何遊戲邏輯
- 不修改其他強化模式的描述

## Architecture Decisions

- **只改描述字串**：根源是 UI 文字未隨遊戲邏輯更新，不涉及任何邏輯修改。
- **新描述措辭**：`僅消耗 1 個素材，失敗則工具等級與 pity 均歸零` — 清楚說明失敗風險，移除已不存在的 +1~+3 說明。

## Tasks

- [x] Task 1: 修正 `src/cogs/ui_renderer.py:409` 鐵齒模式描述字串，並同步更新 `docs/discord/ui-renderer.md:161`

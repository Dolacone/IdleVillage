---
title: "移除奉獻系統"
status: Draft
created: 2026-07-14
doc_type: change
last_reviewed: 2026-07-14
source_paths: []
scope: "Tracks removal of the offering (奉獻) player action system from design through review."
---

## Problem Statement

奉獻系統（2026-05-23 引入，見 `docs/changelogs/2026-05-23-offering-action.md`）是第 5 種玩家行動：消耗食物/木頭/研究點其中一種資源，累積至全村門檻後，讓所有玩家素材各 +1。目前決定移除此系統，回歸原本四種行動（採集/建設/戰鬥/研究）。

## Recommended Direction

完全移除：刪除所有奉獻相關程式碼、DB 欄位 `village_state.offering_accumulator`、UI 下拉選單與第二層資源選單、公告樣板、env var `OFFERING_THRESHOLD_PER_PLAYER`，並同步更新所有涉及的文件。

### 排除的替代方案

- 軟關閉（保留程式碼與 schema，僅在 UI 隱藏並停用結算邏輯）：會留下死程式碼與未使用欄位，增加維護負擔，且用戶已明確選擇完全移除。
- 移除功能但保留歷史資料遷移：需額外撰寫一次性遷移腳本供人工查閱，非目前需求範圍。

## Clarifications

<!-- Q: 移除範圍要用哪種方向？ / A: 完全移除，包含程式碼、DB 欄位、UI、通知、env var，並更新所有相關文件。 — resolved during refine stage -->

## MVP Scope / Not Doing

- 範圍內：移除奉獻行動的資料庫欄位、結算邏輯、UI 下拉選單/按鈕、公告樣板、env var，以及 `docs/db-schema.md`、`docs/engine/formula.md`、`docs/engine/action-resolver.md`、`docs/discord/ui-renderer.md`、`docs/discord/command-handler.md`、`docs/discord/notification.md` 等文件更新。
- 範圍外：不保留任何歷史 `offering_accumulator` 資料遷移或匯出；不新增 feature flag。

## Architecture Decisions

<!-- Key technical choices and rationale — added during plan stage -->

## Key Assumptions

- 移除 `village_state.offering_accumulator` 欄位屬安全操作，不影響其他系統的資料完整性（該欄位為奉獻系統獨有，未被其他功能引用）。
- `players.action_target` 欄位可繼續沿用於建設行動，不受移除奉獻影響。
- 現有正在進行中的奉獻行動（若有玩家 `action = 'offering'`）在部署後的處理方式不在此次範圍內特別處理，需於 plan 階段確認是否需要遷移腳本清理殘留狀態。

## Tasks

- [ ] Task 1: 待 plan 階段填寫

## Review Issues

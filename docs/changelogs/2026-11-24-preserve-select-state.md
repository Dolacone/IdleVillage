---
title: "選單變動不重設其他選單"
status: Draft
created: 2026-11-24
doc_type: change
last_reviewed: 2026-11-24
source_paths: []
scope: "Tracks this change from design through review."
---

## Problem Statement

> command checkbox 單一項目的變動不會把其他 checkbox reset
> 例：改動工具類型的時候，`鐵齒`與`無限`選項應該維持不變

改動一個選單時，同畫面其他已選的選單被清空。

```
工具強化：選 建設工具 → 鐵齒 → 無限 → 改選 採集工具
  工具類型：🌾 採集工具
  強化模式：（未選）
  執行次數：（未選）

自動工具：選 建設 → 3 小時 → 改選 加工廠
  建設目標：加工廠
  時數：（未選）
```

`docs/discord/command-handler.md` 的 `gear_type_select` 已寫「保留當前模式」，實作不符。

## Recommended Direction

選單保留已選的值，直到玩家改動它，或它的選項因其他選單改變而重建。

```
工具強化：選 建設工具 → 鐵齒 → 無限 → 改選 採集工具
  工具類型：🌾 採集工具
  強化模式：鐵齒
  執行次數：無限

自動工具：選 建設 → 3 小時 → 改選 加工廠
  建設目標：加工廠
  時數：3 小時

鐵齒 + 無限 → 🩸 獻祭素材 100 個
  強化模式：鐵齒
  執行次數：無限

鐵齒 + 無限 → 🔮 詞條管理 → ✨ 自動抽取 → 返回詞條管理 → ← 返回
  強化模式：鐵齒
  執行次數：無限
```

- 工具強化：改工具類型時保留強化模式與執行次數。
- 自動工具：改建設目標時保留時數。
- 獻祭素材後回到工具強化畫面，保留強化模式與執行次數。
- 從詞條管理（含自動抽取設定）返回工具強化畫面，保留強化模式與執行次數。

### Alternatives

| 方向 | 結果 |
| :--- | :--- |
| A：custom_id 攜帶其他選單的值（選定） | 沿用既有慣例 |
| B：從訊息現有元件的 default 讀回其他選單的值 | 詞條管理返回時讀不到 |
| C：Cog 內以玩家 ID 暫存選擇 | 與 custom_id 狀態混用 |

- 選 A：`upgrade_mode_select:{gear_type}:{count}`、`auto_affix_*:{gear}:{target}:{value}:{source}:{scope}` 已用 custom_id 攜帶選單狀態。
- 排除 B：詞條管理畫面沒有工具強化的選單，`back_to_gear` 無處讀回模式與次數。
- 排除 C：Bot 重啟後遺失。同一玩家開多個 Ephemeral 介面時互相覆寫。同一畫面出現兩種狀態來源。

## Key Assumptions

- 玩家換工具類型時，多數沿用同一強化模式與執行次數。
- 玩家獻祭或管理詞條後，多數回到原本的強化模式與執行次數繼續強化。

## Clarifications

<!-- Q: 自動工具改建設目標時清掉時數，是否一併修？ / A: 是，兩個畫面都修。 — resolved during idea stage -->
<!-- Q: 獻祭素材與詞條管理返回後清掉模式與次數，是否納入？ / A: 納入。 — resolved during idea stage -->

## MVP Scope / Not Doing

MVP Scope:

- 工具強化畫面改工具類型保留強化模式與執行次數。
- 自動工具畫面改建設目標保留時數。
- 獻祭素材、詞條管理返回後保留強化模式與執行次數。

Not Doing:

- 自動工具改工具時，建設目標與時數選單依新工具重建。
  - 選項依工具是否運行中與可加時數而變。
- 主介面改行動時，建設目標選單依行動顯示或隱藏。
- 詞條管理改工具類型時，詞條分組選單依新工具重建。
- 從主介面開啟工具強化，以及開啟詞條管理，維持不預設選中。
- 不改 renderer 已不產生的舊路由 `extract_affix:`、`clear_affix:`。

## Architecture Decisions

## Tasks

## Review Issues

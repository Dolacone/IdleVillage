---
title: "數字顯示加上千分位逗號"
status: Draft
created: 2026-11-16
doc_type: change
last_reviewed: 2026-11-16
source_paths: []
scope: "Tracks this change from design through review."
---

## Problem Statement

Bot 顯示的數字沒有千分位分隔，大數字難以閱讀。

```
村莊試煉達成！目標 750000 點行動產出已完成
共 12 位玩家瓜分了 7505 個 🌟萬能素材（25% 平均分配、75% 依貢獻度）：
貢獻 156618 (1331 素材)：𝕯𝖔𝖑𝖆
```

## Recommended Direction

所有玩家可見的數字都以 `,` 分隔千分位。

```
村莊試煉達成！目標 750,000 點行動產出已完成
共 12 位玩家瓜分了 7,505 個 🌟萬能素材（25% 平均分配、75% 依貢獻度）：
貢獻 156,618 (1,331 素材)：𝕯𝖔𝖑𝖆
```

- 範圍涵蓋所有 Discord 顯示文字：
  - 村莊 Dashboard 與主介面 Embed。
  - 工具強化、詞條管理、自動抽取、自動工具、試煉目標選單的 Embed 與元件 label/description。
  - Public 通知。
  - `/idlevillage-ranking` 與管理員介面。
- 等級（`Lv{n}`）也加逗號，例如 `Lv1,024`。
- 小數保留現有位數規則，只在整數部分加逗號。
- 數值本身、四捨五入與計算邏輯不變。

### Alternatives

| 方向 | 結果 |
| :--- | :--- |
| A：共用格式函式，在每個顯示點呼叫（選定） | 一處定義格式規則 |
| B：每個顯示點各自寫 `f"{n:,}"` | 小數與整數規則分散 |
| C：對最終訊息字串做正規表達式替換 | 會改壞時間戳記與 ID |

- 選 A：整數與小數格式只定義一次，所有顯示點一致。
- 排除 B：小數去除尾隨零的規則要在多處重複。
- 排除 C：`<t:{unix}:R>`、custom_id、玩家 ID fallback 也是數字，會被誤加逗號。

## Key Assumptions

- 玩家閱讀加逗號的數字比未加逗號快。
- 沒有玩家或外部工具從 Bot 訊息文字解析數字。

## Clarifications

<!-- Q: 等級（Lv）達到 1000 以上也加逗號嗎？ / A: 是，所有顯示數字一致，例如 Lv1,024。 — resolved during idea stage -->
<!-- Q: 新分支從哪裡開？ / A: 疊在 PR #16 分支 2026-11-05-remove-building-upgrade-notification 上，PR 目標為 main。 — resolved during idea stage -->

## MVP Scope / Not Doing

MVP Scope:

- 所有玩家可見數字加千分位逗號，包含等級。

Not Doing:

- 不改 Discord 時間戳記語法 `<t:{unix}:R>`。
- 不改 custom_id 與 Select option value；這些值會被程式解析。
- 不改 Modal 輸入欄位的預設值；管理員提交後程式會解析。
- 不改玩家 ID fallback 顯示；ID 是識別碼，不是數量。
- 不改 log 輸出。
- 不改數值縮寫（不使用 萬、K、M）。

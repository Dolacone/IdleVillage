---
title: "試煉獎勵改為 25% 均分 + 75% 依貢獻分配"
status: Draft
created: 2026-10-08
doc_type: change
last_reviewed: 2026-10-08
source_paths:
  - docs/changelogs/2026-10-08-trial-reward-equal-share.md
scope: "Tracks this change from design through review."
---

## Problem Statement

試煉達成時，獎勵池 `pool = target / TRIAL_REWARD_DIVISOR` 個萬能素材全部依貢獻比例分配：`reward_i = ceil(contribution_i / total_contribution × pool)`。貢獻低的玩家只分到極少量。

改為兩部分：

- 25% 獎勵池平均分給所有參加的玩家。
- 75% 獎勵池依貢獻比例分配（沿用現行比例制）。

## Recommended Direction

在 `trial_manager` 的達成流程中改寫每人獎勵公式，兩部分相加後只進位一次：

```text
N = count(contribution_i > 0)
reward_i = ceil(pool × 25% / N + contribution_i / total_contribution × pool × 75%)
```

25% 寫死為程式常數。試煉開始與達成通知的說明文字改為描述新分配方式，每行仍只顯示總獲得數。

替代方向：

- 兩部分各自 ceil 再相加：每人最多多發 2 個，超發量比現制高。不採用，原因是使用者選擇相加後 ceil。
- 均分部分 floor、貢獻部分 ceil：均分部分會因 floor 損失，`N` 大時低貢獻玩家幾乎拿不到保底。不採用，原因同上。

選擇相加後 ceil 的原因：每人只進位一次，總超發量上限維持在 `N - 1` 個，與現制同等級。

## Clarifications

- Q: 每人獎勵的進位方式？ / A: 兩部分相加後 ceil。
- Q: 「參加的人」怎麼定義？ / A: `trial_contributions` 中 contribution > 0 的玩家。自動工具貢獻歸擁有者，同樣算參加。
- Q: 25/75 比例要寫死還是可設定？ / A: 寫死在程式碼常數。
- Q: 試煉通知要怎麼呈現新分配方式？ / A: 只改說明文字，每行仍顯示總獲得數。
- Q: Jira ticket？ / A: 沒有。

## MVP Scope / Not Doing

MVP Scope:

- 試煉達成的每人獎勵公式改為 25% 均分 + 75% 依貢獻，相加後 ceil。
- 只有 contribution > 0 的玩家參與分配與列入 `participants`。
- 試煉開始與達成通知的說明文字改為描述新分配方式。
- 更新 trial-manager 與 notification 文件。

Not Doing:

- 不新增環境變數；`TRIAL_REWARD_DIVISOR` 與獎勵池大小不變。
- 通知每行不顯示均分/貢獻拆分明細。
- 不變更進度累加、逾時失敗、開啟試煉流程。

## Key Assumptions

- 25% 保底能提高低貢獻玩家的參與意願，上線後觀察每次試煉的參與人數是否增加。
- 高貢獻玩家的獎勵減少約 25% 不會降低其投入，上線後觀察高貢獻玩家的試煉貢獻量是否下降。
- 同一位玩家只有一列 `trial_contributions`（`user_id` 唯一鍵），多開帳號不在考量內。

## Architecture Decisions

## Tasks

## Review Issues

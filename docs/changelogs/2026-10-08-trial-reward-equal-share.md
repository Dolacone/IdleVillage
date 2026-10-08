---
title: "試煉獎勵改為 25% 均分 + 75% 依貢獻分配"
status: Draft
created: 2026-10-08
doc_type: change
last_reviewed: 2026-10-08
source_paths:
  - docs/changelogs/2026-10-08-trial-reward-equal-share.md
  - docs/discord/notification.md
  - docs/managers/trial-manager.md
  - src/core/notification.py
  - src/managers/trial_manager.py
  - tests/test_discord_notifications.py
  - tests/test_trial_manager.py
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

- 比例常數 `TRIAL_REWARD_EQUAL_SHARE_PERCENT = 25` 定義在 `src/managers/trial_manager.py` 模組層級。貢獻部分比例由 `100 - TRIAL_REWARD_EQUAL_SHARE_PERCENT` 推得，不另設常數。
- `_succeed_trial` 用 `fractions.Fraction` 計算每人獎勵，最後 `math.ceil` 一次。現行 `contribution / total × pool` 用浮點數，整數結果可能被算成 `x.0000001` 而多進位一，改用有理數消除此風險。
- 參與者篩選放在 SQL：`SELECT user_id, contribution FROM trial_contributions WHERE contribution > 0 ORDER BY contribution DESC`。`N` 與 `total_contribution` 都從篩選後的列計算。`contribution = 0` 的列不發獎勵，也不列入 `participants`。
- 試煉達成時 `progress >= target > 0`，因此 `N >= 1`，不需處理除以零。
- `src/core/notification.py` 從 `managers.trial_manager` 匯入 `TRIAL_REWARD_EQUAL_SHARE_PERCENT` 組通知文字，避免比例在兩處寫死後不一致。`src/core/settlement.py` 已匯入 `managers.trial_manager`，`managers` 不匯入 `core.notification`，不會循環匯入。
- `trial_start` 事件的 `reward_pool`（`src/cogs/actions.py`）與事件結構不變。

## Tasks

Dependency graph:

```
Task 1 (trial_manager reward formula + constant) -> Task 2 (notification wording)
```

Parallel groups: none. Task 2 imports the constant from Task 1. Implementation order: 1, 2.

- [ ] Task 1: Split the reward pool in `src/managers/trial_manager.py`. Tests in `tests/test_trial_manager.py`.
  - AC1: Module constant `TRIAL_REWARD_EQUAL_SHARE_PERCENT == 25`.
  - AC2: With `target=10000`, `TRIAL_REWARD_DIVISOR=100`, A contributes 9000 and B contributes 1000: A gets 80, B gets 20, `total_awarded == 100`. Under the old formula A would get 90 and B 10, so this test fails if the equal share is removed.
  - AC3: Rounding happens once per participant on the sum: with `target=1000`, contributions 334/333/333, each participant gets 4 and `total_awarded == 12`.
  - AC4: A `trial_contributions` row with `contribution = 0` receives no universal material, is not in `participants`, and does not count toward `N`. With target 10000, A=9000, B=1000, plus C=0: A gets 80, B gets 20.
  - AC5: Exact integer rewards do not over-round from float error: with `target=4000`, A contributes 3900 and B contributes 600, A gets exactly 31 (float math gives 32) and B gets 9.
  - AC6: Existing reward tests (`test_reaching_target_triggers_success_and_awards_universal_material`, `test_dynamic_target_drives_reward_pool_and_deadline`) still pass; update comments to describe the new formula.
- [ ] Task 2: Update trial notification text in `src/core/notification.py`. Tests in `tests/test_discord_notifications.py`.
  - AC1: `trial_start` last line equals `達成後共 {reward_pool} 個 🌟萬能素材：25% 由參與者平均分配，75% 依貢獻度分配`.
  - AC2: `trial_success` second line equals `共 {participant_count} 位玩家瓜分了 {total_awarded} 個 🌟萬能素材（25% 平均分配、75% 依貢獻度）：`.
  - AC3: Percentages come from `trial_manager.TRIAL_REWARD_EQUAL_SHARE_PERCENT`; a test that patches the constant to 30 sees `30%` and `70%` in both messages.
  - AC4: Participant lines, sort order, and 1900-character truncation are unchanged.

## Review Issues

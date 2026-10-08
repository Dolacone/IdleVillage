---
title: "試煉獎勵改為 25% 均分 + 75% 依貢獻分配"
status: Reviewed
created: 2026-10-08
doc_type: change
last_reviewed: 2026-10-08
source_paths:
  - docs/README.md
  - docs/changelogs/2026-10-08-trial-reward-equal-share.md
  - docs/discord/notification.md
  - docs/managers/player-manager.md
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

選擇相加後 ceil 的原因：每人只進位一次，總發放量上限為 `ceil(reward_pool) + N - 1`，與現制同等級。

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
- `src/core/notification.py` 以 `from managers import trial_manager` 匯入模組，在 `_format_event` 內讀取 `trial_manager.TRIAL_REWARD_EQUAL_SHARE_PERCENT` 組通知文字，避免比例在兩處寫死後不一致，測試也能 patch 模組屬性。`core/notification.py` 已匯入 `cogs.ui_renderer`，後者已匯入 `managers.trial_manager`，不會產生新的循環匯入。
- `trial_start` 事件的 `reward_pool`（`src/cogs/actions.py`）與事件結構不變。

## Tasks

Dependency graph:

```
Task 1 (trial_manager reward formula + constant) -> Task 2 (notification wording)
```

Parallel groups: none. Task 2 imports the constant from Task 1. Implementation order: 1, 2.

- [x] Task 1: Split the reward pool in `src/managers/trial_manager.py`. Tests in `tests/test_trial_manager.py`.
  - AC1: Module constant `TRIAL_REWARD_EQUAL_SHARE_PERCENT == 25`.
  - AC2: With `target=10000`, `TRIAL_REWARD_DIVISOR=100`, A contributes 9000 and B contributes 1000: A gets 80, B gets 20, `total_awarded == 100`. Under the old formula A would get 90 and B 10, so this test fails if the equal share is removed.
  - AC3: Rounding happens once per participant on the sum: with `target=1000`, A contributes 700 and B contributes 300: A gets 7, B gets 4, `total_awarded == 11`. Per-part ceil would give 8/5 (13); the old formula gives 7/3 (10).
  - AC4: A `trial_contributions` row with `contribution = 0` receives no universal material, is not in `participants`, and does not count toward `N`. With target 10000, call `add_progress(A, 9000)`, `add_progress(C, 0)`, then `add_progress(B, 1000)`: A gets 80, B gets 20, C gets nothing. Without the filter, `N = 3` gives A 76, B 16, C 9 and C appears in `participants`.
  - AC5: Exact integer rewards do not over-round from float error: with `target=48000`, A contributes 23200 then B contributes 24800, A gets 234 and B gets exactly 246 (float math with the same structure gives 246.00000000000003, which rounds up to 247).
  - AC6: Existing reward tests (`test_reaching_target_triggers_success_and_awards_universal_material`, `test_ceil_rounding_can_exceed_reward_pool`, `test_dynamic_target_drives_reward_pool_and_deadline`) still pass with unchanged assertions; update their comments to describe the new formula.
- [x] Task 2: Update trial notification text in `src/core/notification.py`. Tests in `tests/test_discord_notifications.py`.
  - AC1: `trial_start` last line equals `達成後共 {reward_pool} 個 🌟萬能素材：25% 由參與者平均分配，75% 依貢獻度分配`.
  - AC2: `trial_success` second line equals `共 {participant_count} 位玩家瓜分了 {total_awarded} 個 🌟萬能素材（25% 平均分配、75% 依貢獻度）：`.
  - AC3: `notification.py` uses `from managers import trial_manager` and reads `trial_manager.TRIAL_REWARD_EQUAL_SHARE_PERCENT` inside `_format_event` at call time. A test that patches `managers.trial_manager.TRIAL_REWARD_EQUAL_SHARE_PERCENT` to 30 sees `30%` and `70%` in both messages.
  - AC4: Participant lines, sort order, and 1900-character truncation are unchanged.

## Review Issues

- [x] [Major] Issue 1: `tests/test_trial_manager.py:468-472` (`test_exact_integer_rewards_do_not_over_round`, Task 1 AC5) cannot fail when the `Fraction` math is removed. Reverting `src/managers/trial_manager.py:180` to `reward_pool = info["target"] / divisor` and `:188` to `contribution / total_contribution * contribution_pool` makes A's value `5.0 + 26.0 = 31.0`, so `ceil` gives 31 and the test still passes (mutation run on a HEAD copy: `37 passed`). The comment `float math ceils to 32` and AC5's "float math gives 32" hold only for the ordering `pool*0.25/N + c/t*pool*0.75`, not for the implemented structure. Fix: use an input where the implemented structure over-rounds under float, for example `target=48000`, `add_progress(A, 23200)` then `add_progress(B, 24800)`: exact rewards A 234, B 246; float version gives B `246.00000000000003 -> 247`. Update AC5 and the test comment to match.
- [x] [Minor] Issue 2: `docs/README.md:36-39` links each recent change record (`2026-10-08-remove-upgrade-affixes.md` and earlier), but has no row for `changelogs/2026-10-08-trial-reward-equal-share.md`. AGENTS.md requires every doc to be reachable from `docs/README.md`. Fix: add a "Trial reward equal share change record" row and add `docs/README.md` to `source_paths`.

## Plan Review Issues

- [x] Issue 1: Task 1 AC3 cannot fail when the rounding rule changes. Contributions 334/333/333 with `target=1000` give 4/4/4 (total 12) under sum-then-ceil, under per-part ceil, and under the old formula; it also duplicates the existing `test_ceil_rounding_can_exceed_reward_pool`. Fix: replace AC3 with `target=1000`, A=700, B=300: A gets 7, B gets 4, `total_awarded == 11` (per-part ceil gives 8/5 = 13, old formula gives 7/3 = 10).
- [x] Issue 2: Task 1 AC6 omits `test_ceil_rounding_can_exceed_reward_pool`, whose comment `each share is ~3.33` describes the old formula. Fix: add it to AC6. Its assertions (4/4/4, total 12) still hold under the new formula (`ceil(0.833 + 2.505)`, `ceil(0.833 + 2.4975)`); update only the comment.
- [x] Issue 3: Task 2 AC3 does not fix the import form. `from managers.trial_manager import TRIAL_REWARD_EQUAL_SHARE_PERCENT` binds the value at import, so a test patching `managers.trial_manager.TRIAL_REWARD_EQUAL_SHARE_PERCENT` sees no change. Fix: state in Architecture Decisions and Task 2 AC3 that `notification.py` uses `from managers import trial_manager` and reads `trial_manager.TRIAL_REWARD_EQUAL_SHARE_PERCENT` inside `_format_event`; the test patches `managers.trial_manager.TRIAL_REWARD_EQUAL_SHARE_PERCENT`. The circular-import rationale also cites the wrong evidence: `core/notification.py` already imports `cogs.ui_renderer`, which imports `managers.trial_manager`; cite that chain.
- [x] Issue 4: `docs/managers/player-manager.md:78` still says trial universal material is distributed 「依貢獻度發放」. Fix: reword it to "依 `trial-manager` 的分配規則發放（25% 均分、75% 依貢獻度）" and add `docs/managers/player-manager.md` to `source_paths`.
- [x] Issue 5: The overage bound 「多最多 `N - 1` 個」 in `docs/managers/trial-manager.md` and Recommended Direction holds only when `reward_pool = target / TRIAL_REWARD_DIVISOR` is an integer; both values come from env config. The exact bound is `total_awarded <= ceil(reward_pool) + N - 1`. Fix: state that bound in both places.
- [x] Issue 6: Task 1 AC4 does not fix when C's zero row is created. A zero row only exists while the trial is active (`add_progress` with `output = 0`, from a `partial_output` of 0 in `src/core/settlement.py`). If the test calls `add_progress(C, 0)` after B triggers success, the call is a no-op and the test passes even without the `contribution > 0` filter. Fix: state the order in AC4: `add_progress(A, 9000)`, `add_progress(C, 0)`, then `add_progress(B, 1000)`. Also state the failing values: without the filter `N = 3`, so A gets 76, B gets 16, C gets 9 and appears in `participants`.

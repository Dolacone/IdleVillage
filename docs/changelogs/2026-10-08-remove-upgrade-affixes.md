---
title: "移除 ＡＰ退還 與 素材減免 詞條"
status: Draft
created: 2026-10-08
doc_type: change
last_reviewed: 2026-10-08
source_paths:
  - docs/changelogs/2026-10-08-remove-upgrade-affixes.md
scope: "Tracks this change from design through review."
---

## Problem Statement

詞條抽選池有 7 種，其中 `upgrade_ap_refund`（ＡＰ退還）與 `upgrade_cost_reduce`（素材減免）要從遊戲中移除。2026-10-07 20:59 快照（`bak/village.db.26100720`）共 3 格使用這兩種詞條：

| 玩家 | 工具 | 槽號 | 詞條 | 數值 |
| :--- | :--- | :--- | :--- | :--- |
| FFF | 採集 | 0 | `upgrade_ap_refund` | 3 |
| FFF | 戰鬥 | 1 | `upgrade_cost_reduce` | 4 |
| bilio | 戰鬥 | 0 | `upgrade_ap_refund` | 5 |

這些現存詞條改為 `material_drop`（素材掉落），槽號與數值不變。

## Recommended Direction

移除兩種詞條的定義、抽選資格、強化效果與顯示名稱。bot 啟動時以可重複執行的 UPDATE 把現存的兩種詞條改為 `material_drop`。

替代方向：

- 一次性手動腳本：deploy 前後由操作者對正式 DB 執行。不採用，原因是使用者選擇啟動時自動遷移。程式不再認得舊類型，手動漏跑會讓讀取詞條加成時出錯。
- 只停止抽出、保留既有效果：舊詞條繼續生效，新抽選不再出現。不採用，原因是使用者要求從遊戲中移除，現存詞條改成素材掉落。

選擇啟動遷移的原因：deploy 後自動套用，遷移與程式版本綁在一起，不需人工操作 Fly.io volume。

## Clarifications

- Q: 既有詞條用什麼方式轉換？ / A: bot 啟動時自動遷移。
- Q: 受影響玩家要通知嗎？ / A: 不通知。
- Q: 移除後抽選機率？ / A: 剩 5 種，等機率，各 20%。
- Q: Jira ticket？ / A: 沒有。
- Q: 數值怎麼轉？ / A: 維持相同 %，槽號不變，類型改為 `material_drop`。

## MVP Scope / Not Doing

MVP Scope:

- 抽選池（含單次抽取與自動抽取）移除兩種詞條，剩 5 種等機率。
- 自動抽取「特定效果」選單只列 5 種。
- 強化流程移除 AP 退還與素材消耗減免效果。
- 詞條名稱對照表移除兩種詞條。
- 啟動遷移把現存兩種詞條改為 `material_drop`。
- 更新 affix-manager、gear-manager、ui-renderer、notification、db-schema 文件。

Not Doing:

- 通知受影響玩家。
- `素材退還`（`upgrade_material_refund`）維持不變。
- 舊互動元件（已開啟的畫面帶舊類型的 custom_id）不另做相容處理，沿用現有驗證視為不合法輸入。
- 修改 `bak/` 內的備份檔與歷史 change document。

## Key Assumptions

- 移除兩種強化詞條不會明顯改變強化經濟；兩者全服只有 3 格，素材掉落已有 10 人使用。
- 等機率的 5 種抽選讓其他詞條出現率由 1/7 升為 1/5，上線後需觀察週期縮短與素材掉落的持有量是否進一步集中。
</content>
</invoke>

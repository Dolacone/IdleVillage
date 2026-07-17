---
title: "萬能素材擴大適用：詞條抽取/清除"
status: Draft
created: 2026-07-17
doc_type: change
last_reviewed: 2026-07-17
source_paths:
  - src/managers/affix_manager.py
scope: "Tracks extending universal material (萬能素材) fallback coverage from gear upgrade only to also cover affix extract/clear."
---

## Problem Statement

萬能素材（`materials_universal`）目前僅能作為工具強化（標準/墊檔/鐵齒）素材不足時的補足來源（見 `docs/changes/2026-07-14-universal-material.md`）。詞條抽取（`extract_affix`）與詞條清除（`clear_affix`）仍完全依賴該工具類型專屬素材，萬能素材無法用於這兩個動作。

需求：讓萬能素材也能用於詞條抽取/清除的素材消耗，規則與強化一致——優先扣除該類型專屬素材，專屬素材不足時才動用萬能素材補足差額；兩者相加仍不足則視為前置條件不滿足，不執行動作、不扣除任何資源。

## Recommended Direction

在 `affix_manager.extract_affix` 與 `clear_affix` 中，將現有的「僅檢查/扣除 `player_manager.get_material`/`spend_material`」邏輯，改為套用與 `gear_manager.attempt_upgrade` 相同的萬能素材補足模式：

```
cost = AFFIX_EXTRACT_COST（或 AFFIX_CLEAR_COST）
materials = get_material(gear_type)
universal = get_universal_material()
若 materials + universal < cost → raise ValueError（同現有行為，不扣除任何資源）

from_type = min(cost, materials)
若 from_type > 0：spend_material(gear_type, from_type)
shortfall = cost - from_type
若 shortfall > 0：spend_universal_material(shortfall)
```

此為就地修改兩個函式內既有的素材檢查段落，不新增函式簽章、不改變回傳值結構（`extract_affix`/`clear_affix` 回傳格式不變）。

### 為何直接在 affix_manager 內重複此邏輯，而非抽出共用 helper

`gear_manager.attempt_upgrade` 目前是將「本類型優先、差額用萬能素材補足」的三行邏輯直接寫在函式內（`src/managers/gear_manager.py:219-232`），並未抽出共用函式。維持相同風格，在 `affix_manager` 內以相同的三行邏輯就地實作，不新增 `player_manager` 層級的共用介面，避免這次只涉及「抽取/清除」的變更去牽動已驗證穩定的 `gear_manager` 既有實作。

## Clarifications

<!-- Q: 是否也要套用到 sacrifice_material（獻祭素材）？ / A: 使用者僅提及「抽/洗詞條」，不含獻祭，維持獻祭素材不吃萬能素材的現有規則。 — resolved during refine stage -->
<!-- Q: extract_affix/clear_affix 成功後是否有素材退還機制（類似 upgrade_material_refund）需要處理 from_type/universal 分帳？ / A: 無，詞條系統沒有素材退還詞條效果，抽取/清除消耗一律不退還，故不需要 upgrade_material_refund 那類分帳邏輯。 — resolved during refine stage -->

## MVP Scope / Not Doing

- 範圍內：
  - `affix_manager.extract_affix` 素材檢查/扣除邏輯改為「本類型優先、差額用萬能素材補足」。
  - `affix_manager.clear_affix` 同上。
  - 對應文件更新：`docs/managers/affix-manager.md`、`docs/discord/ui-renderer.md`（詞條操作段落補充萬能素材補足說明，比照工具強化子選單的既有寫法）。
- 範圍外：
  - `sacrifice_material`（獻祭素材）：使用者需求僅提及抽取/清除詞條，不含獻祭，維持現狀。
  - `clear_all_affixes`（鐵齒炸裂時的全清除）：本身無素材成本，不受影響。
  - 萬能素材的取得/掉落管道：仍維持既有「無法透過任何管道獲得」的佔位狀態，不在此變更範圍內。
  - UI 按鈕的 disabled 條件變更：`✨ 抽取詞條`/`🗑️ 清除詞條` 目前的 disabled 條件（詞條槽已滿／無詞條）不含素材是否足夠的判斷，本次不新增此判斷，維持現有「素材不足時執行才報錯」行為，與強化按鈕的即時 disabled 邏輯不同步（強化按鈕的 disabled 邏輯屬既有機制，不在本次範圍內擴充到詞條操作）。

## Key Assumptions

- 「抽/洗詞條」對應 `affix_manager.extract_affix` 與 `clear_affix` 兩個函式，不含 `sacrifice_material`、`clear_all_affixes`。
- 詞條系統沒有素材退還效果，因此不需要處理 `gear_manager` 那種「退還金額需排除萬能素材補足部分」的分帳問題。
- 素材不足時的行為維持現狀：`extract_affix`/`clear_affix` raise `ValueError`，不扣除任何資源。

## Architecture Decisions

（將於 plan 階段補充）

## Tasks

（將於 plan 階段補充）

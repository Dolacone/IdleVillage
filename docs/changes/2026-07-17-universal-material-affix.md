---
title: "萬能素材擴大適用：詞條抽取/清除"
status: Ready-to-implement
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
  - 對應文件更新（詳見 Task 3）：`docs/managers/affix-manager.md`、`docs/managers/player-manager.md`、`docs/discord/ui-renderer.md`、`docs/discord/command-handler.md`。
- 範圍外：
  - `sacrifice_material`（獻祭素材）：使用者需求僅提及抽取/清除詞條，不含獻祭，維持現狀。
  - `clear_all_affixes`（鐵齒炸裂時的全清除）：本身無素材成本，不受影響。
  - 萬能素材的取得/掉落管道：不變更既有取得管道（村莊試煉獎勵已是實際取得管道，見 `docs/managers/trial-manager.md`），本次僅擴大「使用」範圍到詞條抽取/清除。
  - UI 按鈕的 disabled 條件變更：`✨ 抽取詞條`/`🗑️ 清除詞條` 目前的 disabled 條件（詞條槽已滿／無詞條）不含素材是否足夠的判斷，本次不新增此判斷，維持現有「素材不足時執行才報錯」行為，與強化按鈕的即時 disabled 邏輯不同步（強化按鈕的 disabled 邏輯屬既有機制，不在本次範圍內擴充到詞條操作）。

## Key Assumptions

- 「抽/洗詞條」對應 `affix_manager.extract_affix` 與 `clear_affix` 兩個函式，不含 `sacrifice_material`、`clear_all_affixes`。
- 詞條系統沒有素材退還效果，因此不需要處理 `gear_manager` 那種「退還金額需排除萬能素材補足部分」的分帳問題。
- 素材不足時的行為維持現狀：`extract_affix`/`clear_affix` raise `ValueError`，不扣除任何資源。

## Architecture Decisions

1. 扣除順序固定「本類型專屬素材優先，差額由萬能素材補足」，與 `gear_manager.attempt_upgrade`（`src/managers/gear_manager.py:227-232`）一致，不提供來源選擇。
2. 前置檢查由 `mats < cost` 改為 `mats + universal < cost` 時 raise `ValueError`；沿用現有「不足即拒絕、不扣除任何資源」的模式。錯誤訊息比照 `attempt_upgrade` 附註萬能素材持有量（`need {cost}, have {mats} (+{universal} universal)`）。
3. 不新增 `player_manager` 共用 helper：`gear_manager` 目前將此三行邏輯內聯，維持相同風格在 `affix_manager` 內就地實作，避免牽動已驗證穩定的 `gear_manager`。詞條系統無素材退還效果，故不需要 `from_type`/universal 分帳（不同於 `upgrade_material_refund`）。
4. 依賴順序：`extract_affix`（Task 1）與 `clear_affix`（Task 2）彼此獨立，皆僅依賴 `player_manager` 既有的 `get_universal_material`/`spend_universal_material`（已於 2026-07-14 變更建立）。兩者可並行實作，本次仍循序執行。文件更新（Task 3）依賴 Task 1、2。

## Tasks

- [ ] Task 1: `extract_affix` 素材檢查/扣除改為萬能素材補足 [可與 Task 2 並行]
  - Files: `src/managers/affix_manager.py`
  - Tests: `tests/test_affix_manager.py` — 新增涵蓋：(a) 本類型素材足夠時不動用萬能素材、(b) 本類型不足但萬能素材補足後可抽取且兩者正確扣除、(c) 兩者相加仍不足時 raise `ValueError` 且不扣除任何資源（含詞條未寫入）；既有 `test_extract_raises_on_insufficient_materials`（本類型 0、萬能 0）需維持通過
  - Depends on: 無（`get_universal_material`/`spend_universal_material` 已存在）
  - Acceptance: 前置檢查為 `mats + universal >= cost`；扣除順序 `from_type = min(cost, mats)` 先扣本類型、`shortfall = cost - from_type` 扣萬能；不足時 raise `ValueError` 且不 INSERT 詞條、不扣任何素材；回傳值結構 `{slot_index, affix_type, value}` 不變；新增與既有測試全數通過

- [ ] Task 2: `clear_affix` 素材檢查/扣除改為萬能素材補足 [可與 Task 1 並行]
  - Files: `src/managers/affix_manager.py`
  - Tests: `tests/test_affix_manager.py` — 新增涵蓋：(a) 本類型素材足夠時不動用萬能素材、(b) 本類型不足但萬能素材補足後可清除且兩者正確扣除、(c) 兩者相加仍不足時 raise `ValueError` 且不扣除任何資源（含詞條未被刪除）
  - Depends on: 無
  - Acceptance: 前置檢查為 `mats + universal >= cost`；扣除順序同 Task 1；不足時 raise `ValueError` 且不 DELETE 詞條、不扣任何素材；回傳值結構 `{affix_type, value}` 不變；新增與既有測試全數通過

- [ ] Task 3: 文件更新
  - Files: `docs/managers/affix-manager.md`, `docs/managers/player-manager.md`, `docs/discord/ui-renderer.md`, `docs/discord/command-handler.md`
  - Tests: 無（純文件）
  - Depends on: Task 1, Task 2
  - Acceptance:
    - `affix-manager.md`：`extract_affix`/`clear_affix` 介面說明改為「先扣本類型素材，不足差額由萬能素材補足；兩者相加仍不足時 raise ValueError」，新增 Changelog 條目
    - `player-manager.md`：「萬能素材」章節（現述「僅限工具強化」「詞條抽取/清除不吃萬能素材」）改為工具強化 + 詞條抽取/清除皆適用；同步 `materials_universal` 欄位表格描述與 Changelog
    - `ui-renderer.md`：詞條操作段落補充「素材不足時自動用萬能素材補足」，比照工具強化子選單寫法
    - `command-handler.md`：`extract_affix`/`clear_affix` 路由描述由「消耗對應素材」改為「先扣對應素材，不足由萬能素材補足」
    - 四份文件 `last_reviewed` 更新為 2026-07-17

## Plan Review Issues

- [x] [Major] Task 3 的文件範圍不完整。`docs/managers/player-manager.md` 目前在「萬能素材」章節明確寫著「僅限工具強化」且「詞條抽取/清除不吃萬能素材」；若本次實作完成但不更新這份 canonical owner 文件，SSOT 會直接與實作衝突。至少應把 `docs/managers/player-manager.md` 納入 Task 3，並同步更新該段敘述、Changelog 與 `last_reviewed`。→ 已將 `player-manager.md` 納入 Task 3 檔案清單與 acceptance。
- [x] [Minor] `docs/discord/command-handler.md` 也會過時：目前互動路由表把 `extract_affix` / `clear_affix` 描述成「消耗對應素材」，未反映「先扣專屬素材，不足時由萬能素材補足」的新規則。若 Task 3 目的是把玩家互動相關文件補齊，這份模組文件也應納入更新集合。→ 已將 `command-handler.md` 納入 Task 3。
- [x] [Minor] 計畫文件本身沿用了已過期前提：`MVP Scope / Not Doing` 仍寫「萬能素材無法透過任何管道獲得」，但 repo 內 `src/managers/trial_manager.py` 與 `docs/managers/trial-manager.md` 已經把村莊試煉獎勵實作為萬能素材的實際取得管道。這不影響本次 fallback 邏輯，但會讓設計理由建立在錯誤現況上，建議在計畫內改成「不變更既有取得管道」而不是重述錯誤事實。→ 已改為「不變更既有取得管道」。
- [x] [Minor] `MVP Scope / Not Doing` 的「範圍內 → 對應文件更新」仍只列 `affix-manager.md`、`ui-renderer.md`，未與已擴充為四份文件的 Task 3（新增 `player-manager.md`、`command-handler.md`）同步。實作者若先看 Scope 會漏掉這兩份文件，建議把 Scope 內的文件清單補齊為四份，或改為指向 Task 3。→ 已將 Scope 文件清單補齊為四份並指向 Task 3。

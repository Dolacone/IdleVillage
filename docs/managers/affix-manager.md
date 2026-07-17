---
title: "Module: affix-manager"
doc_type: module
last_reviewed: 2026-07-17
source_paths:
  - src/managers/affix_manager.py
---

# Module: affix-manager

管理工具詞條的 CRUD、槽位計算與加成彙總。其他模組透過 `get_affix_bonuses()` 取得彙總值，不直接查 `gear_affixes` 表。

## 詞條類型

| 代碼 | 效果（每條 1–5% 整數，可疊加）|
| :--- | :--- |
| `efficiency` | 對應行動 output +X% |
| `material_drop` | 對應素材掉落率 +X% |
| `upgrade_success` | 該工具強化成功率 +X% |
| `upgrade_cost_reduce` | 該工具強化素材消耗 -X%（floor，最低 1） |
| `upgrade_ap_refund` | 強化成功時 X% 機率退還 1 AP |
| `upgrade_material_refund` | 強化成功時 X% 機率退還消耗素材 |
| `cycle_time_reduce` | 行動週期縮短 X% |

## 槽位系統

- 可用槽數 = `floor(gear_level / AFFIX_SLOT_INTERVAL)`
- 槽位 0-based；槽位滿時抽取鎖定，需先清除才能抽新的
- 鐵齒炸裂（等級歸零）時，所有詞條清除

## 操作介面

- `slot_count(gear_level) -> int` — 計算可用槽數
- `get_affixes(db, user_id, gear_type) -> list[dict]` — 回傳 `[{slot_index, affix_type, value}, ...]`
- `get_affix_bonuses(db, user_id, gear_type) -> dict[str, int]` — 彙總各類型總加成
- `extract_affix(db, user_id, gear_type, gear_level, now) -> dict` — 消耗 `AFFIX_EXTRACT_COST` 對應素材，隨機抽一條詞條填入第一個空槽；回傳 `{slot_index, affix_type, value}`；滿槽時 raise ValueError
- `clear_affix(db, user_id, gear_type, slot_index, gear_level, now) -> dict` — 消耗 `AFFIX_CLEAR_COST` 對應素材，清除指定槽；回傳 `{affix_type, value}`；空槽時 raise ValueError

素材消耗規則（`extract_affix`/`clear_affix` 共用）：先扣該工具類型自身素材（最多扣至消耗量），不足差額由萬能素材（`materials_universal`）補足；兩者相加仍不足時 raise ValueError，不扣除任何素材、不改變詞條。詞條系統無素材退還效果，故不需區分自身/萬能來源。萬能素材詳見 `managers/player-manager.md`。`clear_all_affixes` 無素材成本，不受此規則影響。
- `clear_all_affixes(db, user_id, gear_type, now)` — 清除所有詞條（無素材成本，鐵齒炸裂時呼叫）

## 環境變數

| 變數 | 說明 |
| :--- | :--- |
| `AFFIX_SLOT_INTERVAL` | 每 N 工具等級解鎖 1 槽（預設 5） |
| `AFFIX_EXTRACT_COST` | 抽取消耗對應素材數量（預設 1） |
| `AFFIX_CLEAR_COST` | 清除消耗對應素材數量（預設 3） |

## Changelog

- 2026-07-17: `extract_affix`/`clear_affix` 素材消耗改為「自身素材優先、差額由萬能素材補足」；前置檢查由 `mats >= cost` 改為 `mats + universal >= cost`，不足時 raise ValueError 且不扣除任何資源。
- 2026-05-22: 新增模組。

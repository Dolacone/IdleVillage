---
title: "新素材：萬能素材"
status: Draft
created: 2026-07-14
doc_type: change
last_reviewed: 2026-07-14
source_paths: []
scope: "Tracks introduction of the universal material (萬能素材) placeholder and its use as a shortfall fallback during gear upgrade."
---

## Problem Statement

新增第 5 種素材「萬能素材」：目前無法透過任何管道獲得（僅作為未來機制的佔位），但規則已生效：可作為任意工具類型的素材使用。玩家在強化工具時，若原本工具類型的素材不足，優先扣除該類型素材，不足的差額由萬能素材補足；若加上萬能素材仍舊不足，則無法進行該次強化。

## Recommended Direction

新增 `materials_universal` 欄位（`players` 表），素材系統維持既有介面（`addMaterial` / `spendMaterial` / `setMaterial`）並讓 `type` 參數多支援 `"universal"` 一種值。強化流程（`gear-manager.attempt_upgrade` / `get_upgrade_info`）的素材檢查與扣除邏輯改為：

```
shortfall = max(0, material_cost - materials[gear_type])
若 materials_universal < shortfall → 素材不足，無法強化（同現有行為，不扣除任何資源）
否則：
  materials[gear_type] -= min(material_cost, materials[gear_type])
  materials_universal -= shortfall
```

範圍僅限強化工具（三種模式：標準/墊檔/鐵齒）的素材消耗；獻祭素材（`sacrifice_material`）與詞條抽取/清除（`affix-manager`）維持現有素材規則，不吃萬能素材（使用者需求明確指向「強化」，其餘消耗行為不在範圍內，避免未經確認的規則擴張）。

素材掉落（`player-manager.md` 素材系統）與獲取管道維持不變，萬能素材不加入任何掉落表；目前僅能透過管理員介面（`/idlevillage-manager` 編輯素材）設定，做為佔位驗證用途。

### 排除的替代方案

- 萬能素材套用到所有素材消耗行為（強化、獻祭、詞條抽取/清除）：使用者需求明確僅提及「強化」，擴大範圍屬未確認假設，且會使獻祭/詞條的素材語意複雜化，故排除。
- 提供玩家手動「兌換」萬能素材為指定類型的操作（而非強化時自動補差額）：使用者描述的是強化時「自動使用」以補差額，而非手動兌換介面；手動兌換是額外未要求的互動流程，故排除。

## Clarifications

<!-- Q: 萬能素材是否套用到獻祭素材與詞條抽取/清除的素材消耗？ / A: 不套用，僅限強化工具（標準/墊檔/鐵齒）三種模式。 — resolved during refine stage -->
<!-- Q: 萬能素材目前如何取得？ / A: 目前無任何掉落或產出管道，僅能由管理員透過 /idlevillage-manager 編輯素材數量設定，作為佔位驗證用途。 — resolved during refine stage -->

## MVP Scope / Not Doing

- 範圍內：
  - `players` 表新增 `materials_universal` 欄位（DB schema）。
  - `player-manager` 素材操作介面（`addMaterial`/`spendMaterial`/`setMaterial`/`getMaterial`）支援 `"universal"` 類型。
  - `gear-manager.attempt_upgrade` 與 `get_upgrade_info` 的素材檢查/扣除邏輯改為「本類型優先、差額用萬能素材補足」。
  - `/idlevillage` 主介面與工具強化子選單 Embed 顯示萬能素材持有量。
  - `/idlevillage-manager` 玩家管理員介面新增萬能素材的顯示與編輯欄位。
  - 對應文件更新：`docs/db-schema.md`、`docs/managers/player-manager.md`、`docs/managers/gear-manager.md`、`docs/discord/ui-renderer.md`、`docs/discord/command-handler.md`。
- 範圍外：
  - 萬能素材的任何獲取/掉落管道（保持「目前無法獲得」的佔位狀態）。
  - 獻祭素材、詞條抽取/清除套用萬能素材。
  - 玩家自助的素材兌換介面。

## Key Assumptions

- 「強化」僅指 `gear-manager` 的 `attempt_upgrade`（標準/墊檔/鐵齒三種模式），不含 `sacrifice_material`。
- 萬能素材佔位期間僅能由管理員透過既有 `setMaterial` 管理介面寫入，不需要額外的獲取管道設計。
- 素材不足時「無法進行動作」沿用現有行為：不消耗任何 AP 或素材，維持前置檢查即拒絕的模式。

## Architecture Decisions
<!-- Key technical choices and rationale — added during plan stage -->

## Tasks
- [ ] Task 1: ...

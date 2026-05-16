---
title: "標準升級成功率納入鐵齒炸裂等級加成"
status: Draft
created: 2026-05-16
doc_type: change
last_reviewed: 2026-05-16
source_paths: []
scope: "Tracks this change from design through review."
---

## Problem Statement

目前鐵齒炸裂等級（`risky_failed_levels`）只對鐵齒模式的成功率有加成效果，標準模式完全無法受益。玩家在鐵齒失敗後切換回標準模式，過去的犧牲沒有任何補償，導致鐵齒風險回報感不足。

## Recommended Direction

在標準（normal）模式的成功率公式中加入與鐵齒模式相同的 `risky_failed_levels` 加成項：

```
# 修改後的標準模式公式：
final_rate = base_rate + pity_count × GEAR_PITY_BONUS + risky_failed_levels × 0.0001
```

讓兩種模式共享相同的 `risky_failed_levels` 加成邏輯，使鐵齒炸裂的代價在任何模式下都能兌換成長期補償。

## Clarifications

Q: 標準模式套用 `risky_failed_levels` 的加成倍率應該是多少？
A: 與鐵齒相同（×0.0001，即每炸1級+0.01%）。

Q: 是否要對標準模式的 `risky_failed_levels` 加成設上限？
A: 不設上限，與鐵齒模式一致。

## MVP Scope / Not Doing

**做：**
- 標準模式成功率公式加入 `risky_failed_levels × 0.0001`
- 更新 `get_upgrade_info` 在標準模式下也回傳 `risky_failed_levels` 與 `risky_bonus_pct`（或將此資訊納入現有回傳格式）
- 更新 `docs/managers/gear-manager.md` 中的成功率公式文件

**不做：**
- 不更改倍率（維持 0.0001）
- 不為標準模式設置 risky_failed_levels 加成的獨立上限
- 不更動墊檔（buffer）模式的公式

## Architecture Decisions

## Tasks

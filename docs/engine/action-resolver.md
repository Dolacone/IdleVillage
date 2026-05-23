---
title: "Module: action-resolver"
doc_type: module
last_reviewed: 2026-05-23
source_paths:
  - src/core/settlement.py
---

# Module: action-resolver

處理單一玩家在單一週期內的行動結算。由 cycle-engine 逐一呼叫。

## 輸入

- 玩家當前行動類型。DB stored value: `gathering`, `building`, `combat`, `research`, or null。
- 玩家當前建設目標。僅 `action = building` 時需要。
- Discord UI 顯示使用繁體中文，resolver 只處理英文 stored value。

## 結算流程

```
1. 若未設定行動 → 跳過，結束。

2. 計算完整週期消耗（消耗量見 formula.md 環境變數 FOOD_COST / WOOD_COST / KNOWLEDGE_COST）。

3. 資源扣除：
   對每個本次需要的資源：
     若 resource_current < resource_cost → shortage_flag = true
     resource_after = max(0, resource_current - resource_cost)

4. 計算基礎產出（呼叫 formula 模組）：
   output = BASE_OUTPUT × (1 + stage_bonus + gear_bonus + facility_bonus)
   output = floor(output)

5. 套用資源不足懲罰：
   若 shortage_flag：settlement_output = floor(output × 0.5)
   否則：settlement_output = output

   shortage_flag 是 boolean，不會因多種資源不足而多重疊加。

6. 分配產出：
   gathering → 村莊食物 += settlement_output，村莊木頭 += settlement_output
   building → 目標建築 XP += settlement_output（呼叫 building-manager）
   combat → 村莊知識 += settlement_output
   research → 研究所 XP += settlement_output（呼叫 building-manager；target 固定為 research_lab）

7. 關卡進度 += output（呼叫 stage-manager）
   關卡進度使用資源不足懲罰前的 output。
   若關卡已逾時，stage-manager 只對關卡進度套用逾時倍率。

8. 完整週期 settlement 依 player-manager 的有效素材掉落率獲得 +1 對應素材。
   普通關同類 action 與升級關全部 action 使用加倍掉落率。
   素材掉落獨立判定，不受資源不足或關卡逾時影響。
```

## 行動類型參考表

| Stored value | UI 顯示 | 食物外額外消耗 | 產出目標 | 玩家素材欄位 |
| :--- | :--- | :--- | :--- | :--- |
| `gathering` | 採集 | 無 | 食物 + 木頭（各一份 output） | `materials_gathering` |
| `building` | 建設 | 木頭 WOOD_COST | 指定建築 XP | `materials_building` |
| `combat` | 戰鬥 | 木頭 WOOD_COST | 知識 | `materials_combat` |
| `research` | 研究 | 知識 KNOWLEDGE_COST | 研究所 XP | `materials_research` |
| `offering` | 奉獻 | 玩家選定物資（消耗量 = 四種行動產出合計） | 無（不產出資源/XP/素材/關卡進度） | 無 |

## 奉獻行動結算

奉獻行動的結算邏輯獨立於一般產出路徑：

1. 照常扣除 `FOOD_COST`（基礎維持費，同其他行動）。
2. 計算 `offering_cost = Σ floor(output_type)` for {gathering, building, combat, research}，使用各自的 gear/facility/stage bonus。
3. 實際消耗量 = `min(村莊 action_target 資源餘額, offering_cost)`。
4. 扣除實際消耗量；`village_state.offering_accumulator += 實際消耗量`。
5. 若 `offering_accumulator >= total_players × OFFERING_THRESHOLD_PER_PLAYER`：
   - 全員 `materials_gathering/building/combat/research += 1`。
   - `offering_accumulator = 0`。
   - 發送奉獻達標通知。
6. 無 settlement_output，無關卡進度，無素材掉落。

`action_target` 儲存玩家選定資源類型：`food`、`wood`、`knowledge`。

## Partial cycle

Partial cycle timing and ratio rules are owned by `engine/cycle-engine.md`.
This module applies the cost and output values passed by cycle-engine using the same shortage and distribution rules as a full settlement.

## 懲罰說明

任一所需資源不足時，settlement output ×0.5。多種資源同時不足仍只套用一次 ×0.5。

## Changelog

- 2026.05.08.00: Material drop step now references stage-matching effective drop rate.

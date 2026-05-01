# Module: action-resolver

處理單一玩家在單一週期內的行動結算。由 cycle-engine 逐一呼叫。

## 輸入

- 玩家當前行動類型（採集 / 建設 / 戰鬥 / 研究 / 未設定）
- 玩家當前建設目標（若行動為建設）

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
   採集 → 村莊食物 += settlement_output，村莊木頭 += settlement_output
   建設 → 目標建築 XP += settlement_output（呼叫 building-manager）
   戰鬥 → 村莊知識 += settlement_output
   研究 → 研究所 XP += settlement_output（呼叫 building-manager）

7. 關卡進度 += output（呼叫 stage-manager）
   關卡進度使用資源不足懲罰前的 output。
   若關卡已逾時，stage-manager 只對關卡進度套用逾時倍率。

8. 完整週期 settlement 有 MATERIAL_DROP_RATE 機率獲得 +1 對應素材（呼叫 player-manager）。
   素材掉落獨立判定，不受資源不足或關卡逾時影響。
```

## 行動類型參考表

| 行動 | 食物外額外消耗 | 產出目標 | 玩家素材 |
| :--- | :--- | :--- | :--- |
| 採集 | 無 | 食物 + 木頭（各一份 output） | 工具素材（MATERIAL_DROP_RATE） |
| 建設 | 木頭 WOOD_COST | 指定建築 XP | 建設素材（MATERIAL_DROP_RATE） |
| 戰鬥 | 木頭 WOOD_COST | 知識 | 武器素材（MATERIAL_DROP_RATE） |
| 研究 | 知識 KNOWLEDGE_COST | 研究所 XP | 研究素材（MATERIAL_DROP_RATE） |

## Partial cycle

Partial cycle timing and ratio rules are owned by `engine/cycle-engine.md`.
This module applies the cost and output values passed by cycle-engine using the same shortage and distribution rules as a full settlement.

## 懲罰說明

任一所需資源不足時，settlement output ×0.5。多種資源同時不足仍只套用一次 ×0.5。

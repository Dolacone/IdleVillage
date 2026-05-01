---
title: "Module: resource-manager"
doc_type: module
last_reviewed: 2026-05-01
source_paths:
  - src/managers/resource_manager.py
---

# Module: resource-manager

管理村莊共用資源池（食物、木頭、知識）。

## 資源種類

| 資源 | 圖示 | 初始值 | 來源 | 消耗方 |
| :--- | :---: | :--- | :--- | :--- |
| 食物 | 🌾 | 0 | 採集 | 所有行動 |
| 木頭 | 🪵 | 0 | 採集 | 建設、戰鬥 |
| 知識 | 🧠 | 0 | 戰鬥 | 研究 |

> 各資源的每週期消耗量與不足懲罰規則，見 `engine/formula.md`（環境變數）與 `engine/action-resolver.md`（結算邏輯）。

## 操作介面（供其他模組呼叫）

- `deposit(type, amount)` — 增加指定資源
- `withdraw(type, amount)` — 扣除指定資源（不得低於 0）
- `balance(type)` — 查詢當前數量
- `canAfford(type, amount)` — 確認是否足夠（回傳 boolean）

## 生產鏈

```
採集 ──→ 食物 + 木頭
               │
               ├──→ 建設（消耗木頭）──→ 建築 XP
               │
               └──→ 戰鬥（消耗木頭）──→ 知識
                                          │
                                          └──→ 研究（消耗知識）──→ 研究所 XP
```

## 設計說明

- 資源池為全伺服器共用，無玩家個人庫存。
- 村莊初始資源為 0，開局天然引導玩家先採集。
- 資源無上限，不需管理溢出。

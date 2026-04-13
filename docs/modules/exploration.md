# Module: Exploration

定義探索判定的公式、發現機率分配與節點容量限制。

### 1. 探索判定 (Exploration Check)

- 判定公式: (AGI + PER) / 2 / 100 * EXPLORING_BASE_CHANCE。
- 基礎機率: EXPLORING_BASE_CHANCE 預設值參見環境變數。

### 2. 發現分配 (Discovery Distribution)

當判定成功時，系統會以等機率 (各 25%) 隨機從以下類別中選擇一種進行補充或建立：
- 糧食節點 (Food Node)
- 木材節點 (Wood Node)
- 石材節點 (Stone Node)
- 威脅節點 (Threat Node)

### 3. 節點與容量規則 (Node Rules)

- 單一性 (Singleton): 每個村莊每種資源或威脅僅存在一個全域節點。
- 儲量上限: 所有資源節點的儲量與威脅節點的 HP，上限統一為村莊目前倉庫容量的 2 倍 (Storage Capacity * 2)。
- 威脅累積速度: 若發現結果為威脅節點，增加之 HP 數值為同等判定下資源產出量的 10%。
- 永久性: 威脅節點不具備效期，不會自動逃跑或消失，直到 HP 歸零為止。

## Changelog
- 2026.04.13.00: Initial exploration module definition. Centralized discovery chances, node limits, and threat scaling. - See [2026.04.13.00.md](../changelogs/2026.04.13.00.md)

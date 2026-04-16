# Module: Tokens

定義 Token 的分類、獲取機制、個人加成與集體使用邏輯。

### 1. Token 獲取與分類 (Acquisition & Categories)

- 獲取機率: 每完成一個 Action Cycle (且行動不為 idle)，系統 100% 贈予 1 個對應類別的 Token。
- 類別定義:
  - gathering: 包含伐木 (gathering_wood)、採集糧食 (gathering_food)、採礦 (gathering_stone)。
  - exploring: 包含探索 (exploring)。
  - building: 包含建築 (building)。
  - attacking: 包含攻擊 (attack)。
- 持有權: Token 為玩家個人持有，資料儲存於 tokens 表中。

### 2. 個人加成 (Self-Buffs)

- 消耗: 每次消耗所選數量的對應類別 Token。可選數量為 1, 2, 3, 5, 10, 25, 50。
- 持續時間: 每 1 個 Token 提供 `3 * ACTION_CYCLE_MINUTES`。總持續時間為 `quantity * 3 * ACTION_CYCLE_MINUTES`。
- 效果: 當玩家執行相同類別的行動時, 該行動的效率公式額外獲得 `+100` 總素質。
- 套用方式: 加成只在公式計算時生效, 不會寫回 `player_stats` 持久資料。
- 對應規則:
  - gathering Token: 所有 gathering 行動都獲得 `+100` 總素質。`gathering_food` 套用於 `PER + KNO + 100`; `gathering_wood` 與 `gathering_stone` 套用於 `STR + END + 100`。
  - exploring Token: `AGI + PER + 100`。
  - building Token: `KNO + END + 100`。
  - attacking Token: `STR + AGI + 100`。
- 覆蓋與堆疊規則:
  - 同類加成: 再次使用同類 Token 會延長持續時間。延長量為 `quantity * 3 * ACTION_CYCLE_MINUTES`，基準點為目前有效的 expiration time。
  - 異類加成: 使用不同類別的 Token 會立即覆蓋舊有加成。
  - 時間重置: 異類覆蓋時，舊加成的所有剩餘時間會被完全清空，並將持續時間重設為 `quantity * 3 * ACTION_CYCLE_MINUTES`，起算點為使用當下的 `now`。

### 3. 村莊保護 (Village Protection)

- 消耗: 消耗所選數量的任一類別 Token。可選數量為 1, 2, 3, 5, 10, 25, 50。
- 持續時間: 每 1 個 Token 提供 `1 * ACTION_CYCLE_MINUTES`。總持續時間為 `quantity * ACTION_CYCLE_MINUTES`。
- 效果: 減少該村莊 50% 的建築 XP 損耗 (Village Decay)。
- 堆疊規則: 時間採累加制，無上限。若保護已生效，新的持續時間加在目前有效的 expiration time 後；若保護未生效，則從使用當下的 `now` 起算。

### 4. 村莊命令 (Village Command)

- 消耗: 消耗 10 個指定類別的 Token。
- 設定: 玩家可指定村莊目前的發展方針 (如 gathering_wood)。
- 介面規則: 玩家需在 Token 介面中選擇本次要消耗的 Token 類型。
- 影響: 
  - 所有狀態為 idle 的玩家在結算時會自動執行該命令。
  - 若命令因資源不足或節點不存在而失效，則自動退回基礎 idle 邏輯 (產出糧食)。
- 效期: 永不逾期，直到下一個玩家使用 Token 進行覆蓋。

### 5. 指令介面 (Commands)

- /idlevillage-tokens (Ephemeral, Embed Menu)
  - 功能: 集中管理個人 Token 持有量、加成、村莊保護與發展命令。
  - 批量觸發 (v2026.04.16.00): 個人加成與村莊保護可選擇一次消耗多個代幣 (1, 2, 3, 5, 10, 25, 50)。
  - 持續時間提示: 介面需明確提示 1 個代幣對應的週期數 (加成 3 週期, 保護 1 週期)。
  - 驗證規則: 若玩家持有量不足所選數量, 系統必須拒絕本次操作, 並且不可扣除任何 Token、不可改動既有 expiration time。
  - 命令成本: 村莊命令固定消耗所選代幣類型的 10 個 Token。

## Changelog
- 2026.04.13.00: Initial token module definition with categories, self-buffs, protection, and village command logic. - See [2026.04.13.00.md](../changelogs/2026.04.13.00.md)
- 2026.04.16.00: Merged redundant command docs and added support for multi-token selection (1-50) with duration cues. - See [2026.04.16.00.md](../changelogs/2026.04.16.00.md)

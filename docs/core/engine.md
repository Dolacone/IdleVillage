# Core: Engine (Trigger and Settlement)

定義系統如何實作延遲計算、公告同步與狀態同步, 確保不同 AI Session 之間的實作邏輯一致.

### 1. 觸發層級 (Trigger Levels)
- 個體主動觸發 (Player-Active Trigger):
  - 來源: `/idlevillage`、行動切換、提交按鈕、Refresh。
  - 順序: 先結算村莊，再結算玩家，最後依公告節流規則決定是否同步公開公告。
- 集體介面觸發 (Village-Collective Trigger):
  - 來源: `/idlevillage` 開啟主介面、`/idlevillage-announcement` 建立或刷新公告、管理介面調整資源與節點。
  - 順序: 先同步村莊狀態，再渲染玩家介面或公告內容。
- 被動自動觸發 (Watcher Trigger):
  - 來源: 背景 Watcher Heartbeat。
  - 對象: `completion_time <= now` 的玩家，以及所有需要進行村莊損耗結算的村莊。
  - 順序: 先做 inactivity scan，將符合條件的玩家標記為 `missing`，再進行玩家與村莊結算。

### 2. 標準結算流程 (Settlement Steps)

所有的結算必須精確到秒, 並遵循以下順序:
1. 若玩家存在已逾期的完整循環, 必須以 while-loop 逐個循環回補, 不可跳到 Now.
2. 每個循環切片都先重算玩家素質: 依 player_actions_log 最近 150 筆紀錄更新 player_stats.
3. 計算 Delta: SliceEnd - SliceStart.
4. 紀錄行動片段:
   - 若本次結算完成了一個完整行動週期且玩家不是 missing, 寫入一筆 `player_actions_log` 素質紀錄.
   - `player_actions_log` 不記錄 action name, 而是記錄該完整週期提供的五項素質增量.
   - UI refresh, interrupted settlement, 或其他未滿一個週期的 partial slice 不寫入 `player_actions_log`.
   - 每位玩家在 `player_actions_log` 中只保留最新 150 筆完整週期紀錄.
5. 資源 / XP 結算 (v2026.04.13.00):
   - Token 產出: 每完成一個循環且行動不為 idle，系統贈予 1 個對應類別 Token (分類詳見 docs/modules/tokens.md)。
   - idle: 若村莊存有有效村莊命令且條件符合，結算時優先嘗試執行該命令 (行為詳見 docs/modules/village.md)。
   - gathering: 依節點儲量與玩家素質結算產出。
   - attack:
     - 扣除威脅節點 HP。
     - 產出資源: 每 1 點傷害產出 1 黃金與 1 隨機基礎資源。
   - building: 偵測 XP 變動觸發升降級公告。
   - exploring: 執行判定並依機率分配補充節點儲量 (機率分配詳見 docs/modules/exploration.md)。
   - 資源入庫: 套用倉庫容量限制與溢出處理。
6. 村莊損耗結算 (Village Settlement):
   - 計算損耗 XP 並扣除。
   - 套用威脅加倍與保護減免 (加乘規則詳見 docs/modules/village.md)。
7. 資料更新:
   - 玩家狀態欄位: 更新 `players.status`、`players.target_id`、`players.last_update_time`、`players.completion_time`。
   - 素質欄位: 更新 `player_stats` 對應玩家的快取數值與 `last_calc_time`。
   - 村莊欄位: 更新 `villages.last_tick_time`、`villages.last_announcement_updated`，以及公告訊息定位欄位。
   - 資源與建築欄位: 更新 `village_resources`、`buffs`、`resource_nodes`、`monsters`。
   - Token、保護與村莊命令的資料結構與公式詳見 `docs/modules/tokens.md`。

### 3. Action Cycle 啟動 (Lease Start) (v2026.04.10.00)
- 啟動前檢查:
  - 玩家必須存在於 `players` 表。
  - 村莊必須存在於 `villages` 表。
  - 若為 `gathering`，目標節點必須存在且 `remaining_amount > 0`。
  - 若為 `attack`，目標威脅節點必須存在且 `hp > 0`。
- 資源預扣:
  - `gathering`、`exploring`、`building`、`attack` 都會先扣除糧食成本。
  - `building` 另外依建築類型扣除對應的雙資源成本。
  - 具體成本公式與建築成本對應以 `docs/modules/village.md` 與 `docs/modules/buildings.md` 為準。
- 啟動成功後:
  - 寫入 `players.status` 與 `players.target_id`。
  - 設定 `players.last_update_time = cycle_start`。
  - 設定 `players.completion_time = cycle_start + ACTION_CYCLE_MINUTES`。
- 若預扣失敗或目標無效:
  - 不變更玩家狀態。
  - 保留既有進度，等待下次互動或結算。

### 4. 公告同步與通知機制 (Announcement & Notifications)

- 即時通知事件:
  - 資源耗盡 (Stock 為 0)。
  - 建築升級 (L_post > L_pre)。
  - 建築降級 (L_post < L_pre)。
  - 玩家閒置 (由 Active 轉為 idle)。
- 靜態同步 (Dashboard):
  - 資源發現 (含威脅節點探索) 不再發送獨立公告訊息，僅更新資料並在下次 dashboard 同步時反映。

## Changelog
- 2026.04.07.00: Updated settlement flow. - See [2026.04.07.00.md](../changelogs/2026.04.07.00.md)
- 2026.04.13.00: Refactored to SSOT. Centralized formulas to modules and removed standalone discovery announcements. See [2026.04.13.00.md](../changelogs/2026.04.13.00.md)
- 2026.04.14.00: Planned stat-history logging so only completed cycles write per-stat deltas and each player retains only the newest 150 rows. - See [2026.04.14.00.md](../changelogs/2026.04.14.00.md)

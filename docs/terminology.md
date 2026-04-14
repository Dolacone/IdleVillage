# Terminology

本文件定義專案中使用的核心術語與概念, 確保社群提案與 AI 實作之間的一致性.

### 1. 玩家狀態與活動 (Player Activity)

- Active Players (活躍玩家): 
  - 定義: 尚未被標記為 `missing` 的註冊玩家. 判定基準為過去 7 天內有 Discord 發言, 或過去 7 天內執行過 `/idlevillage`.
  - 影響: 只有活躍玩家會持續產出進度並消耗資源. 活躍玩家的人數會增加建築的每小時 XP 損耗.
- Inactive Players (非活躍玩家 / 失蹤人口):
  - 定義: 7 天內未發言且 7 天內未執行 `/idlevillage` 的玩家.
  - 處理: 系統會自動停止其當前行動, 將狀態設為 `missing`. 非活躍玩家不消耗村莊糧食, 也不計入建築損耗係數.
- Idle State (閒置狀態):
  - 定義: 玩家目前沒有執行任何工作, 探索或移動指令的狀態.
- Auto-Restart (自動重啟) (v2026.04.09.01):
  - 定義: 當一個行動週期 (Action Cycle) 結束且村莊資源充足時, 系統自動為玩家續約下一個週期的機制.
- Village Command (村莊命令) (v2026.04.13.00):
  - 定義: 玩家支付 Token 設定的集體方針, 自動導向閒置玩家執行特定任務。
- Threat Node (威脅節點) (v2026.04.13.00):
  - 定義: 探索發現的敵對實體, 具備累積 HP 特性, 超過門檻會造成村莊損耗加倍。
- Tokens (代幣/標記) (v2026.04.13.00):
  - 定義: 執行行動獲得的獎勵資源, 用於啟動個人 Buff、村莊保護或變更村莊命令。

### 2. 計算模型 (Calculation Models)

- Until-Timestamp (延遲計算 / 預計結算點):
  - 定義: 不採用每秒或每小時輪詢更新, 而是透過目前狀態預算出未來的 [完成時間點]. 
  - 運作: 當玩家進行互動時, 系統比對 [現在時間] 與 [上次更新時間] 來補算這段期間的數值變化.
- Completion Timestamp (完成時間點):
  - 定義: 根據當前 Action Cycle 預計結束的時間點.
- 150 Cycles Sliding Window (150 週期滑動窗口) (v2026.04.08.00):
  - 定義: 素質計算邏輯. 抓取 `player_actions_log` 中最近 150 筆完整週期的素質紀錄來動態決定素質.
- Stat History Row (素質歷史紀錄) (v2026.04.14.00):
  - 定義: `player_actions_log` 的單筆資料. 代表一個完整 Action Cycle 對五項素質的固定增量, 不保存 action name 作為素質計算來源.

### 3. 資源與建築 (Resources and Buildings)

- Normalized Tables (正規化資料表) (v2026.04.09.01):
  - `village_resources`: 獨立儲存村莊各類資源 (糧食、木材、石材) 數值的資料表.
  - `buffs`: 獨立儲存村莊建築/增益 XP 的資料表.
- Scaled Integer (縮放整數):
  - 定義: 為了避免浮點數精確度飄移, 資料庫中使用整數儲存放大後的數值.
  - 範例: 1.25 倍品質存為 125. 資源數量與 XP 則直接以 1x 整數儲存.
- Building XP (建築經驗值):
  - 定義: 將等級與耐久度整合為單一數值. 超過等級門檻的部分即為該等級的耐久緩衝區.
- Resource Node (資源節點):
  - 定義: 荒野中具備儲量與品質的產出單位. (v2026.04.09.00 起採用單一類型全域節點模型, 探索成功時會補充既有 singleton 或建立缺少的類型)
- Base Outcome (基礎產出) (v2026.04.09.01):
  - 定義: 在沒有任何素質加成下, 每個標準行動週期 (Action Cycle) 的標準產出數量 (預設為 50).

### 4. 系統組件 (System Components)

- The Watcher (監視任務):
  - 定義: 背景執行的輕量級任務, 負責處理那些已達到 Completion Timestamp 但尚未被玩家主動觸發更新的結算作業.

## Changelog
- 2026.04.07.00: Updated to reflect 1-hour lease model and stats recalculation logic. - See [2026.04.07.00.md](changelogs/2026.04.07.00.md)
- 2026.04.08.00: Defined 150 Cycles Sliding Window and Action Cycle concepts. - See [2026.04.08.00.md](changelogs/2026.04.08.00.md)
- 2026.04.09.01: Introduced Normalized Tables and Base Outcome terminology. Removed Satiety. - See [2026.04.09.01.md](changelogs/2026.04.09.01.md)
- 2026.04.14.00: Defined stat-history rows as the new `player_actions_log` source for the 150-cycle stat window. - See [2026.04.14.00.md](changelogs/2026.04.14.00.md)

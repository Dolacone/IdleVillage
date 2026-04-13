# Interface: Player Commands

定義玩家與機器人之間的所有 Slash Commands 互動介面與回饋格式.

### 1. 指令列表 (Slash Commands)
- `/idlevillage`: 開啟個人行動中心 (Ephemeral).
- `/idlevillage-help`: [暫不實作] 顯示遊戲指南.
- `/idlevillage-announcement`: [管理員] 在當前頻道發布村莊公告訊息 (Public).
- `/idlevillage-initial`: [管理員] 初始化村莊.
- `/idlevillage-manage`: [管理員] 互動式管理村莊資源與節點.
- `/idlevillage-tokens`: 管理個人 Token 持有量、個人加成使用與村莊保護使用 (Ephemeral).
- `/idlevillage-village-command`: 設定村莊命令 (Ephemeral), 介面必須清楚顯示本次設定將消耗 10 個 Token.

### 2. 個人主介面 (/idlevillage)
這是一個包含 Embed 與多個互動組件的隱藏訊息 (Ephemeral).

#### 2.1 Embed 結構
- Title: `Idle Village - [村莊名稱]`
- Color: `Green`
- Description: 採用與公開公告相同的 [統一模板](../interfaces/announcement.md#2-訊息格式模板-template), 包含資源、建築與活躍村民統計.

- 👤 Player Status (位於 Embed 最下方, 僅在個人介面顯示)
  - Stats: `💪 STR {val} | 🏃 AGI {val} | 👁️ PER {val} | 🧠 KNO {val} | 🔋 END {val}`
  - Status: 顯示當前行動、最後互動時間與下次結算時間 (當地時區時標).
    - 範例: `Gathering Stone (Last activity: <t:{ts}:t>, Next check: <t:{ts}:R>)`
    - 戰鬥範例: `Attacking Boar (HP: 450/1000) (Next check: <t:{ts}:R>)`
    - 閒置範例: `Idle (Last activity: <t:{ts}:t>, Next check: <t:{ts}:R>)`

#### 2.2 互動組件 (Components)
- Dropdown: Action Category (Interact, Build, Explore, Return to Village)
- Dropdown: Sub-menu (動態顯示對應目標或建築)
  - Interact 目標格式: {Name} (可能是資源節點或怪物)
  - Interact 描述格式: 
    - 資源: Stock {amount} | Quality {quality}%
    - 怪物: HP {curr}/{max} | Quality {quality}%
  - Build 描述格式 (v2026.04.11.00): {Description} (materials: {TypeA} & {TypeB})
  - 玩家選取目標後, 第二層下拉選單需保留已選中的 target, 再顯示 Submit 按鈕.

- Button: Submit (Green, Start Action)
- Button: Refresh (Gray, 🔄 Refresh Status, 設有 5 秒冷卻)

### 3. Token 介面 (/idlevillage-tokens)
- 功能範圍:
  - 顯示各類 Token 持有量。
  - 使用 Token 啟動個人加成。
  - 使用 Token 啟動村莊保護。
- 個人加成說明:
  - 必須清楚說明對應類別行動在公式計算時獲得 `+100` 總素質。
  - 持續時間顯示為 `3 * ACTION_CYCLE_MINUTES`。
- 村莊保護說明:
  - 必須清楚說明保護效果為減少 50% 村莊建築 XP 損耗。
  - 持續時間顯示為 `1 * ACTION_CYCLE_MINUTES`。

### 4. 村莊命令介面 (/idlevillage-village-command)
- 功能範圍:
  - 顯示目前村莊命令。
  - 提供可選擇的村莊命令清單。
  - 在確認前清楚提示將消耗 10 個 Token。
- 失敗說明:
  - 若 Token 不足, 必須直接提示設定失敗且不變更村莊命令。

### 5. 管理員管理介面 (/idlevillage-manage)
這是為管理員設計的互動式選單 (Ephemeral), 用於更直觀地維護村莊狀態.

#### 5.1 資源調整 (Resource Management)
- Step 1: 下拉選單 (Action Selector)
  - 選項: `Manage Resources`, `Manage Nodes`.
- Step 2: 下拉選單 (Resource Type)
  - 僅在選擇 `Manage Resources` 後顯示.
  - 選項: `Food`, `Wood`, `Stone`, `Gold`.
- Step 3: 狀態顯示與按鈕
  - Embed 顯示當前選定資源的數量.
  - 快速調整按鈕: `+100`, `+1,000`, `-100`, `-1,000`.
  - Set Custom 按鈕: 點擊後彈出 Modal 視窗, 提供一個文字輸入欄位輸入絕對數值.

#### 5.2 節點管理 (Node Management)
- Step 1: 下拉選單 (Action Selector)
  - 選項: `Manage Nodes`.
- Step 2: 下拉選單 (Node List)
  - 列出村莊內所有活躍節點與怪物.
  - 節點格式: `#{id} {Type} (Stock: {stock}, Q: {quality}%)`.
  - 怪物格式: `#{id} [Monster] {Name} (HP: {hp}, Q: {quality}%)`.
- Step 3: 移除按鈕
  - Remove Target 按鈕: 紅色樣式, 點擊後直接從資料庫移除該目標並重新渲染介面.

### 6. 間隔控制規範 (Interval Control)
- Action Cycle Duration: 由環境變數 `ACTION_CYCLE_MINUTES` 定義.
- Refresh Button Cooldown: 5 秒.
- Announcement Throttling: 60 秒.
- Watcher Heartbeat: 開發環境 60 秒, 生產環境 300 秒.

## Changelog
- 2026.04.08.00: Initial specification for modernized /idlevillage interface and interval controls. - See [2026.04.08.00.md](../changelogs/2026.04.08.00.md)
- 2026.04.08.02: Added /idlevillage-admin command and fixed next check display for idle players. - See [2026.04.08.02.md](../changelogs/2026.04.08.02.md)
- 2026.04.08.03: Replaced /idlevillage-admin with interactive /idlevillage-manage UI. - See [2026.04.08.03.md](../changelogs/2026.04.08.03.md)
- 2026.04.09.01: Aligned /idlevillage resource/building wording with normalized village resources and the shared building progress renderer. - See [2026.04.09.01.md](../changelogs/2026.04.09.01.md)
- 2026.04.10.00: Unified UI template with public announcement. Added Gold resource, Hunting buff, and combat status. Updated admin UI for Gold/Monsters. - See [2026.04.10.00.md](../changelogs/2026.04.10.00.md)

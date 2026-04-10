# Interface: Player Commands

定義玩家與機器人之間的所有 Slash Commands 互動介面與回饋格式.

### 1. 指令列表 (Slash Commands)
- `/idlevillage`: 開啟個人行動中心 (Ephemeral).
- `/idlevillage-help`: [暫不實作] 顯示遊戲指南.
- `/idlevillage-announcement`: [管理員] 在當前頻道發布村莊公告訊息 (Public).
- `/idlevillage-initial`: [管理員] 初始化村莊.
- `/idlevillage-manage`: [管理員] 互動式管理村莊資源與節點.

### 2. 個人主介面 (/idlevillage)
這是一個包含 Embed 與多個互動組件的隱藏訊息 (Ephemeral).

#### 2.1 Embed 結構
- **Title:** `Idle Village - [村莊名稱]`
- **Color:** `Green`

- **🏘️ Village Resources**
  - 格式: `🍎 {food} | 🪵 {wood} | 🪨 {stone} (Cap: {max})`
  - 備註: 數值應包含千分位撇號 (e.g., 1,500).

- **🏗️ Village Buildings** (使用 Code Block 排版)
  - 廚房: `Lv.{lv} [XP: {curr_level_xp} / {next_level_required}]`
  - 倉庫: `Lv.{lv} [XP: {curr_level_xp} / {next_level_required}]`
  - 加工: `Lv.{lv} [XP: {curr_level_xp} / {next_level_required}]`
  - 備註: 格式需與 Village Announcement 對齊, 使用當前等級內的 XP Progress (已扣除前面等級所需總和), XP 數值需使用千分位格式 (例如 `1,000`).

- **👤 Player Status** (位於 Embed 最下方)
  - **Stats:** `💪 STR {val} | 🏃 AGI {val} | 👁️ PER {val} | 🧠 KNO {val} | 🔋 END {val}`
  - **Status:** 顯示當前行動、最後互動時間與下次結算時間 (當地時區時標).
    - 範例: `Gathering Stone (Last activity: <t:{ts}:t>, Next check: <t:{ts}:R>)`
    - 閒置範例: `Idle (Last activity: <t:{ts}:t>, Next check: <t:{ts}:R>)`

#### 2.2 互動組件 (Components)
- **Dropdown: Action Category** (Gather, Build, Explore, Return to Village)
- **Dropdown: Sub-menu** (動態顯示對應節點或建築)
  - Gather 節點格式: `{Type} Node`
  - Gather 描述格式: `Stock {amount} | Quality {quality}%`
  - 玩家選取目標後, 第二層下拉選單需保留已選中的 target, 再顯示 Submit 按鈕.
- **Button: Submit** (Green, Start Action)
- **Button: Refresh** (Gray, 🔄 Refresh Status, 設有 5 秒冷卻)

### 3. 管理員管理介面 (/idlevillage-manage)
這是為管理員設計的互動式選單 (Ephemeral), 用於更直觀地維護村莊狀態.

#### 3.1 資源調整 (Resource Management)
- **Step 1: 下拉選單 (Action Selector)**
  - 選項: `Manage Resources`, `Manage Nodes`.
- **Step 2: 下拉選單 (Resource Type)**
  - 僅在選擇 `Manage Resources` 後顯示.
  - 選項: `Food`, `Wood`, `Stone`.
- **Step 3: 狀態顯示與按鈕**
  - Embed 顯示當前選定資源的數量.
  - 快速調整按鈕: `+100`, `+1,000`, `-100`, `-1,000`.
  - **Set Custom 按鈕**: 點擊後彈出 Modal 視窗, 提供一個文字輸入欄位輸入絕對數值.

#### 3.2 節點管理 (Node Management)
- **Step 1: 下拉選單 (Action Selector)**
  - 選項: `Manage Nodes`.
- **Step 2: 下拉選單 (Node List)**
  - 列出村莊內所有活躍節點.
  - 格式: `#{id} {Type} (Stock: {stock}, Q: {quality}%)`.
- **Step 3: 移除按鈕**
  - **Remove Node 按鈕**: 紅色樣式, 點擊後直接從資料庫移除該節點並重新渲染介面.

### 4. 間隔控制規範 (Interval Control)
- **Action Cycle Duration**: 由環境變數 `ACTION_CYCLE_MINUTES` 定義.
- **Refresh Button Cooldown**: 5 秒.
- **Announcement Throttling**: 60 秒.
- **Watcher Heartbeat**: 開發環境 60 秒, 生產環境 300 秒.

## Changelog
- 2026.04.08.00: Initial specification for modernized /idlevillage interface and interval controls. - See [2026.04.08.00.md](../changelogs/2026.04.08.00.md)
- 2026.04.08.02: Added /idlevillage-admin command and fixed next check display for idle players. - See [2026.04.08.02.md](../changelogs/2026.04.08.02.md)
- 2026.04.08.03: Replaced /idlevillage-admin with interactive /idlevillage-manage UI. - See [2026.04.08.03.md](../changelogs/2026.04.08.03.md)
- 2026.04.09.01: Aligned /idlevillage resource/building wording with normalized village resources and the shared building progress renderer. - See [2026.04.09.01.md](../changelogs/2026.04.09.01.md)

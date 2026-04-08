# Interface: Player Commands

定義玩家與機器人之間的所有 Slash Commands 互動介面與回饋格式.

### 1. 指令列表 (Slash Commands)
- `/idlevillage`: 開啟個人行動中心 (Ephemeral).
- `/idlevillage-help`: [暫不實作] 顯示遊戲指南.
- `/idlevillage-announcement`: [管理員] 在當前頻道發布村莊公告訊息 (Public).
- `/idlevillage-initial`: [管理員] 初始化村莊.
- `/idlevillage-admin`: [管理員] 管理村莊資源與節點.

### 2. 個人主介面 (/idlevillage)
這是一個包含 Embed 與多個互動組件的隱藏訊息 (Ephemeral).

#### 2.1 Embed 結構
- **Title:** `Idle Village - [村莊名稱]`
- **Color:** `Green`

- **🏘️ Village Resources**
  - 格式: `🍎 {food} | 🪵 {wood} | 🪨 {stone} (Cap: {max})`
  - 備註: 數值應包含千分位撇號 (e.g., 1,500).

- **🏗️ Village Buildings** (使用 Code Block 排版)
  - 廚房: `Lv.{lv} [XP: {curr} / {next}]`
  - 倉庫: `Lv.{lv} [XP: {curr} / {next}]`
  - 加工: `Lv.{lv} [XP: {curr} / {next}]`
  - 備註: 建築名稱與 `Lv.` 之間僅保留單一空格, XP 數值需使用千分位格式 (例如 `1,000`).

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

### 3. 管理員指令 (/idlevillage-admin)
[僅限管理員] 用於手動調整村莊狀態.
- 目前透過參數組合執行:
  - `mode=resource set`, `target=food|wood|stone`, `amount=<數值>`: 設定資源數值.
  - `mode=node remove`, `target=<node_id>`: 移除指定的資源節點.

### 4. 間隔控制規範 (Interval Control)
- **Action Cycle Duration**: 由環境變數 `ACTION_CYCLE_MINUTES` 定義.
- **Refresh Button Cooldown**: 5 秒.
- **Announcement Throttling**: 60 秒.
- **Watcher Heartbeat**: 開發環境 60 秒, 生產環境 300 秒.

## Changelog
- 2026.04.08.00: Initial specification for modernized /idlevillage interface and interval controls. - See [2026.04.08.00.md](../changelogs/2026.04.08.00.md)
- 2026.04.08.02: Added /idlevillage-admin command and fixed next check display for idle players. - See [2026.04.08.02.md](../changelogs/2026.04.08.02.md)

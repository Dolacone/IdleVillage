# Interface: Player Commands

定義玩家與機器人之間的所有 Slash Commands 互動介面與回饋格式.

### 1. 指令列表 (Slash Commands)
- `/idlevillage`: 開啟個人行動中心 (Ephemeral).
- `/idlevillage-help`: [暫不實作] 顯示遊戲指南.
- `/idlevillage-announcement`: [管理員] 在當前頻道發布村莊公告訊息 (Public).
- `/idlevillage-initial`: [管理員] 初始化村莊.

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

- **👤 Player Status** (位於 Embed 最下方)
  - **Stats:** `💪 STR {val} | 🏃 AGI {val} | 👁️ PER {val} | 🧠 KNO {val} | 🔋 END {val}`
  - **Status:** 顯示當前行動、最後互動時間與下次結算時間 (當地時區時標).
    - 範例: `⛏️ Gathering Stone (Last activity: <t:{ts}:t>, Next check: <t:{ts}:R>)`
    - 閒置範例: `🏕️ Idle (Last activity: <t:{ts}:t>, Next check: <t:{ts}:R>)`

#### 2.2 互動組件 (Components)
- **Dropdown: Action Category** (Gather, Build, Explore, Return to Village)
- **Dropdown: Sub-menu** (動態顯示對應節點或建築)
- **Button: Submit** (Green, Start Action)
- **Button: Refresh** (Gray, 🔄 Refresh Status, 設有 5 秒冷卻)

### 3. 間隔控制規範 (Interval Control)
- **Action Cycle Duration**: 由環境變數 `ACTION_CYCLE_MINUTES` 定義.
- **Refresh Button Cooldown**: 5 秒.
- **Announcement Throttling**: 60 秒.
- **Watcher Heartbeat**: 開發環境 60 秒, 生產環境 300 秒.

## Changelog
- 2026.04.08.00: Initial specification for modernized /idlevillage interface and interval controls. - See [2026.04.08.00.md](../changelogs/2026.04.08.00.md)

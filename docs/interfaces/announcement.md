# Interface: Village Announcement

定義伺服器公開頻道中的村莊公告看板格式.

### 1. 顯示規則
- **訊息類型:** 混合格式訊息 (純文字資源區塊, 搭配建築與村民的 Code Block).
- **更新機制:** 當村莊中有玩家執行 `/idlevillage`、Watcher 完成結算, 或管理員執行 `/idlevillage-announcement` 時嘗試觸發更新.
- **節流控制 (Throttling)**: 每次公告更新後需冷卻 60 秒 (由資料庫 `last_announcement_updated` 紀錄).
- 排序邏輯: Active Villagers 依據彙整後的人數 (Count) 降序排列; 若人數相同, 按動作名稱 (Action Name) 升序排列.
- **活躍定義:** 僅列出目前非 `missing` 狀態的玩家.

### 2. 訊息格式模板 (Template)

(Last Update: <t:{unix_timestamp}:R>)

Village Resources (Cap: {max})
🍎 {food} | 🪵 {wood} | 🪨 {stone}

Village Buildings
```text
廚房: Lv.{lv} [XP: {curr_level_xp} / {next_level_required}]
倉庫: Lv.{lv} [XP: {curr_level_xp} / {next_level_required}]
加工: Lv.{lv} [XP: {curr_level_xp} / {next_level_required}]
```

Active Villagers
```text
{Action_Name}: {Count}
{Action_Name}: {Count}
...
```

### 3. 區塊樣式規範
- **Header**:
  - (Last Update: <t:{unix_timestamp}:R>) 位於訊息最上方.
  - 使用 Discord 的動態時間格式 (Relative Time), 自動適應使用者時區.
- **Resources**:
  - 不使用 Code Block.
  - 使用純文字標題與表情符號, 不使用 Markdown emphasis.
  - XP 以外的數值需包含千分位撇號.
- **Village Buildings**:
  - 建築內容必須包裹在單一 Code Block (```text) 中.
  - 標題 Village Buildings 保持純文字, 不使用 Markdown emphasis.
  - XP 數值需包含千分位撇號.
  - XP Display: 顯示當前等級累積的經驗值 (已扣除前一等級所需總和) 與升至下一級所需的經驗值差距.
- **Active Villagers**:
  - 必須包裹在單一 Code Block (```text) 中.
  - 標題 Active Villagers 保持純文字, 不使用 Markdown emphasis.
  - 彙整邏輯: 不再列出個別玩家名稱, 改為按動作類型分組並顯示參與人數.
  - 動作名稱映射:
    - idle -> Idle
    - exploring -> Exploring
    - gathering -> Gathering {Resource_Type}
    - building -> Building {Building_Name}
  - 排序規則:
    1. 按人數 (Count) 降序排列.
    2. 若人數相同, 按動作名稱 (Action Name) 升序排列 (A-Z).

### 4. 通知機制 (Notifications)
除公告看板外, 系統會在以下事件發生時於公告頻道發送即時訊息:
- 資源耗盡通知: 當資源節點存量歸零 (Out of Stock) 時, 發送通知提醒村莊已無該項產出.
- 建築升級通知: 當村莊建築等級提升時, 發送慶祝訊息.
- 建築降級通知: 當建築因 XP 損耗而降級時, 發送提醒訊息.
- 閒置標註通知: 當玩家完成目前行動且未排定下一個行動而進入 Idle 狀態時, 發送訊息標註 (@tag) 該玩家.
- 資源發現靜默規則: `exploring` 成功時只更新資料與公告看板內容, 不另外發送 discovery 訊息.


### 5. 錯誤處理
- 若公告訊息 ID 遺失或被刪除, 系統應在下次更新嘗試時檢測到 404 錯誤, 並清除資料庫紀錄.

## Changelog
- 2026.04.08.00: Initial specification for Village Announcement dashboard. - See [2026.04.08.00.md](../changelogs/2026.04.08.00.md)
- 2026.04.08.02: Simplified active villagers UI (removed stats) and added automated notifications for node expiry and player idle states. - See [2026.04.08.02.md](../changelogs/2026.04.08.02.md)
- 2026.04.08.03: Aligned Resource and Building sections with /idlevillage style. Clarified code block usage for villagers list only. - See [2026.04.08.03.md](../changelogs/2026.04.08.03.md)
- 2026.04.09.00: Moved Last Update to header, simplified building XP display, and aggregated active villagers count. - See [2026.04.09.00.md](../changelogs/2026.04.09.00.md)
- 2026.04.09.01: Added building level-down notifications and clarified that exploration discoveries stay silent outside the dashboard refresh. - See [2026.04.09.01.md](../changelogs/2026.04.09.01.md)

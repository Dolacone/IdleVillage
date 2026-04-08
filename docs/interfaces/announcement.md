# Interface: Village Announcement

定義伺服器公開頻道中的村莊公告看板格式.

### 1. 顯示規則
- **訊息類型:** 純文字訊息 (使用 Code Block ` ``` ` 包裹以實現等寬對齊).
- **更新機制:** 當村莊中有玩家執行 `/idlevillage`、Watcher 完成結算, 或管理員執行 `/idlevillage-announcement` 時嘗試觸發更新.
- **節流控制 (Throttling)**: 每次公告更新後需冷卻 60 秒 (由資料庫 `last_announcement_updated` 紀錄).
- **排序邏輯:** 村民列表依據「最後行動開始時間 (start_time)」降序排列 (Latest at top).
- **活躍定義:** 僅列出目前非 `missing` 狀態的玩家.
- **探索通知:** 若探索發現新節點, 額外發送一則純文字 discovery 訊息到同一個公告頻道.

### 2. 訊息格式模板 (Template)
```text
=== [ VILLAGE NAME ] STATUS REPORT ===
Resources: 食物 {food} | 木頭 {wood} | 石頭 {stone} (Cap: {max})
Buildings: 廚房 Lv{lv} | 倉庫 Lv{lv} | 加工 Lv{lv}

--- ACTIVE VILLAGERS (Sorted by latest action) ---
{Player_Name} | {Status_Text}
{Player_Name} | {Status_Text}
...
(Last Update: {YYYY-MM-DD HH:MM:SS} UTC)
```

### 3. 欄位規範與截斷
- **Player Name**: 截斷至 12 字元.
- **Status Text**: 顯示簡化後的當前動作與剩餘時間 (e.g., `[Gathering Stone] (12m)`, `[Idle] (45m)`).
- **Village Name**: 應顯示 Discord 伺服器名稱, 不應顯示 Guild ID.
- **字元限制**: 若村民過多導致訊息超過 2000 字, 僅顯示前 20 位最活躍的村民.

### 4. 通知機制 (Notifications)
除公告看板外, 系統會在以下事件發生時於公告頻道發送即時訊息:
- **探索通知**: 若探索發現新節點, 發送一則純文字 discovery 訊息.
- **資源耗盡通知**: 當資源節點因庫存耗盡 (Out of Stock) 或到期 (Timeout) 而消失時, 發送通知並說明原因.
- **閒置標註通知**: 當玩家完成目前行動且未排定下一個行動而進入 `Idle` 狀態時, 發送訊息標註 (@tag) 該玩家.

### 5. 錯誤處理
- 若公告訊息 ID 遺失或被刪除, 系統應在下次更新嘗試時檢測到 404 錯誤, 並清除資料庫紀錄.

## Changelog
- 2026.04.08.00: Initial specification for Village Announcement dashboard. - See [2026.04.08.00.md](../changelogs/2026.04.08.00.md)
- 2026.04.08.02: Simplified active villagers UI (removed stats) and added automated notifications for node expiry and player idle states. - See [2026.04.08.02.md](../changelogs/2026.04.08.02.md)

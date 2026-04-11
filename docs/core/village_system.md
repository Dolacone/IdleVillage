# Core: Village System

定義村莊與 Discord 伺服器的綁定關係.

### 1. 伺服器初始化 (Guild Initialization)
- 觸發事件: 透過指令 `/idlevillage-initial` 手動初始化 (僅限特定管理員使用).
- 回應模式: 初始化結果應僅對指令呼叫者可見 (ephemeral), 避免在公共頻道產生訊息洗版.
- 初始邏輯 (v2026.04.10.00):
  - 建立對應的 villages 紀錄.
  - 初始資源: 系統自動在 village_resources 寫入糧食、木材、石材各 1,000 單位. 黃金為 0.
  - 初始建築: 在 buffs 表建立 廚房、倉庫、加工、狩獵 四項基礎紀錄 (XP 為 0).

### 2. 資料庫結構 (Table: villages)
| 欄位名 | 型別 | 說明 |
| :--- | :--- | :--- |
| id | INTEGER (PK) | 綁定的 Discord Guild ID |
| last_tick_time | TIMESTAMP | 上次執行建築損耗結算的時間 |
| announcement_channel_id | TEXT | 公告面板所在的頻道 ID |
| announcement_message_id | TEXT | 公告面板訊息 ID |
| last_announcement_updated | TIMESTAMP | 上次公開儀表板刷新的時間 |

*註: 資源存儲已遷移至 village_resources 表, 建築增益已遷移至 buffs 表.*

## Changelog
- 2026.04.07.00: Updated to reflect 1-hour lease model and stats recalculation logic. See [2026.04.07.00.md](../../changelogs/2026.04.07.00.md)
- 2026.04.08.00: Added announcement channel/message tracking fields for the public village dashboard. See [2026.04.08.00.md](../../changelogs/2026.04.08.00.md)
- 2026.04.09.01: Normalized Resources and Buildings (as "buffs") into separate tables. Performed numerical rebalance. See [2026.04.09.01.md](../../changelogs/2026.04.09.01.md)
- 2026.04.10.00: Updated initialization resources and added Hunting buff. See [2026.04.10.00.md](../../changelogs/2026.04.10.00.md)

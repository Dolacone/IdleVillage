# Setup Guide (Discord Bot and Environment)

本文件說明如何從零開始設定 Discord Bot 並配置開發環境.

### 1. Discord 開發者入口網站設定

1. 建立應用程式 (Create Application):
   - 前往 Discord Developer Portal.
   - 點擊 New Application, 輸入遊戲名稱.

2. 取得 Bot Token:
   - 在左側選單選擇 Bot.
   - 點擊 Reset Token 並複製產生的 Token.

3. 權限與意圖 (Intents):
   - 重要: 為了監測玩家活躍度, 必須開啟 Message Content Intent.
   - 在 Portal 的 Bot 頁面, 將 Privileged Gateway Intents 下的 Message Content Intent 切換為 ON.

4. 邀請 Bot 到伺服器:
   - 在選單選擇 OAuth2 -> URL Generator.
   - 重要: 僅勾選 bot 與 applications.commands 這兩個 Scope. (不需要 Redirect URI)
   - 在 Bot Permissions 中勾選 Send Messages, Read Messages/View Channels, Read Message History.
   - 複製生成的網址並在瀏覽器中打開.

### 2. 環境變數配置 (.env)

在專案根目錄建立 .env 檔案, 並參考 `.env.example`:

- `DISCORD_TOKEN`: 機器人存取憑證.
- `DATABASE_PATH`: 資料庫儲存路徑 (預設 `data/village.db`).
- `ADMIN_IDS`: 允許執行管理指令 (Initial/Announcement) 的 Discord ID 清單 (以逗號分隔).
- `ACTION_CYCLE_MINUTES`: 遊戲倍速/行動週期長度 (分鐘, 預設 `60`).

### 3. 本地執行

- 安裝依賴: `pip install -r src/requirements.txt`
- 啟動 Bot: `python src/main.py`

## Changelog
- 2026.04.06.00: Updated setup instructions for the flat `src/` runtime layout and `.env.example` flow. - See [2026.04.06.00.md](changelogs/2026.04.06.00.md)
- 2026.04.07.00: Updated to reflect 1-hour lease model and stats recalculation logic. - See [2026.04.07.00.md](changelogs/2026.04.07.00.md)
- 2026.04.08.00: Added ADMIN_IDS and ACTION_CYCLE_MINUTES configuration details. - See [2026.04.08.00.md](changelogs/2026.04.08.00.md)
- 2026.04.09.01: Performed numerical rebalance and normalized core data structures. - See [2026.04.09.01.md](changelogs/2026.04.09.01.md)

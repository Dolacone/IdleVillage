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

在專案根目錄建立 .env 檔案:

- DISCORD_TOKEN=your_bot_token_here
- DATABASE_PATH=data/village.db
- DEBUG=1

### 3. 本地執行

- 安裝依賴: `pip install -r src/requirements.txt`
- 啟動 Bot: `python src/main.py`

## Changelog
- 2026.04.06.00: Updated setup instructions for the flat `src/` runtime layout and `.env.example` flow. See [2026.04.06.00.md](./changelogs/2026.04.06.00.md)

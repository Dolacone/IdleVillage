# Shared Interface: /idlevillage

這是遊戲的核心互動介面, 旨在讓玩家在單一指令中掌握所有資訊並下達決策.

### 1. 介面結構 (Embed Content)
當玩家執行 /idlevillage 時, 系統會回傳一個包含以下資訊的 Embed:

- 個人狀態 (Player Stats):
  - 飽食度, 當前負重/最大負重.
  - 當前素質 (Sliding Window 計算結果).
- 村莊狀態 (Village Status):
  - 共用糧食, 木材, 石材存量.
  - 輔助建築等級 (Food Efficiency, Storage, Yield).
- 當前進度 (Current Progress):
  - 若正在工作中: 顯示預計完成時間 (ETA) 與產出進度.
  - 若在村莊中: 顯示可用的資源節點清單.

### 2. 互動組件 (Components)
Embed 下方包含以下互動元件:

- 行動類別選單 (Dropdown: Action Category):
  - 選項: 採集 (Gather), 建設 (Build), 探索 (Explore), 取消當前行動.
- 動態子選單 (Dynamic Sub-menu):
  - 根據第一層選單的選擇而變動:
    - Gather: 顯示所有可用節點 (包含距離資訊).
    - Build: 顯示可建設的建築.
    - Explore: 顯示探索時間 (1, 2, 4, 8 小時) 與目標類型.
- 提交按鈕 (Submit Button):
  - 確認選單內容後, 將行動指令發送至伺服器.

### 3. 位置感知機制 (Location Awareness)
- 在村莊時: 玩家可以看到完整的資源點列表與建築選項.
- 在荒野時: 玩家僅能看到當前工作的進度與 [取消並回村] 的選項.
- 自動重新整理: 玩家與選單互動時, 系統會重新計算 Until-Timestamp 數值, 確保顯示的飽食度與負重是最新的.

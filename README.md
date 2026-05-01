---
title: Idle Colony
doc_type: overview
last_reviewed: 2026-05-01
source_paths:
---

# Idle Colony

這是一個以 Discord 為平台的社群驅動 (Community-Driven) 集體協作掛機遊戲. 

## 1. 核心理念: 社群提案, AI 實作

本遊戲的開發流程完全由社群與 AI 協作完成:
- 玩家社群 (Players): 負責設計遊戲機制, 提交新的模組提案 (Module Proposals). 提案者需具備遊戲性設計的知識, 但不需要具備任何編程能力.
- AI 代理人 (AI Agents): 負責讀取社群提案, 並將其轉化為實際的程式碼, 資料庫結構 (Schemas) 以及遊戲介面.

## 2. 核心進入點
- 主要指令: `/idlevillage`
- 功能: 顯示個人素質, 村莊狀態, 並提供整合型選單進行所有遊戲決策.

## 3. 專案結構 (Project Structure)
- `docs/core/`: 核心系統邏輯 (引擎, 玩家系統, 村莊系統).
- `docs/modules/`: 遊戲玩法的模組化定義 (建築, 資源, 探索).
- `src/`: Discord Bot 服務主體.
- `src/core/`: 實作結算與計算引擎.
- `src/cogs/`: Discord 互動指令與介面.
- `src/database/`: 基於 Markdown 定義的資料庫動態管理.
- `tests/`: 自動化測試根目錄 (不打包進 Docker).

## 4. 快速啟動 (Quick Start)
1. 複製 `.env.example` 並填寫 `DISCORD_TOKEN`.
2. 安裝依賴: `pip install -r src/requirements.txt`.
3. 執行: `python src/main.py`.

## 5. 遊戲發展流程
1. 提案: 玩家在社群中討論並提出新的模組想法 (例如: 釣魚, 鍛造).
2. 設計: 玩家撰寫邏輯文件, 定義行動流程與預期平衡參數.
3. 實作: AI 根據文件更新 Bot 程式碼與資料庫設計.
4. 測試: 進行 Playtest 並根據反饋進行數值平衡調整.

## 4. 模組開發與貢獻規範 (Module Development)

### 4.1 玩家提案規範 (Player Proposals)
玩家在提交新功能 (模組) 時, 應包含以下內容:
- 功能描述: 該模組在遊戲中解決什麼問題或提供什麼樂趣.
- 行動邏輯: 玩家如何操作 (例如: /action 選單中的新選項).
- 數值關聯: 該行動受哪些素質影響, 並會產出哪些資源或對應哪些素質紀錄.
- 平衡參數建議: 提供初始的速率, 消耗量等數值.

### 4.2 AI 的角色與職責
- 邏輯轉化: AI 會解析玩家的自然語言提案, 並寫入對應的程式模組.
- 架構維護 (Schemas): 資料庫的設計 (Schemas) 由 AI 主導. 為了確保系統穩定性, AI 會將玩家的需求轉換為技術規範文件, 並確保新模組不會損壞現有的資料關聯.
- 自動化測試: AI 負責撰寫驗證邏輯, 確保新行動符合 Until-Timestamp 延遲計算模型.

### 4.3 平衡性調整 (Balance and Tuning)
- 初始發布: 所有新模組在初次實作後皆視為測試版本.
- 數據回饋: AI 會協助分析測試期間的玩家數據.
- 數值調整: 模組內的平衡參數隨時可以進行微調, 且此類調整不應影響模組的核心結構.

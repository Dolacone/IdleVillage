---
title: "素材獻祭換取永久成功率加成"
status: Draft
created: 2026-05-31
doc_type: change
last_reviewed: 2026-05-31
source_paths: []
scope: "新增按鈕讓玩家直接消耗素材換取 risky_failed_levels，效果等同於鐵齒失敗的永久成功率加成，不消耗 AP，不發送公告。"
---

## Problem Statement

`risky_failed_levels` 永久成功率加成目前只能透過鐵齒強化失敗取得，代價是工具等級歸零。玩家若不願冒工具歸零風險，完全無法主動累積此加成。需要一條無風險路徑讓玩家以素材換取永久成功率。

## Recommended Direction

在工具強化子選單新增「🩸 獻祭素材」按鈕。玩家選定素材類型後，輸入投入數量（1 ~ 持有上限），確認後：

- 消耗所選類型素材 N 個
- `risky_failed_levels += N`（效果等同於在任意等級鐵齒失敗 N 次各 1 級的加成總和）
- 不消耗 AP
- 不發送 Public 通知，僅更新個人介面

選方向 A（1 材料 = +1 risky_failed_levels）而非等效等級模擬或固定批次，因為直接換算最透明，玩家能完全預測「花多少得多少」。材料稀缺性（僅靠週期結算掉落）天然限制濫用。

選「自由選擇任一素材類型」而非四種等量消耗，因為玩家可能四種素材庫存不均衡，不應因某種素材不足而卡住。

## Clarifications

Q: 素材類型選擇？
A: 自由選擇任一類型。

Q: 投入數量如何輸入？
A: 透過 Discord Modal 彈出輸入框，玩家輸入 1~持有數量的整數。

## MVP Scope / Not Doing

做：
- 工具強化子選單新增「🩸 獻祭素材」按鈕
- 點擊後彈出 Modal（選素材類型 + 輸入數量）
- 驗證素材足夠後扣除素材、`risky_failed_levels += N`
- 介面回饋：更新強化子選單 embed（含新 risky_failed_levels 數值）
- 無 AP 消耗、無 Public 通知

不做：
- 多種素材同時投入（單次選一種）
- 獻祭歷史記錄
- 獻祭量上限或每日限制

## Key Assumptions

- Discord Modal 最多 5 個 TextInput，本需求只需 1 個（數量），類型透過另一個 TextInput 或改為先選下拉再點按鈕的方式處理
- 實際 UI 流程待 plan 階段確認現有 Modal 使用模式後決定

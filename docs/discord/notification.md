---
title: "Module: notification"
doc_type: module
last_reviewed: 2026-05-06
source_paths:
  - src/core/notification.py
---

# Module: notification

負責遊戲事件發生時，Bot 主動在指定頻道發送 Public 訊息。

## 通知頻道

通知頻道存於 DB 的 `village_state.announcement_channel_id`。
首次初始化可由環境變數預設值寫入 DB。

## 村莊 Dashboard 訊息

Bot 維護一則**固定的 Public 訊息**作為村莊狀態看板（Dashboard）。

- `dashboard_message_id` 與 `dashboard_channel_id` 存於村莊全局狀態（見 stage-manager）。
- **每次 Watcher 完成一輪結算後**，edit 該訊息更新村莊狀態（見 ui-renderer 村莊狀態區 embed）。
- **初始化**：`/idlevillage-announcement` 執行時，在該指令執行的頻道發送新 Dashboard 訊息，將新的 `message_id` 與 `channel_id` 寫入村莊全局狀態。

## 事件清單

| 事件 | 觸發時機 | 訊息內容 | 公開/私人 |
| :--- | :--- | :--- | :--- |
| 關卡通關 | stage-manager 判定進度達標 | 通過第 X 關 + 下一目標 + 目標需求 | Public |
| 關卡逾時 | Watcher 結算時首次偵測到 `now - stage_started_at > STAGE_OVERTIME_SECONDS` | ⚠️ 逾時警告，說明後續進度減半計算 | Public |
| 升級關通關 | 每輪第 5 關通關時 | 附加建築等級上限提升資訊，但不取代一般關卡通關通知 | Public |
| 建築升級 | building-manager 觸發升級 | `{建築名稱}` 從 Lv{x} 變成 Lv{y}，下一等級需求 {z} | Public |
| 工具強化成功 | gear-manager 回傳成功 | `{user_display_name} 的 {gear_name} 升級成功 :tada: Lv{current_level} -> Lv{target_level}（總失敗次數：{failure_count}）` | Public |
| 工具強化失敗 | gear-manager 回傳失敗 | `{user_display_name} 的 {gear_name} 升級失敗 :boom: Lv{current_level} -> Lv{target_level}（總失敗次數：{failure_count}）` | Public |

## 通知去重

- 不使用 persistent notification log。
- 關卡通關通知只在關卡切換處理瞬間發送。所有關卡都通知，不只升級關。
- 關卡逾時通知只在首次檢查發現逾時且 `overtime_notified = false` 時發送，發送後設為 true。
- 關卡切換時 `overtime_notified` reset to false。
- 建築升級通知只在升級處理瞬間發送。
- 建築一次升多級時，每個等級分開發送。
- 工具強化成功/失敗為 Public 訊息，只在強化處理瞬間發送，不需要持久去重。

## 同一 settlement 內的通知順序

1. 關卡通關通知
2. 升級關建築等級上限通知
3. 建築升級通知（若多級，逐級發送）
4. Dashboard 更新

## 訊息範本

### 關卡通關
```
通過第 {cleared_stage_number} 關
下一目標：{next_stage_name}
目標需求：{next_target}
```

### 逾時警告
```
第 {n} 關已超過 {STAGE_OVERTIME_SECONDS} 秒
後續貢獻計入關卡進度時將乘上 {STAGE_OVERTIME_PROGRESS_MULTIPLIER}
目前進度：{progress} / {target}（{pct}%）
```

### 升級關通關
```
升級關通關，第 {round} 輪完成
建築等級上限從 Lv{old_cap} 變成 Lv{new_cap}
下一目標：{next_stage_name}
目標需求：{next_target}
```

### 建築升級
```
{建築名稱} 從 Lv{old_level} 變成 Lv{new_level}
下一等級需求：{next_requirement}
```

### 工具強化成功
```
{user_display_name} 的 {gear_name} 升級成功 :tada: Lv{current_level} -> Lv{target_level}（總失敗次數：{failure_count}）
```

### 工具強化失敗
```
{user_display_name} 的 {gear_name} 升級失敗 :boom: Lv{current_level} -> Lv{target_level}（總失敗次數：{failure_count}）
```

## 工具強化通知欄位

- `current_level`: 本次強化嘗試前的工具等級。
- `target_level`: 本次嘗試想升到的等級，等於 `current_level + 1`。
- `failure_count`: 總失敗次數。成功時顯示成功前累積失敗次數；失敗時顯示含本次失敗後的累積失敗次數。

## Changelog

- 2026.05.06.01: 工具強化成功/失敗 Public notification 改為顯示 current level、target level、成功/失敗狀態與總失敗次數；official user-facing gear naming changed to tools: 採集工具, 建設工具, 狩獵工具, 研究工具.

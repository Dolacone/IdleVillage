---
title: "Module: notification"
doc_type: module
last_reviewed: 2026-07-14
source_paths:
  - src/core/notification.py
  - src/cogs/actions.py
  - src/cogs/trial_cog.py
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
| 詞條抽取 | `extract_affix` handler 成功後 | `{user_display_name} 的 {gear_name} 抽到詞條：{affix_label}（{sign}{value}%）`，sign 為 `-`（reduce 類型）或 `+`（其他） | Public |
| 詞條清除 | `clear_affix` handler 成功後 | `{user_display_name} 的 {gear_name} 清除詞條：{affix_label}（{sign}{value}%）`，sign 為 `-`（reduce 類型）或 `+`（其他） | Public |
| 試煉開始 | `/idlevillage-trial` 成功開啟試煉 | 發起者 + 目標值 + 資源類型 + 期限 + 獎勵池大小 | Public |
| 試煉達成 | trial-manager 判定進度達標 | 目標值 + 資源類型 + 各參與者貢獻與獲得數量列表（依貢獻降冪） | Public |
| 試煉失敗（逾時） | trial-manager 判定 24 小時內未達標 | 目標值 + 資源類型 + 逾時當下進度，說明資源不退還 | Public |

## 通知去重

- 不使用 persistent notification log。
- 關卡通關通知只在關卡切換處理瞬間發送。所有關卡都通知，不只升級關。
- 關卡逾時通知只在首次檢查發現逾時且 `overtime_notified = false` 時發送，發送後設為 true。
- 關卡切換時 `overtime_notified` reset to false。
- 建築升級通知只在升級處理瞬間發送。
- 建築一次升多級時，每個等級分開發送。
- 工具強化成功/失敗為 Public 訊息，只在強化處理瞬間發送，不需要持久去重。
- 詞條抽取/清除通知只在操作瞬間發送，不需持久去重。
- 試煉開始通知只在 `/idlevillage-trial` 成功開啟當下發送一次。
- 試煉達成/失敗通知只在 trial-manager 判定當下（settlement 內或 Watcher tick）發送一次，不需持久去重。

## 同一 settlement 內的通知順序

1. 關卡通關通知
2. 升級關建築等級上限通知
3. 建築升級通知（若多級，逐級發送）
4. 試煉達成/失敗通知
5. Dashboard 更新

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

### 詞條抽取
```
{user_display_name} 的 {gear_name} 抽到詞條：{affix_label}（{sign}{value}%）
```
sign 為 `-`（reduce 類型，如 `upgrade_cost_reduce`）或 `+`（其他類型）。

### 詞條清除
```
{user_display_name} 的 {gear_name} 清除詞條：{affix_label}（{sign}{value}%）
```
sign 為 `-`（reduce 類型，如 `upgrade_cost_reduce`）或 `+`（其他類型）。

### 試煉開始
```
<@{user_id}> 發起了村莊試煉！
目標：{target} {resource_emoji}{resource_label}
期限：<t:{deadline_unix}:R> 前需全服玩家共同達成
達成後將依貢獻度瓜分共 {reward_pool} 個 🌟萬能素材
```
`{reward_pool}` = `floor(target / TRIAL_REWARD_DIVISOR)`，僅供公告顯示；實際發放總量以達成當下逐人無條件進位後加總為準（見達成訊息）。

### 試煉達成
```
🎉 村莊試煉達成！目標 {target} {resource_emoji}{resource_label} 已完成
共 {participant_count} 位玩家依貢獻度瓜分了 {total_awarded} 個 🌟萬能素材：
<@{user_id}>：貢獻 {contribution}，獲得 {reward} 個
...（依貢獻降冪排序）
```
參與者列表超過 1900 字元時截斷，並附上「（清單過長，部分內容已省略）」提示，比照 `/idlevillage-ranking` 的截斷規則。

### 試煉失敗（逾時）
```
⌛ 村莊試煉逾時失敗！目標 {target} {resource_emoji}{resource_label} 未達成（進度：{progress}/{target}）
資源不予退還。{cooldown_hours} 小時內無法開啟新試煉。
```

## 工具強化通知欄位

- `current_level`: 本次強化嘗試前的工具等級。
- `target_level`: 成功時為實際到達等級（`new_level` = `current_level + level_gain`）；失敗時為嘗試目標（`current_level + 1`）。
- `failure_count`: 總失敗次數。成功時顯示成功前累積失敗次數；失敗時顯示含本次失敗後的累積失敗次數。

## Changelog

- 2026-07-14: 新增村莊試煉事件（試煉開始、達成、失敗）與訊息範本；「同一 settlement 內的通知順序」新增第 4 項試煉達成/失敗通知並重新編號。試煉相關訊息一律使用 `<@{user_id}>` mention 呈現使用者，不需額外解析 display name。
- 2026-07-14: 移除奉獻達標事件、訊息範本，並自「同一 settlement 內的通知順序」重新編號。
- 2026-05-31: 工具強化成功通知的 `target_level` 改為使用實際到達等級（`new_level`），以正確反映鐵齒 +2/+3 多段升級結果。失敗通知不變，仍顯示 `current_level + 1`。
- 2026-05-22: 新增詞條抽取/清除公告事件（`affix_extracted`、`affix_cleared`）。
- 2026.05.06.01: 工具強化成功/失敗 Public notification 改為顯示 current level、target level、成功/失敗狀態與總失敗次數；official user-facing gear naming changed to tools: 採集工具, 建設工具, 狩獵工具, 研究工具.

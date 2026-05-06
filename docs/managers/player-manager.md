---
title: "Module: player-manager"
doc_type: module
last_reviewed: 2026-05-06
source_paths:
  - src/managers/player_manager.py
---

# Module: player-manager

管理每位玩家的個人狀態，包含行動設定、AP、素材庫存與工具等級。

## 玩家識別

- 主鍵為 Discord `user_id`。
- v2 preview 僅支援環境變數指定的單一 Guild。

## 玩家資料結構

| 欄位 | 型別 | 初始值 | 說明 |
| :--- | :--- | :--- | :--- |
| `action` | enum / null | null | 當前自動行動。DB 儲存英文 enum；UI 顯示繁中 |
| `action_target` | enum / null | null | 建設目標建築。僅 `action = building` 時使用 |
| `completion_time` | timestamp | null | 當前週期結束時間（設定行動時寫入） |
| `last_update_time` | timestamp | null | 上次結算時間（換行動比例產出計算用） |
| `ap_full_time` | timestamp | created_at + AP_CAP × AP_RECOVERY_MINUTES | AP 回滿時間，用於倒推當前 AP |
| `materials_gathering` | int | 0 | 採集素材（採集工具用） |
| `materials_building` | int | 0 | 建設素材（建設用） |
| `materials_combat` | int | 0 | 戰鬥素材（狩獵工具用） |
| `materials_research` | int | 0 | 研究素材（研究用） |
| `gear_gathering` | int | 0 | 採集工具等級 |
| `gear_building` | int | 0 | 建設工具等級 |
| `gear_combat` | int | 0 | 狩獵工具等級 |
| `gear_research` | int | 0 | 研究工具等級 |
| `pity_gathering` | int | 0 | 採集工具保底計數 |
| `pity_building` | int | 0 | 建設工具保底計數 |
| `pity_combat` | int | 0 | 狩獵工具保底計數 |
| `pity_research` | int | 0 | 研究工具保底計數 |

## AP 系統

- **回復**：由 `ap_full_time` 倒推，不儲存當前 AP 數值。
- **上限**：AP_CAP。
- **新玩家**：0 AP，`ap_full_time = created_at + AP_CAP × AP_RECOVERY_MINUTES`。
- **當前 AP**：
  ```
  若 now >= ap_full_time → AP = AP_CAP
  否則 AP = max(0, AP_CAP - ceil((ap_full_time - now) / AP_RECOVERY_MINUTES))
  ```
- **消耗 AP**：
  ```
  ap_full_time = max(now, ap_full_time) + amount × AP_RECOVERY_MINUTES
  ```
- **用途**：
  - 工具強化：消耗 1 AP（呼叫 gear-manager）
  - 爆發執行：消耗 1 AP，即時結算 3 個週期（呼叫 cycle-engine）

## 素材系統

- 每次完整 cycle settlement 有 MATERIAL_DROP_RATE 機率獲得 1 個對應類別素材。
- 素材欄位固定為 `materials_gathering`, `materials_building`, `materials_combat`, `materials_research`。
- Burst 視為 3 次完整 cycle settlement，每次各自判定素材掉落。
- Partial cycle 不掉落素材。
- 素材個人持有，不進入村莊資源池。
- 唯一用途：工具強化（呼叫 gear-manager）。

## 操作介面（供其他模組呼叫）

- `setAction(playerId, action, target?)` — 設定行動與目標
- `getAction(playerId)` — 取得當前行動設定
- `getAP(playerId)` — 由 `ap_full_time` 計算並回傳當前 AP
- `spendAP(playerId, amount)` — 扣除 AP 並更新 `ap_full_time`
- `addMaterial(playerId, type, amount)` — 增加素材
- `spendMaterial(playerId, type, amount)` — 扣除素材（不足則拒絕）
- `getGearLevel(playerId, type)` — 取得裝備等級
- `setGearLevel(playerId, type, level)` — 設定裝備等級
- `getPity(playerId, type)` — 取得保底計數
- `setPity(playerId, type, count)` — 設定保底計數

## Changelog

- 2026.05.06.01: Official user-facing gear naming changed to tools:
  採集工具, 建設工具, 狩獵工具, 研究工具.

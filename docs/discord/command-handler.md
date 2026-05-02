---
title: "Module: command-handler"
doc_type: module
last_reviewed: 2026-05-02
source_paths:
  - src/cogs/actions.py
  - src/cogs/general.py
---

# Module: command-handler

定義所有 Discord Slash Commands 與互動元件（Button/Dropdown）的路由與處理。

## Slash Commands

| 指令 | 對象 | 行為 |
| :--- | :--- | :--- |
| `/idlevillage` | 所有玩家 | 先補算到期完整週期，再渲染個人主介面（Ephemeral），呼叫 ui-renderer |
| `/idlevillage-announcement` | 管理員 | 將當前頻道寫入 `announcement_channel_id`，並發布或刷新村莊公告（Public） |
| `/idlevillage-manage` | 管理員 | 檢查 Dashboard 訊息是否存在（不存在則在當前頻道發送新的），再開啟資源管理介面（Ephemeral） |

所有指令必須先檢查 interaction guild 是否等於環境變數 `DISCORD_GUILD_ID`。不符合時拒絕執行。

## 互動元件路由

### 主介面
| 元件 ID | 觸發條件 | 處理邏輯 |
| :--- | :--- | :--- |
| `action_select` | 選擇行動類型 | 若選建設則顯示 Dropdown 2，否則直接啟用確認按鈕 |
| `building_target_select` | 選擇建設目標 | 啟用確認按鈕 |
| `confirm_action` | 點擊確認行動 | 呼叫 `player-manager.setAction()`，更新 Embed |
| `burst_execute` | 點擊瞬間行動 | 確認 AP ≥ 1 → 呼叫 `cycle-engine.burst()`，更新 Embed |
| `open_gear_upgrade` | 點擊強化裝備 | 渲染裝備強化子選單 |

### 裝備強化子選單
| 元件 ID | 觸發條件 | 處理邏輯 |
| :--- | :--- | :--- |
| `gear_type_select` | 選擇裝備類型 | 更新強化預覽資訊 |
| `attempt_upgrade` | 點擊強化 | 呼叫 `gear-manager.attemptUpgrade()`，顯示結果 |
| `back_to_main` | 點擊返回 | 重新渲染主介面 |

### 管理員介面
| 元件 ID | 觸發條件 | 處理邏輯 |
| :--- | :--- | :--- |
| `resource_select` | 選擇資源類型 | 顯示當前數量 |
| `resource_add_small` / `_large` | 點擊小額/大額增加 | 使用 `ADMIN_RESOURCE_DELTA_SMALL` / `ADMIN_RESOURCE_DELTA_LARGE` 呼叫 `resource-manager.deposit()` |
| `resource_sub_small` / `_large` | 點擊小額/大額減少 | 使用 `ADMIN_RESOURCE_DELTA_SMALL` / `ADMIN_RESOURCE_DELTA_LARGE` 呼叫 `resource-manager.withdraw()` |
| `resource_set_custom` | 點擊 Set Custom | 開啟 Modal，僅接受 >= 0 的整數，收到輸入後呼叫 `resource-manager` |

## 權限控管

- 管理員指令需驗證 Discord 伺服器管理員權限。
- 管理員指令只允許在 `DISCORD_GUILD_ID` 指定的 Guild 執行。
- 所有玩家互動均為 Ephemeral（只有本人看得見）。
- 公告指令回應為 Public。

## Changelog

- 2026.05.02.00: Removed `/idlevillage-help` command. Removed `refresh` interaction route.

---
title: "Module: command-handler"
doc_type: module
last_reviewed: 2026-08-15
source_paths:
  - src/cogs/actions.py
  - src/cogs/general.py
  - src/cogs/player_manager_cog.py
---

# Module: command-handler

定義所有 Discord Slash Commands 與互動元件（Button/Dropdown）的路由與處理。

## Slash Commands

| 指令 | 對象 | 行為 |
| :--- | :--- | :--- |
| `/idlevillage` | 所有玩家 | 先補算到期完整週期，再渲染個人主介面（Ephemeral），呼叫 ui-renderer |
| `/idlevillage-ranking` | 所有玩家 | 查詢各工具類型前三等級排行，以 Ephemeral content 回傳；超過 1900 字元時截斷並附上省略說明 |
| `/idlevillage-announcement` | 管理員 | 將當前頻道寫入 `announcement_channel_id`，並發布或刷新村莊公告（Public） |
| `/idlevillage-manage` | 管理員 | 檢查 Dashboard 訊息是否存在（不存在則在當前頻道發送新的），再開啟資源管理介面（Ephemeral） |
| `/idlevillage-manager` | 管理員 | 顯示玩家選擇器（User Select Dropdown，Ephemeral）；選定玩家後顯示完整數據面板，含各欄位編輯按鈕（Ephemeral） |

所有指令必須先檢查 interaction guild 是否等於環境變數 `DISCORD_GUILD_ID`。不符合時拒絕執行。

## 互動元件路由

### 主介面
| 元件 ID | 觸發條件 | 處理邏輯 |
| :--- | :--- | :--- |
| `action_select` | 選擇行動類型 | 若選建設則顯示建設目標 Dropdown；否則直接啟用確認按鈕 |
| `building_target_select` | 選擇建設目標 | 啟用確認按鈕 |
| `confirm_action` | 點擊確認行動 | 呼叫 `player-manager.setAction()`，更新 Embed |
| `burst_execute` | 點擊瞬間行動 | 確認 AP ≥ 1 → 呼叫 `cycle-engine.burst()`，更新 Embed |
| `open_gear_upgrade` | 點擊強化工具 | 渲染工具強化子選單 |
| `open_trial_start` | 點擊開啟試煉 | 重讀 active、cooldown 與三種資源，再計算 `max_target`。active、cooldown 或 `max_target == 0` 時返回主介面並顯示對應訊息，不建立空 Select。其餘情況顯示第 0 頁 Ephemeral 目標選單，不扣款 |
| `trial_target_page:{page}` | 點擊上一頁或下一頁 | page 代表 0-based 目的頁。重讀 active、cooldown 與三種資源，再計算 `max_target`。前置條件失效時返回主介面，不建立空 Select。頁碼超界時夾限到最後一頁。此步驟不扣款 |
| `trial_target_select` | 選擇目標 | 將選取值解析為整數，呼叫 `trial-manager.start_trial(db, now, target)`。manager 在寫入鎖內重新驗證。合法級距超過最新上限時回傳 `stale_target`。成功後刷新主介面並觸發 Public 開始通知 |
| `open_auto_tool` | 點擊自動工具 | 渲染自動工具子介面 |

### 自動工具子介面
| 元件 ID | 觸發條件 | 處理邏輯 |
| :--- | :--- | :--- |
| `auto_tool_type_select` | 選擇工具 | 重繪子介面，載入該工具可加/可減時數上限（`max_add`／`max_subtract`） |
| `auto_tool_target_select:{tool}` | 選擇建設目標（僅啟動建設） | 重繪子介面並記住目標 |
| `auto_tool_add_select:{tool}:{target}` | 選擇時數（閒置＝初始時數；運行中＝加時間） | 重繪子介面並記住有號 delta（正） |
| `auto_tool_sub_select:{tool}:{target}` | 選擇減時數（僅運行中） | 重繪子介面並記住有號 delta（負） |
| `auto_tool_confirm:{tool}:{delta}:{target}` | 點擊確認 | `delta` 為有號時數：工具未運行 → `auto_tool_manager.start(hours=delta)`（要求 ≥1 該工具素材、只扣 1，不吃萬能）；運行中 `delta>0` → `add_time`、`delta<0` → `subtract_time`（純調時間、不碰素材，減到底即停）；失敗顯示統一錯誤且不改狀態；重繪子介面 |
| `back_to_main` | 點擊返回 | 重新渲染主介面 |

開啟主介面（`/idlevillage`、`back_to_main`）時，除補算手動行動外，也對該玩家所有到期自動工具呼叫 `settle_auto_tool_cycles`。詳見 `managers/auto-tool-manager.md`。

### 工具強化子選單
| 元件 ID | 觸發條件 | 處理邏輯 |
| :--- | :--- | :--- |
| `gear_type_select` | 選擇工具類型 | 更新強化預覽資訊（保留當前模式） |
| `upgrade_mode_select:{gear_type}` | 選擇強化模式（標準 / 墊檔 / 鐵齒） | 更新成本預覽與成功率顯示 |
| `attempt_upgrade:{gear_type}:{mode}` | 點擊強化 | 呼叫 `gear-manager.attempt_upgrade(db, user_id, gear_type, now, mode)`，顯示結果 |
| `open_affix_mgmt:{gear_type}` | 點擊詞條管理 | 切到獨立詞條管理畫面；實際開啟時不預設選中工具類型 |
| `back_to_main` | 點擊返回 | 重新渲染主介面 |

### 詞條管理畫面
| 元件 ID | 觸發條件 | 處理邏輯 |
| :--- | :--- | :--- |
| `affix_gear_select` | 選擇工具類型 | 重新渲染詞條管理畫面，載入該工具的槽位與現有詞條 |
| `affix_slot_select:{gear_type}` | 選擇要清除的詞條槽 | 重新渲染詞條管理畫面，將該槽標記為待清除 |
| `affix_extract:{gear_type}` | 點擊抽取詞條 | 消耗 `AFFIX_EXTRACT_COST` 個素材（先扣對應素材，不足由萬能素材補足），隨機填入第一個空槽 |
| `affix_clear:{gear_type}:{slot_index}` | 點擊清除詞條 | 消耗 `AFFIX_CLEAR_COST` 個素材（先扣對應素材，不足由萬能素材補足），清除指定槽詞條 |
| `back_to_gear:{gear_type}` | 點擊返回 | 回到工具強化子選單 |

### 管理員介面（資源管理）
| 元件 ID | 觸發條件 | 處理邏輯 |
| :--- | :--- | :--- |
| `resource_select` | 選擇資源類型 | 顯示當前數量 |
| `resource_add_small` / `_large` | 點擊小額/大額增加 | 使用 `ADMIN_RESOURCE_DELTA_SMALL` / `ADMIN_RESOURCE_DELTA_LARGE` 呼叫 `resource-manager.deposit()` |
| `resource_sub_small` / `_large` | 點擊小額/大額減少 | 使用 `ADMIN_RESOURCE_DELTA_SMALL` / `ADMIN_RESOURCE_DELTA_LARGE` 呼叫 `resource-manager.withdraw()` |
| `resource_set_custom` | 點擊 Set Custom | 開啟 Modal，僅接受 >= 0 的整數，收到輸入後呼叫 `resource-manager` |

### 玩家管理員介面（/idlevillage-manager）
| 元件 ID | 觸發條件 | 處理邏輯 |
| :--- | :--- | :--- |
| `mgr_player_select` | User Select — 選擇目標玩家 | 查詢玩家 DB；玩家不存在回傳錯誤；存在則呼叫 `build_manager_embed()` + `build_manager_components()` 顯示面板 |
| `mgr_edit_gear:{uid}` | 點擊「編輯工具等級」按鈕 | 彈出「編輯工具等級」Modal（4 欄位：採集/建設/戰鬥/研究等級） |
| `mgr_edit_material:{uid}` | 點擊「編輯素材數量」按鈕 | 彈出「編輯素材數量」Modal（5 欄位：採集/建設/戰鬥/研究/萬能） |
| `mgr_edit_pity:{uid}` | 點擊「編輯保底計數」按鈕 | 彈出「編輯保底計數」Modal（4 欄位） |
| `mgr_edit_risky:{uid}` | 點擊「編輯鐵齒失敗累積」按鈕 | 彈出「編輯鐵齒失敗累積」Modal（1 欄位） |
| `mgr_modal_gear:{uid}` | 提交工具等級 Modal | 驗證非負整數 → 呼叫 `player_manager.set_gear_level()` × 4 → 刷新面板 |
| `mgr_modal_material:{uid}` | 提交素材 Modal | 驗證非負整數 → 呼叫 `player_manager.set_material()` × 4 + `set_universal_material()` × 1 → 刷新面板 |
| `mgr_modal_pity:{uid}` | 提交保底 Modal | 驗證非負整數 → 呼叫 `player_manager.set_pity()` × 4 → 刷新面板 |
| `mgr_modal_risky:{uid}` | 提交鐵齒 Modal | 驗證非負整數 → 呼叫 `player_manager.set_risky_failed_levels()` → 刷新面板 |

所有 `mgr_*` 互動均需 guild/admin 雙重驗證。`{uid}` 為目標玩家的 Discord user ID。

## 權限控管

- 管理員指令需驗證 Discord 伺服器管理員權限。
- 管理員指令只允許在 `DISCORD_GUILD_ID` 指定的 Guild 執行。
- 所有玩家互動均為 Ephemeral（只有本人看得見）。
- 公告指令回應為 Public。

## Changelog

- 2026-08-15: `open_trial_start` 改為顯示動態目標選單。新增 `trial_target_select` 與 `trial_target_page:{page}` 路由。選取目標後才原子開啟試煉。
- 2026-07-20: Auto-tool routes reworked for pay-as-you-go: `auto_tool_count_select` replaced by `auto_tool_add_select` / `auto_tool_sub_select`; `auto_tool_confirm:{tool}:{delta}:{target}` carries a signed hours delta routed to `start` / `add_time` / `subtract_time`. See `managers/auto-tool-manager.md`.
- 2026-07-17: Added auto-tool routes (`open_auto_tool`, `auto_tool_type_select`, `auto_tool_target_select:{tool}`, `auto_tool_count_select:{tool}:{target}`, `auto_tool_confirm:{tool}:{count}:{target}`); opening the main interface now also settles due auto-tools. See `managers/auto-tool-manager.md`.
- 2026-07-17: `affix_extract`/`affix_clear` 素材消耗改為「先扣對應素材，不足由萬能素材補足」；路由行為不變，僅素材來源擴充。
- 2026-07-14: `open_trial_start` no longer opens a Modal — clicking it directly starts a trial with a fixed, system-chosen amount/resource; no player input at all. Removed the `modal_start_trial` route.
- 2026-07-14: Replaced the `/idlevillage-trial` slash command with an `open_trial_start` button on the main interface (same row as burst/gear upgrade), disabled unless a trial can currently be started; submits via `modal_start_trial` Modal (resource type + target, free-text) instead of slash command options.
- 2026-07-14: `/idlevillage-manager` 編輯素材數量 Modal 新增第 5 個欄位（萬能素材），`mgr_modal_material` 提交流程改為呼叫 `set_material()` × 4 + `set_universal_material()` × 1。
- 2026-07-14: Removed `offering_resource_select` dropdown route and offering resource validation in `confirm_action:` handler.
- 2026-05-22: Added `extract_affix:{gear_type}` and `clear_affix:{gear_type}:{slot_index}` routes for the tool affix system.
- 2026-05-15: Replaced five `/idlevillage-manager` sub-commands with a single unified interface driven by user select + modal edits.
- 2026.05.15: Added `upgrade_mode_select:{gear_type}` interaction route for mode selection. `attempt_upgrade` custom_id now encodes gear_type and mode as `attempt_upgrade:{gear_type}:{mode}`.
- 2026.05.06.01: Official user-facing gear naming changed to tools; command
  handler copy now uses 工具強化 and 工具類型.
- 2026.05.02.00: Removed `/idlevillage-help` command. Removed `refresh` interaction route.

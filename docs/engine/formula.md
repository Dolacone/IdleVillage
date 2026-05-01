# Module: formula

效率公式與全局平衡參數。其他所有模組在計算產出時呼叫此模組。

所有平衡數值必須由環境變數讀取，程式碼不得 hardcode。
`.env.example` 必須列出所有 v2 使用的環境變數。所有列出的 key 都是 required；啟動時若缺少任一 key，列印 missing key 並啟動失敗。

## 效率公式

$$\text{raw_output} = \text{base_output} \times (1 + \text{stage_bonus} + \text{gear_bonus} + \text{facility_bonus})$$

所有計算結果入庫前一律 floor 為整數。

| 加成項 | 計算方式 | 作用範圍 |
| :--- | :--- | :--- |
| 關卡加成 | 已通過總關卡數 × `STAGE_BONUS_PER_CLEAR` | 全局，所有行動共用 |
| 裝備加成 | 對應裝備等級 × `GEAR_BONUS_PER_LEVEL` | 類別對應（採集裝備只加採集） |
| 設施加成 | 對應設施等級 × `FACILITY_BONUS_PER_LEVEL` | 類別對應（採集場只加採集） |

## 行動類別與對應關係

| 行動 | 裝備欄位 | 設施欄位 |
| :--- | :--- | :--- |
| 採集 | 採集道具等級 | 採集場等級 |
| 建設 | 建築工具等級 | 加工廠等級 |
| 戰鬥 | 武器防具等級 | 狩獵場等級 |
| 研究 | 研究裝備等級 | 研究所等級 |

## Environment variables

`.env.example` is the SSOT for startup values. Every key listed here is required at runtime. This file defines which modules own each key.

| Environment variable | Owning module |
| :--- | :--- |
| `DISCORD_TOKEN` | Runtime config |
| `DISCORD_GUILD_ID` | `discord/command-handler.md` |
| `DATABASE_PATH` | `db-schema.md` |
| `ANNOUNCEMENT_CHANNEL_ID` | `discord/notification.md` |
| `ADMIN_IDS` | `discord/command-handler.md` |
| `ACTION_CYCLE_MINUTES` | `engine/cycle-engine.md` |
| `WATCHER_HEARTBEAT_SECONDS` | `engine/cycle-engine.md` |
| `MAX_CYCLES_PER_SETTLEMENT` | `engine/cycle-engine.md` |
| `REFRESH_COOLDOWN_SECONDS` | `discord/command-handler.md` |
| `BASE_OUTPUT` | `engine/formula.md` |
| `FOOD_COST` | `engine/action-resolver.md` |
| `WOOD_COST` | `engine/action-resolver.md` |
| `KNOWLEDGE_COST` | `engine/action-resolver.md` |
| `MATERIAL_DROP_RATE` | `managers/player-manager.md` |
| `ADMIN_RESOURCE_DELTA_SMALL` | `discord/command-handler.md` |
| `ADMIN_RESOURCE_DELTA_LARGE` | `discord/command-handler.md` |
| `STAGE_BONUS_PER_CLEAR` | `engine/formula.md` |
| `GEAR_BONUS_PER_LEVEL` | `engine/formula.md` |
| `FACILITY_BONUS_PER_LEVEL` | `engine/formula.md` |
| `AP_CAP` | `managers/player-manager.md` |
| `AP_RECOVERY_MINUTES` | `managers/player-manager.md` |
| `STAGE_BASE_TARGET` | `managers/stage-manager.md` |
| `STAGE_TARGET_GROWTH_PER_ROUND` | `managers/stage-manager.md` |
| `UPGRADE_STAGE_TARGET_MULTIPLIER` | `managers/stage-manager.md` |
| `STAGE_OVERTIME_SECONDS` | `managers/stage-manager.md` |
| `STAGE_OVERTIME_PROGRESS_MULTIPLIER` | `managers/stage-manager.md` |
| `BUILDING_XP_PER_LEVEL` | `managers/building-manager.md` |
| `GEAR_PITY_BONUS` | `managers/gear-manager.md` |
| `GEAR_MIN_SUCCESS_RATE` | `managers/gear-manager.md` |
| `GEAR_RATE_LOSS_PER_LEVEL` | `managers/gear-manager.md` |

## Rounding

- 所有產出、消耗、XP、進度入庫前都 floor 為整數。
- partial cycle rounding is owned by `engine/cycle-engine.md`.
- stage overtime progress behavior is owned by `managers/stage-manager.md`.

# Module: stage-manager

管理關卡進度、通關判定、難度縮放與升級關邏輯。

## 五關循環結構

每輪依序進行五關：

| 順序 | 關卡類型 | 計分行動 | 目標數值 |
| :--- | :--- | :--- | :--- |
| 1 | 採集關 | 採集行動產出 | `round_difficulty` |
| 2 | 建造關 | 建設行動產出 | `round_difficulty` |
| 3 | 狩獵關 | 戰鬥行動產出 | `round_difficulty` |
| 4 | 研究關 | 研究行動產出 | `round_difficulty` |
| 5 | 升級關 | **全部行動產出合計** | `round_difficulty × UPGRADE_STAGE_TARGET_MULTIPLIER` |

## 難度計算

```
round_number     = floor(stages_cleared / 5) + 1  // 當前輪次（從 1 開始）
round_difficulty = STAGE_BASE_TARGET × (1 + (round_number - 1) × STAGE_TARGET_GROWTH_PER_ROUND)
```

> 驗證：stages_cleared=0 → 第1輪、stages_cleared=4（打升級關前）→ 第1輪、stages_cleared=5 → 第2輪。

## 關卡進度規則

- **普通關**：只有對應類型的行動產出計入進度。
- **升級關**：所有行動類型的產出均計入同一進度條。
- **逾時懲罰**：關卡開始 `STAGE_OVERTIME_SECONDS` 後，後續產出計入進度時 × `STAGE_OVERTIME_PROGRESS_MULTIPLIER`（進度不清零，繼續累積）。
  - 只影響關卡進度，不影響資源產出、建築 XP 或素材掉落。
  - 偵測方式：**懶惰偵測**，由 `addProgress()` 在每次結算時檢查 `now - stage_started_at > STAGE_OVERTIME_SECONDS`，無獨立計時器。
  - 通知方式：首次偵測超時且 `overtime_notified = false` 時發送一次，並設為 true。
  - UI 提示：逾時狀態下，村莊狀態 Dashboard 與個人 Dashboard 均顯示警示（見 ui-renderer）。

## 部署架構

- v2 preview 僅支援環境變數指定的單一 Discord Guild。
- 村莊進度為該 Guild 的單一全域狀態。

## 村莊全局狀態

| 欄位 | 初始值 | 說明 |
| :--- | :--- | :--- |
| `stages_cleared` | 0 | 已通過總關卡數 |
| `current_stage_index` | 0 | 目前是第幾關（0~4 循環） |
| `current_stage_progress` | 0 | 當前關卡累積進度 |
| `stage_started_at` | — | 當前關卡開始時間 |
| `overtime_notified` | false | 當前關卡超時通知是否已發送 |
| `dashboard_message_id` | null | 村莊 Dashboard 訊息 ID |
| `dashboard_channel_id` | null | 村莊 Dashboard 所在頻道 ID |

## 通關流程

```
當 current_stage_progress >= target：
  1. stages_cleared += 1（觸發 STAGE_BONUS_PER_CLEAR 關卡加成）
  2. 若 current_stage_index == 4（升級關）：
       → 建築等級上限自然提升
       → 呼叫 building-manager.checkAllUpgrades()
  3. current_stage_index = (current_stage_index + 1) % 5
  4. current_stage_progress = 0
  5. stage_started_at = now()
  6. overtime_notified = false
  7. 觸發通關通知（所有關卡都通知）
```

超額進度不帶入下一關。單次 settlement 最多只會讓當前關卡通關一次；剩餘量捨棄。Burst 的 3 次完整 settlement 各自獨立判定。

## 操作介面（供其他模組呼叫）

- `addProgress(amount, actionType)` — 新增進度（自動判斷是否計入、是否逾時減半）
- `getStageInfo()` — 回傳當前關卡類型、進度、目標、剩餘時間
- `getStageClearedCount()` — 回傳已通過總關卡數（供 formula 模組取用）

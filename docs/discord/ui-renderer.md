# Module: ui-renderer

負責建構所有 Discord Embed 與互動元件（Button、Dropdown）。不包含業務邏輯，只負責呈現。

## 村莊 Dashboard Embed（Public，由 Watcher 持續更新）

此 embed 為固定 Public 訊息，Watcher 每輪結算後 edit 更新。不含個人資訊。

### 格式模板

```
(Last Update: <t:{unix_timestamp}:R>)

**Idle Village**

📋 Stage {stages_cleared}／{total}｜{stage_name}
   {progress_bar}  {progress} / {target} ({pct}%)
   ⏰ <t:{deadline}:R>
{if overtime}   ⚠️ 逾時！通關效率已降低（產出計分 ×0.5）{/if}

Village Resources
🌾 {food} | 🪵 {wood} | 🧠 {knowledge}

Village Buildings (等級上限：Lv{cap})
[code block]
採集場  Lv{n} ({xp_progress}/{next_requirement} = {pct}%)
加工廠  Lv{n} ({pct}%)
狩獵場  Lv{n} ({pct}%)
研究所  Lv{n} ({pct}%)
[/code block]

Villager Actions
[code block]
{action_name}: {count}   ← 依人數降序，未設定行動的玩家不列出
...
[/code block]
```

### Buildings 百分比計算

`pct = floor(xp_progress / next_requirement × 100)`

例：採集場目前 Lv1，`xp_progress = 50`，升 Lv2 需 `2 × BUILDING_XP_PER_LEVEL`。

若建築已達 level cap 且進度滿，顯示 clamp 後數值。

### Villager Actions 動作名稱

| 行動 | 顯示名稱 |
| :--- | :--- |
| 採集 | 採集 |
| 建設（採集場） | 建設（採集場） |
| 建設（加工廠） | 建設（加工廠） |
| 建設（狩獵場） | 建設（狩獵場） |
| 戰鬥 | 戰鬥 |
| 研究 | 研究 |

排序：人數降序；人數相同則動作名稱升序。

## 主介面 Embed（/idlevillage，Ephemeral）

此 embed 為 Ephemeral（只有指令使用者看得到），包含村莊狀態（同上）+ 個人狀態與互動元件。

### 個人狀態區（下半部）
```
**Player Status**
🏅 等級：🌾採集 Lv{n} | 🔨建設 Lv{n} | ⚔️戰鬥 Lv{n} | 🔬研究 Lv{n}
🎒 素材：🌾採集 {n} | 🔨建設 {n} | ⚔️戰鬥 {n} | 🔬研究 {n}
🏃 行動：{emoji}{action_name}（下次結算：<t:{next_cycle}:R>）
⚡ AP：{ap} / 24
```

行動 emoji 對應：🌾採集、🔨建設、⚔️戰鬥、🔬研究

## 互動元件

### 行動選擇組
- **Dropdown 1**：選擇行動
  - 選項：採集 / 建設 / 戰鬥 / 研究
- **Dropdown 2**（僅選擇「建設」後出現）：選擇建設目標
  - 選項：採集場 / 加工廠 / 狩獵場
  - 顯示格式：`{建築名} Lv{n}（XP: {xp_progress}/{next_requirement}）`
- **Button**：`✅ 確認行動`（Green）

### AP 行動組
- **Button**：`⚡ 爆發執行`（Yellow）
  - 禁用條件：AP < 1
  - 顯示剩餘 AP 數
- **Button**：`🔨 強化裝備`（Blue）
  - 禁用條件：AP < 1 或所有裝備已達上限

### 其他
- **Button**：`🔄 Refresh`（Gray，冷卻時間為 REFRESH_COOLDOWN_SECONDS）

## 裝備強化子選單 Embed

```
🔨 裝備強化
─────────────────────────────
選擇裝備：[Dropdown]

{gear_name}：Lv{current} → Lv{target}
成功率：{base_rate}%（+{pity×5}% 保底）= {final_rate}%
消耗：⚡ 1 AP + {n} 個 {material_name}
持有素材：{material_count} 個
裝備等級上限：Lv{cap}（研究所 Lv{n}）
```

- **Button**：`🎲 強化`（Green，禁用條件：素材不足 / AP 不足 / 已達上限）
- **Button**：`← 返回`（Gray）

## 管理員介面 Embed（/idlevillage-manage）

```
⚙️ 資源管理

[Dropdown：食物 / 木頭 / 知識]

當前 {resource_name}：{amount}
```
- **Button**：`+{ADMIN_RESOURCE_DELTA_SMALL}`、`+{ADMIN_RESOURCE_DELTA_LARGE}`、`-{ADMIN_RESOURCE_DELTA_SMALL}`、`-{ADMIN_RESOURCE_DELTA_LARGE}`
- **Button**：`Set Custom`（觸發 Modal）

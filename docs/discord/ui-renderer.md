---
title: "Module: ui-renderer"
doc_type: module
last_reviewed: 2026-05-02
source_paths:
  - src/cogs/ui_renderer.py
---

# Module: ui-renderer

負責建構所有 Discord Embed 與互動元件（Button、Dropdown）。不包含業務邏輯，只負責呈現。

## 村莊 Dashboard Embed（Public，由 Watcher 持續更新）

此 embed 為固定 Public 訊息，Watcher 每輪結算後 edit 更新。不含個人資訊。

### 格式模板

```
(Last Update: <t:{unix_timestamp}:R>)

**Idle Village**

📋 關卡 {stages_cleared}: {stage_type_zh}
   {progress_bar}  {progress} / {target} ({pct}%)
   ⏰ 期限: <t:{deadline}:R>
{if overtime}   ⚠️ 逾時！通關效率已降低（產出計分 ×0.5）{/if}

公用資源
🌾 {food} | 🪵 {wood} | 🧠 {knowledge}

公用設施 (等級上限：Lv{cap})
🌾 採集場 Lv{n} ({pct}%)
🔨 加工廠 Lv{n} ({pct}%)
⚔️ 狩獵場 Lv{n} ({pct}%)
🔬 研究所 Lv{n} ({pct}%)

村民行動
[code block]
{action_name}: {count}   ← 依人數降序，未設定行動的玩家不列出
...
[/code block]
```

`{stage_type_zh}` 對應表：採集 / 建設 / 戰鬥 / 研究 / 升級。

### Buildings 百分比計算

`pct = floor(xp_progress / next_requirement × 100)`

例：採集場目前 Lv1，`xp_progress = 50`，升 Lv2 需 `2 × BUILDING_XP_PER_LEVEL`。

若建築已達 level cap，顯示 `100%`。

建築圖示對應：採集場 🌾、加工廠 🔨、狩獵場 ⚔️、研究所 🔬。

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
**個人資訊**
🏅 裝備：🌾 {n} | 🔨 {n} | ⚔️ {n} | 🔬 {n}
🎒 素材：🌾 {n} | 🔨 {n} | ⚔️ {n} | 🔬 {n}
🏃 行動：{emoji}{action_name}（下次結算：<t:{next_cycle}:R>）
⚡ AP：{ap} / 24
```

行動 emoji 對應：🌾採集、🔨建設、⚔️戰鬥、🔬研究

## 互動元件

### 元件排列順序

  Row 1: Button — ⚡ 消耗AP立刻完成三次行動 | 🔨 強化裝備
  Row 2: Dropdown — 選擇行動
  Row 3: Dropdown — 選擇建設目標（僅 building 時出現）
  Row 4: Button — ✅ 確認行動

Discord 上限為 5 個 action row。選擇建設時達到 4 rows。

### 瞬間行動

- **Button**：`⚡ 消耗AP立刻完成三次行動`（Blue/Primary）
  - 禁用條件：AP < 1 或無當前行動

### 強化裝備

- **Button**：`🔨 強化裝備`（Blue）
  - 禁用條件：AP < 1 或所有裝備已達上限

### 行動選擇組
- **Dropdown 1**：選擇行動
  - 選項：採集 / 建設 / 戰鬥 / 研究
- **Dropdown 2**（僅選擇「建設」後出現）：選擇建設目標
  - 選項：採集場 / 加工廠 / 狩獵場
  - 顯示格式：`{建築名} Lv{n}（XP: {xp_progress}/{next_requirement}）`
- **Button**：`✅ 確認行動`（Green）

### 其他

無額外按鈕。

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

## Changelog

- 2026.05.02.00: Stage line format changed to `📋 關卡 {n}: {type_zh}`; deadline prefixed with `期限:`; section headers localised to `公用資源` / `公用設施` / `村民行動` / `個人資訊`; building list moved out of code block with per-row emoji; gear line label changed to `裝備`, category text labels and `Lv` prefix removed; materials line category text labels removed; burst button renamed `⚡ 消耗AP立刻完成三次行動` and moved to Row 1 alongside `🔨 強化裝備`; Refresh button removed.

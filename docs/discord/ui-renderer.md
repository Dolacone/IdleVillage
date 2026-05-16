---
title: "Module: ui-renderer"
doc_type: module
last_reviewed: 2026-05-15
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
📊 效率：🌾 {n}(+{p}%) | 🔨 {n}(+{p}%) | ⚔️ {n}(+{p}%) | 🔬 {n}(+{p}%)
🏅 工具：🌾 {n} | 🔨 {n} | ⚔️ {n} | 🔬 {n}
🎒 素材：🌾 {n} | 🔨 {n} | ⚔️ {n} | 🔬 {n}
🏃 行動：{emoji}{action_name}（下次結算：<t:{next_cycle}:R>）
⚡ AP：{ap} / 24
```

效率欄位：`{n}` 為該行動類別的有效產出，`{p}` 為總加成百分比（floor）。
計算方式參見 engine/formula.md 效率公式；關卡加成使用已完成升級關卡數
`floor(stages_cleared / 5)`，不使用已通過總關卡數。
emoji 順序與 工具 / 素材 欄位一致：🌾 🔨 ⚔️ 🔬。

行動 emoji 對應：🌾採集、🔨建設、⚔️戰鬥、🔬研究

## 互動元件

### 元件排列順序

  Row 1: Button — ⚡ 消耗AP立刻完成三次行動 | 🔨 強化工具
  Row 2: Dropdown — 選擇行動
  Row 3: Dropdown — 選擇建設目標（僅 building 時出現）
  Row 4: Button — ✅ 確認行動

Discord 上限為 5 個 action row。選擇建設時達到 4 rows。

### 瞬間行動

- **Button**：`⚡ 消耗AP立刻完成三次行動`（Blue/Primary）
  - 禁用條件：AP < 1 或無當前行動

### 強化工具

- **Button**：`🔨 強化工具`（Blue）
  - 禁用條件：AP < 1 或所有工具已達上限

### 行動選擇組
- **Dropdown 1**：選擇行動
  - 選項：採集 / 建設 / 戰鬥 / 研究
  - 每個選項附帶描述，說明次要消耗與產出（食物消耗為全行動共用，不另列）：
    - 採集：`產出 🌾食物 + 🪵木頭`
    - 建設：`消耗 🪵木頭 | 產出 建築XP`
    - 戰鬥：`消耗 🪵木頭 | 產出 🧠知識`
    - 研究：`消耗 🧠知識 | 產出 研究所XP`
- **Dropdown 2**（僅選擇「建設」後出現）：選擇建設目標
  - 選項：採集場 / 加工廠 / 狩獵場
  - 顯示格式：`{建築名} Lv{n}（XP: {xp_progress}/{next_requirement}）`
- **Button**：`✅ 確認行動`（Green）

### 其他

無額外按鈕。

## 工具強化子選單 Embed

```
🔨 工具強化
─────────────────────────────
選擇工具：[Dropdown]
選擇強化模式：[Dropdown: 標準 / 墊檔 / 鐵齒]

{gear_name}：Lv{current} → Lv{target}
模式：標準
成功率：{base_rate}%（+保底{pity_total}% +鐵齒{risky_bonus}%）= {final_rate}%
保底率：{pity} x {pity_per}% = {pity_total}%
鐵齒率：{risky_failed_levels} x 0.01% = {risky_bonus}%
消耗：⚡ 1 AP + {n} 個 {material_name}
持有素材：{material_count} 個
⚡ AP：{ap} / {ap_cap}
工具等級上限：Lv{cap}（研究所 Lv{n}）
```

保底率與鐵齒率明細行僅在標準（normal）與鐵齒（risky）模式下顯示；buffer 模式略去。
墊檔模式下成功率欄位顯示 `0%（墊檔不進行強化）`，不顯示保底率/鐵齒率明細行。
`{risky_bonus}` = `risky_failed_levels × 0.01`（去除尾隨零，如 1000 級顯示 `10%`）。

成功率顯示必須和 managers/gear-manager.md 的成功率計算一致。若設定值代表整數百分比，
UI 不得因二進位浮點誤差少顯示 1%。例如 `GEAR_RATE_LOSS_PER_LEVEL=0.10`
時，Lv6、保底 0、鐵齒 0 的顯示為 `成功率：40%（+保底0% +鐵齒0%）= 40%`。

工具類型 Dropdown 每個選項附帶描述：
- 未達上限：`Lv{n} → Lv{n+1}: {action_label}產出 +{n×pct}% → +{(n+1)×pct}%`（pct = floor(GEAR_BONUS_PER_LEVEL × 100)）
- 已達上限：`已達等級上限 Lv{cap}`

強化模式 Dropdown（custom_id: `upgrade_mode_select:{gear_type}`）每個選項附帶描述：
- 標準：`正常消耗，失敗 pity+1`
- 墊檔：`半價素材，必定 pity+1，無需擲骰`
- 鐵齒：`僅消耗 1 個素材，失敗則 pity 歸零；成功無保底時 +1~+3`

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

## 玩家管理員介面 Embed（/idlevillage-manager，Ephemeral）

由 `build_manager_embed()` 與 `build_manager_components()` 渲染，僅管理員可見。

### Embed 格式

- **Title**：`玩家管理：{target_user_display_name}`
- **Color**：`disnake.Color.orange()`
- **Fields**（各自 `inline=False`）：
  | Field name | 格式 |
  | :--- | :--- |
  | 工具等級 | `採集 {gear_gathering} ｜ 建設 {gear_building} ｜ 戰鬥 {gear_combat} ｜ 研究 {gear_research}` |
  | 素材數量 | `採集 {materials_gathering} ｜ 建設 {materials_building} ｜ 戰鬥 {materials_combat} ｜ 研究 {materials_research}` |
  | 保底計數 | `採集 {pity_gathering} ｜ 建設 {pity_building} ｜ 戰鬥 {pity_combat} ｜ 研究 {pity_research}` |
  | 鐵齒失敗累積 | `{risky_failed_levels}` |

### 互動元件

Row 1 — 四個 `ButtonStyle.secondary` 按鈕：

| 按鈕標籤 | custom_id |
| :--- | :--- |
| 編輯工具等級 | `mgr_edit_gear:{target_user_id}` |
| 編輯素材 | `mgr_edit_material:{target_user_id}` |
| 編輯保底 | `mgr_edit_pity:{target_user_id}` |
| 編輯鐵齒 | `mgr_edit_risky:{target_user_id}` |

`{target_user_id}` 為目標玩家的 Discord user ID（字串）。

## Changelog

- 2026.05.02.00: Stage line format changed to `📋 關卡 {n}: {type_zh}`; deadline prefixed with `期限:`; section headers localised to `公用資源` / `公用設施` / `村民行動` / `個人資訊`; building list moved out of code block with per-row emoji; gear line label changed to `裝備`, category text labels and `Lv` prefix removed; materials line category text labels removed; burst button renamed `⚡ 消耗AP立刻完成三次行動` and moved to Row 1 alongside `🔨 強化裝備`; Refresh button removed.
- 2026.05.02.02: Action dropdown options now include descriptions showing secondary cost and output per action type. Gear type dropdown options now include descriptions showing the level transition and cumulative stat gain (`Lv{n} → Lv{n+1}: {type}產出 +{n×pct}% → +{(n+1)×pct}%`), or `已達等級上限 Lv{cap}` when at cap.
- 2026.05.02.03: Removed incorrect special-case rule "若建築已達 level cap，顯示 100%". 100% is reached naturally when `xp_progress` reaches `next_req`; no display override is needed or correct.
- 2026.05.04.00: Added 📊 效率 as line 1 of 個人資訊, before 裝備. Displays `{output}(+{pct}%)` per action type using the formula in engine/formula.md.
- 2026.05.06.01: Official user-facing gear naming changed to tools:
  dashboard line `🏅 工具`, button `🔨 強化工具`, and full names
  採集工具, 建設工具, 狩獵工具, 研究工具.
- 2026.05.15: Risky mode now shows `鐵齒等級: {n} (+{pct}%)` line. Risky dropdown description updated to reflect multi-level success.
- 2026.05.16: Success rate line format updated to `成功率：{base}%（+保底{pity_total}% +鐵齒{risky}%）= {final}%`. Two detail lines added below (保底率、鐵齒率) for normal/risky modes. Bottom `鐵齒等級` line removed.
- 2026.05.15: Added mode selection dropdown (`upgrade_mode_select:{gear_type}`) to the gear upgrade sub-menu. Mode descriptions shown inline. Buffer mode displays 0% success rate.
- 2026-05-15: Added `build_manager_embed()` and `build_manager_components()` for the unified manager interface.
- 2026.05.06.00: Gear upgrade success-rate display must match gear-manager precision semantics. Lv6 with no pity displays 40%, not 39%.

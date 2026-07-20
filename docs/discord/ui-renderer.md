---
title: "Module: ui-renderer"
doc_type: module
last_reviewed: 2026-07-17
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
🏆 試煉 {trial_status}

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

### 試煉進度列

`🏆 試煉` 這一行永遠顯示（不再因非進行中而省略），內容依當下狀態切換為以下四態之一（判斷優先序：進行中 → 冷卻中 → 資源不足 → 可開啟，與下方「開啟試煉」按鈕 disabled 條件一致）：

1. 進行中（`trial_state.is_active`）：
   ```
   🏆 試煉 {progress} / {target} ({pct}%)
      {progress_bar}
      ⏰ 期限: <t:{deadline}:R>
   ```
   `{deadline}` = `trial_state.started_at` 的 unix 時間 + `TRIAL_DURATION_SECONDS`。
2. 冷卻中（`is_active=0` 且 `ended_at` 存在且 `now - ended_at < TRIAL_COOLDOWN_SECONDS`）：
   `🏆 試煉 ⏳ 可於 <t:{cooldown_deadline}:t> 後開啟`
   `{cooldown_deadline}` = `ended_at` 的 unix 時間 + `TRIAL_COOLDOWN_SECONDS`。使用 Discord `:t`（短時間）格式顯示固定時刻，而非 `:R` 相對時間，避免與「多久後」的倒數混淆。
3. 資源不足（`is_active=0`，冷卻已過，但村莊三種資源皆低於 `TRIAL_TARGET_AMOUNT`）：
   `🏆 試煉 ⚠️ 資源不足，尚無法開啟`
4. 可開啟（`is_active=0`，冷卻已過，且至少一種資源 `>= TRIAL_TARGET_AMOUNT`）：
   `🏆 試煉 ✅ 可開啟試煉`

刻意不顯示試煉花費的資源類型與發起者：資源類型只在試煉開始的 Public 通知中以「花費」措辭呈現（避免讓人誤以為試煉目標是單一資源的收集數量，因為目標實際上是全服玩家行動產出總和，與資源類型無關）；發起者也僅出現在該通知中，Dashboard 不重複呈現。

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

村莊狀態區塊沿用與 Dashboard 完全相同的 `_build_village_section`，包含「試煉進度列」章節所述的四態 `🏆 試煉` 顯示（進行中／可開啟／資源不足／冷卻中），與下方「🏆 開啟試煉」按鈕的 disabled 狀態並存、互為補充。

### 個人狀態區（下半部）
```
**個人資訊**
📊 效率：🌾 {n}(+{p}%) | 🔨 {n}(+{p}%) | ⚔️ {n}(+{p}%) | 🔬 {n}(+{p}%)
🏅 工具：🌾 {n} | 🔨 {n} | ⚔️ {n} | 🔬 {n}
🎒 素材：🌾 {n} | 🔨 {n} | ⚔️ {n} | 🔬 {n} | 🌟 {n}
🏃 行動：{emoji}{action_name}（下次結算：<t:{next_cycle}:R>）
⚡ AP：{ap} / {ap_cap}
⚡ AP：{ap} / {ap_cap}（下次：<t:{next_ap_unix}:R>）（AP < cap 時顯示）
🏆 試煉貢獻：{n}（僅試煉進行中時顯示）
{trial_message}（僅剛點擊「🏆 開啟試煉」按鈕後顯示一次，如 `✅ 試煉已開始！` 或 `⚠️ 開啟試煉失敗，請重新嘗試。`；下次重新渲染主介面後即消失）
```

效率欄位：`{n}` 為該行動類別的有效產出，`{p}` 為總加成百分比（floor）。
計算方式參見 engine/formula.md 效率公式；關卡加成使用已完成升級關卡數
`floor(stages_cleared / 5)`，不使用已通過總關卡數。
emoji 順序與 工具 欄位一致：🌾 🔨 ⚔️ 🔬；素材欄位額外附加 🌟（萬能素材）。

行動 emoji 對應：🌾採集、🔨建設、⚔️戰鬥、🔬研究

## 互動元件

### 元件排列順序

  Row 1: Button — ⚡ 消耗AP立刻完成三次行動 | 🔨 強化工具 | 🏆 開啟試煉 | ⚙️ 自動工具
  Row 2: Dropdown — 選擇行動
  Row 3: Dropdown — 選擇建設目標（僅 building 時出現）
  Row 4: Button — ✅ 確認行動

Discord 上限為 5 個 action row。選擇建設時達到 4 rows。

### 瞬間行動

- **Button**：`⚡ 消耗AP立刻完成三次行動`（Blue/Primary）
  - 禁用條件：AP < 1 或無當前行動

### 強化工具

- **Button**：`🔨 強化工具`（Blue）
  - 禁用條件：所有工具已達上限（AP 不足時仍可開啟介面）

### 開啟試煉

- **Button**：`🏆 開啟試煉`（Blue，custom_id: `open_trial_start`）
  - 禁用條件：目前已有進行中試煉；或試煉冷卻中（`trial_state.ended_at` 存在且 `now - ended_at < TRIAL_COOLDOWN_SECONDS`）；或村莊三種資源（食物/木頭/知識）皆不足 `TRIAL_TARGET_AMOUNT`
  - 點擊後**不彈出任何 Modal，不需玩家輸入任何資訊**：直接呼叫 `trial-manager.start_trial()`，由系統在可負擔 `TRIAL_TARGET_AMOUNT` 的資源類型中均勻隨機選一種扣除
  - 成功時於主介面個人資訊區塊下方顯示 `✅ 試煉已開始！`，並觸發 Public 開始通知；前置條件不滿足時（理論上按鈕已 disabled，但仍防呆處理併發競態）顯示統一的 `⚠️ 開啟試煉失敗，請重新嘗試。`，不扣除資源

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

行動下拉排除正在作為自動工具運行的工具（見下方「自動工具子介面」與 `managers/auto-tool-manager.md`）；若四種工具皆為自動工具，下拉以停用的提示選項顯示。

### 自動工具

- **Button**：`⚙️ 自動工具`（Blue，custom_id: `open_auto_tool`）；點擊開啟自動工具子介面。

### 其他

無額外按鈕。

## 自動工具子介面 Embed（build_auto_tool_embed / build_auto_tool_components）

Embed 顯示標題、運行中自動工具清單（`{工具}：到期 <t:{unix}:R>`，建設附目標建築）、以及規則說明（每 1 素材 1 小時、上限 `AUTO_TOOL_MAX_MATERIALS` 小時）。無運行中工具時顯示「目前沒有運行中的自動工具」。

元件：
- **Dropdown**（`auto_tool_type_select`）：可操作工具（閒置＝啟動、運行中＝補充；排除手動行動的工具）。皆無可用工具時以停用提示選項顯示。
- **Dropdown**（`auto_tool_target_select:{tool}`，僅選「建設」後出現）：建設目標（採集場/加工廠/狩獵場）。
- **Dropdown**（`auto_tool_count_select:{tool}:{target|none}`，選定工具後出現）：素材數量 `1..max_add`；`max_add == 0`（已達 6h 上限）時以停用提示選項顯示。
- **Button**：`✅ 確認`（Green，custom_id: `auto_tool_confirm:{tool}:{count}:{target|none}`）；未選齊或超上限時 disabled。
- **Button**：`← 返回`（Gray，custom_id: `back_to_main`）。

`max_add = floor((上限秒 − 剩餘秒) / 每素材秒)`；剩餘時間依 `expires_at − now` 計，詳見 `managers/auto-tool-manager.md`。

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
持有素材：{material_count} 個 ｜ 🌟 萬能素材：{universal_material_count} 個
⚡ AP：{ap} / {ap_cap}
工具等級上限：Lv{cap}（研究所 Lv{n}）
```

若該類型素材不足消耗量，強化時自動用萬能素材補足差額（不足以補足時強化按鈕維持 disabled）；UI 不另外顯示扣除細節，僅顯示兩者持有量。

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
- 標準：`正常強化：消耗全額素材，成功升級，失敗保底+1`
- 墊檔：`消耗一半素材，直接獲得一個保底計數，不進行強化`
- 鐵齒：`僅消耗 1 個素材，成功 +1~+3（50/35/15%），失敗則工具等級與 pity 均歸零`

初始狀態：介面開啟時，工具類型 Dropdown 與強化模式 Dropdown 均不預設選中任何選項；
三個按鈕（🎲 強化工具、🩸 獻祭素材、🔮 詞條管理）在工具類型未選定前均 disabled。

- **Button**：`🎲 強化工具`（Green，禁用條件：素材不足 / AP 不足 / 已達上限）
- **Button**：`🩸 獻祭素材`（Red，禁用條件：所選工具類型素材 == 0）；custom_id: `sacrifice_material:{gear_type}`；與 🎲 強化工具、← 返回 **同一 ActionRow**，不佔新列
- **Button**：`← 返回`（Gray）

### 詞條管理入口

- **Button**：`🔮 詞條管理`（Blue，custom_id: `open_affix_mgmt:{gear_type}`，禁用條件：`max_slots == 0`）；位於工具強化子選單與 `🎲 強化工具` / `🩸 獻祭素材` / `← 返回` 同一列
- 點擊後切到獨立的詞條管理畫面；開啟時工具類型 Dropdown（`affix_gear_select`）不預設選中任何選項

### 詞條管理畫面

選定工具類型後，Embed 標題下方顯示持有素材列，格式與工具強化子選單一致：`持有素材：{該類型素材} 個 ｜ 🌟 萬能素材：{materials_universal} 個`（工具類型未選定時不顯示）。

- **Dropdown**：工具類型（custom_id: `affix_gear_select`）
  - 選項描述沿用工具強化畫面的等級/效率預覽
- **Dropdown**：詞條槽選擇（custom_id: `affix_slot_select:{gear_type}`；僅有現存詞條時出現）
  - 選項格式：`槽 {n}: {詞條類型}`
  - 選項描述：`{±value}%`
- **Button**：`🗑️ 清除詞條`（Red，custom_id: `affix_clear:{gear_type}:{slot_index}`，禁用條件：尚未選定槽位）
- **Button**：`✨ 抽取詞條`（Blue，custom_id: `affix_extract:{gear_type}`，禁用條件：詞條槽已滿）
- **Button**：`← 返回`（Gray，custom_id: `back_to_gear:{gear_type}`）

抽取/清除的素材消耗若該類型素材不足，自動用萬能素材補足差額（兩者相加仍不足時執行才報錯），比照工具強化子選單；按鈕 disabled 條件不含素材是否足夠的判斷。

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
  | 素材數量 | `採集 {materials_gathering} ｜ 建設 {materials_building} ｜ 戰鬥 {materials_combat} ｜ 研究 {materials_research} ｜ 萬能 {materials_universal}` |
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

- 2026-07-17: Added `⚙️ 自動工具` main-interface button and the auto-tool sub-interface (`build_auto_tool_embed` / `build_auto_tool_components`); the action dropdown now excludes tools running as auto-tools. See `managers/auto-tool-manager.md`.
- 2026-07-17: 詞條管理畫面選定工具類型後，Embed 新增持有素材列（該類型素材 + 🌟 萬能素材），格式比照工具強化子選單；`build_affix_embed` 新增 `materials`/`universal_materials` 參數。
- 2026-07-17: 詞條操作段落補充：抽取/清除素材不足時自動用萬能素材補足差額（比照工具強化子選單），按鈕 disabled 條件不含素材判斷。
- 2026-07-15: The 4-state `🏆 試煉` display (previously Dashboard-only, see below) now also applies to the `/idlevillage` main interface's village section, since both reuse the same `_build_village_section`/`_build_trial_line` with no distinguishing parameter. Removed the `show_trial_status_line` toggle that had scoped the new states to the Dashboard only.
- 2026-07-15: Dashboard `🏆 試煉` line is now always shown instead of being omitted while no trial is active. Content switches between 4 states: active (unchanged progress format), cooldown (`⏳ 可於 <t:{cooldown_deadline}:t> 後開啟`, fixed time via Discord's `:t` style, not relative), insufficient resources (`⚠️ 資源不足，尚無法開啟`), and openable (`✅ 可開啟試煉`).
- 2026-07-14: `open_trial_start` no longer opens a Modal. Clicking it directly starts a trial with a fixed `TRIAL_TARGET_AMOUNT` and a system-chosen resource (uniformly random among affordable types) — zero player input. `build_main_components` now also takes `resources` to additionally disable the button when no resource type can afford `TRIAL_TARGET_AMOUNT`.
- 2026-07-14: Replaced the trial-opening slash command with an `open_trial_start` button (Row 1, alongside burst/gear upgrade) + `modal_start_trial` Modal (free-text resource + target). Button disabled unless a trial can currently be started. Removed resource type from the Dashboard trial progress line (was `🏆 試煉 {resource_emoji}{resource_label} {progress} / {target}`, now `🏆 試煉 {progress} / {target}`) to avoid implying the goal is a single-resource collection target. `build_main_embed` gained an optional `trial_message` line for post-submission feedback.
- 2026-07-14: Added village trial (🏆) display: village section gains a trial progress line (shown only while a trial is active); 個人資訊 gains a 試煉貢獻 line (shown only while a trial is active).
- 2026-07-14: Added universal material (🌟) display: 個人資訊 素材 line appends universal material count; gear upgrade sub-menu 持有素材 line shows universal material holdings alongside the type-specific count; `/idlevillage-manager` 素材數量 field appends `萬能 {materials_universal}`.
- 2026-07-14: Removed offering action — action dropdown option, `offering_resource_select` dropdown, 🎁 奉獻進度 dashboard line, villager action display names, and action emoji entry.
- 2026-06-07: Removed AP requirement to open gear upgrade interface; unified gear action button labels to `{icon}+四字` format (`🎲 強化工具`, `🩸 獻祭素材`, `✨ 抽取詞條`, `🗑️ 清除詞條`); replaced per-slot clear buttons with single `🗑️ 清除詞條` button + `clear_affix_select:{gear_type}` StringSelect dropdown flow.
- 2026-05-31: Added 🩸 獻祭 button (Red/Danger) to the gear upgrade action row alongside 🎲 強化 and ← 返回; disabled when the selected gear type's material count is 0. Sacrifice result appended to embed description when `result["type"] == "sacrifice"`, showing consumed count and incremental risky bonus. Error result branch also added.
- 2026.05.02.00: Stage line format changed to `📋 關卡 {n}: {type_zh}`; deadline prefixed with `期限:`; section headers localised to `公用資源` / `公用設施` / `村民行動` / `個人資訊`; building list moved out of code block with per-row emoji; gear line label changed to `裝備`, category text labels and `Lv` prefix removed; materials line category text labels removed; burst button renamed `⚡ 消耗AP立刻完成三次行動` and moved to Row 1 alongside `🔨 強化裝備`; Refresh button removed.
- 2026.05.02.02: Action dropdown options now include descriptions showing secondary cost and output per action type. Gear type dropdown options now include descriptions showing the level transition and cumulative stat gain (`Lv{n} → Lv{n+1}: {type}產出 +{n×pct}% → +{(n+1)×pct}%`), or `已達等級上限 Lv{cap}` when at cap.
- 2026.05.02.03: Removed incorrect special-case rule "若建築已達 level cap，顯示 100%". 100% is reached naturally when `xp_progress` reaches `next_req`; no display override is needed or correct.
- 2026.05.04.00: Added 📊 效率 as line 1 of 個人資訊, before 裝備. Displays `{output}(+{pct}%)` per action type using the formula in engine/formula.md.
- 2026-05-23: Added offering action to action dropdown (5th option); added offering_resource_select dropdown; added 🎁 奉獻進度 line to village section; updated villager action display names for offering.
- 2026.05.06.01: Official user-facing gear naming changed to tools:
  dashboard line `🏅 工具`, button `🔨 強化工具`, and full names
  採集工具, 建設工具, 狩獵工具, 研究工具.
- 2026.05.15: Risky mode now shows `鐵齒等級: {n} (+{pct}%)` line. Risky dropdown description updated to reflect multi-level success.
- 2026.05.16: Success rate line format updated to `成功率：{base}%（+保底{pity_total}% +鐵齒{risky}%）= {final}%`. Two detail lines added below (保底率、鐵齒率) for normal/risky modes. Bottom `鐵齒等級` line removed.
- 2026-05-31: Risky mode upgrade dropdown description updated to include multi-level success info: `成功 +1~+3（50/35/15%）`.
- 2026.05.15: Added mode selection dropdown (`upgrade_mode_select:{gear_type}`) to the gear upgrade sub-menu. Mode descriptions shown inline. Buffer mode displays 0% success rate.
- 2026-05-15: Added `build_manager_embed()` and `build_manager_components()` for the unified manager interface.
- 2026.05.06.00: Gear upgrade success-rate display must match gear-manager precision semantics. Lv6 with no pity displays 40%, not 39%.
- 2026-06-23: Added `build_ranking_text(sliced_rankings, name_map)` — formats per-tool-type ranking as plain text. Gear type order: gathering → building → combat → research; uses `ACTION_EMOJIS` for emoji and `GEAR_LABELS` for tool names. Each section: `{emoji}{GEAR_LABELS[type]}:\n- Lv{n}: {name}\n...`; `- （尚無玩家）` when no entries.

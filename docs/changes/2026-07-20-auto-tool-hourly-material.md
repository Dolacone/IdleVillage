---
title: "自動工具改版：隨用隨扣素材與可調剩餘時間"
status: Reviewed
created: 2026-07-20
doc_type: change
last_reviewed: 2026-07-20
source_paths:
  - src/managers/auto_tool_manager.py
  - src/core/settlement.py
  - src/core/engine.py
  - src/core/config.py
  - src/cogs/ui_renderer.py
  - src/cogs/actions.py
  - src/database/schema.py
  - .env.example
  - tests/support.py
  - tests/test_auto_tool_manager.py
  - tests/test_engine_settlement.py
  - tests/test_discord_commands.py
  - tests/test_v2_schema_initialization.py
  - tests/test_v2_config_validation.py
  - docs/managers/auto-tool-manager.md
  - docs/db-schema.md
  - docs/engine/cycle-engine.md
  - docs/engine/formula.md
  - docs/discord/ui-renderer.md
  - docs/discord/command-handler.md
scope: "Tracks the auto-tool revamp: material is spent hourly (pay-as-you-go) instead of prepaid, remaining time is player-set and adjustable, and the cap rises from 6h to 24h."
---

## Problem Statement

現有自動工具（見 `docs/managers/auto-tool-manager.md`）採「預付」模型：啟動時一次扣 1~6 個該工具素材，素材數 = 運行時數，`expires_at = now + count×1h`，上限 6h。缺點：玩家必須一次押上全部素材，無法途中調整運行時間，且上限偏低。

需求把資源模型改為「隨用隨扣」：

- 最長運行時間由 6h 提高到 24h。
- 啟動時不再一次預扣全部素材；改為每 1 小時扣 1 個該工具素材。
- 某個小時要扣素材時手上沒有該素材 → 自動中斷、釋放工具。
- 玩家可隨時增加或減少剩餘時間（以 1 小時為單位），上限 24h；減到底即停止。

## Recommended Direction

方向 A（採用）：延伸現有 auto-tool 子系統，改為雙時鐘。

- 保留 `expires_at` 語意為「工具停止時間」，但改為玩家自訂、與素材脫鉤（加/減時間只改 `expires_at`，不碰素材）。
- 新增獨立的「素材扣除時鐘」欄位 `next_material_time`：下次扣素材時間，序列為 `started_at + N × SECONDS_PER_MATERIAL`（N=0,1,2...），即 t=0 啟動瞬間扣第一個。
- `start` 不再預扣全部，只在 t=0 扣第一個素材（並要求手上 ≥ 1）。
- `refuel` 拆為「加時間」與「減時間」兩路，純調 `expires_at`；減到 remaining ≤ 0 即 `end`。
- 結算時 auto-tool 掃描除了推進產出週期，也在 `next_material_time <= now` 時扣 1 素材；扣不到 → `end`。產出週期與素材 tick 為兩條獨立時鐘，於結算時依時間先後交錯處理（見架構決策，plan 階段補完）。

理由：與現有 auto-tool 子系統、cycle-engine 掃描流程、`BEGIN IMMEDIATE` 序列化與固定結算順序（原架構決策 #7/#8）一致，不動產出週期模型，變更面可控。

### 排除的替代方案

- 方向 B：把素材扣除綁進產出週期（每個產出週期扣素材）。否決：產出週期 `effective_cycle_seconds` 可遠短於 1h，且受 `cycle_time_reduce` 影響會漂移，與「每小時扣一個」不符。
- 方向 C：用單一 `completion_time` 同時當產出與素材時鐘（把週期設成 1h）。否決：破壞既有 `effective_cycle_seconds` 產出模型，牽動全域，違反最小變更。

## Clarifications

<!-- Q: 調整剩餘時間（加/減）是否涉及素材扣除或退還？ / A: 完全不涉及素材；素材只在每小時 tick 扣。加/減只改 expires_at。 -->
<!-- Q: 第一次扣素材時機、啟動是否需要素材門檻？ / A: 啟動瞬間即開始計時，計時瞬間扣第一次素材（實質 = 啟動即扣 1）；start 檢查手上 ≥ 1 素材才可啟動。 -->
<!-- Q: 每小時素材 tick 的時鐘如何計算？ / A: 從 started_at 起算每 SECONDS_PER_MATERIAL(1h) 一次，t=0 起。與產出結算週期為獨立雙時鐘。 -->
<!-- Q: 如何停止？素材耗盡/主動停止時進行中半週期怎麼處理？ / A: 減時間到底即停，不設獨立停止鈕；素材耗盡自動中斷。進行中未完成的產出週期一律丟棄，不做 partial。 -->

## MVP Scope / Not Doing

範圍內：
- `player_auto_tools` 新增 `next_material_time` 欄位（素材扣除時鐘）。
- `auto_tool_manager`：`start` 改為 t=0 扣 1（要求 ≥1）、設 `expires_at = now + hours×per`、設 `next_material_time = started_at + per`；`refuel` 拆為加/減時間（只調 `expires_at`）；新增/調整 `max_add`（上限 24h）與減時間邊界計算；素材 tick 扣除與耗盡 `end`。
- `settlement`：auto-tool 結算改為依時間先後交錯處理「產出週期」與「素材 tick」，素材 tick 扣不到即 `end`（進行中週期丟棄）。
- `config`：`AUTO_TOOL_MAX_MATERIALS`（6）語意/命名調整為「上限小時數」= 24（命名是否改為 `AUTO_TOOL_MAX_HOURS` 於 plan 決定）。
- UI：start 子介面由「選素材數 1~6」改為「選初始運行時數 1~24」；運行中列顯示剩餘到期 + 手上素材可撐時數；加時間 / 減時間下拉。
- 文件更新：`auto-tool-manager.md`、`db-schema.md`、`cycle-engine.md`、`formula.md`（env）、`ui-renderer.md`、`command-handler.md`。

範圍外：
- 不改互斥（雙向）、`BEGIN IMMEDIATE` 序列化、固定結算順序等既有架構決策的核心邏輯（沿用）。
- 不改產出週期 / `effective_cycle_seconds` / action-resolver 產出模型。
- 不新增公開通知類型；中斷不做 partial 半週期。
- 萬能素材仍不可替代（沿用）。

## Architecture Decisions

1. 雙時鐘欄位。`player_auto_tools` 新增 `next_material_time TEXT`（nullable）：下次扣素材的時間點。序列為 `started_at + N × per`（N=1,2...），第一個素材已在 `start`（t=0）扣掉。沿用既有 `_migrate_v2_columns` 冪等模式：`CREATE TABLE` 定義加此欄（nullable，因 TEXT 時間戳無合理 NOT NULL 預設），並以 `PRAGMA table_info(player_auto_tools)` 檢查後 `ALTER TABLE ... ADD COLUMN next_material_time TEXT`。

   舊列遷移語意（不重扣）：既有預付制的運行中 auto-tool 列，其剩餘時數（至 `expires_at`）在舊模型已一次付清素材。因此結算時遇 `next_material_time` 為 NULL 的舊列，回填為該列的 `expires_at`（非 `started_at + per`）——素材 tick 有效條件為 `next_material_time < expires_at`（決策 #5），回填成 `expires_at` 使其永不觸發，該列以已付時數平安跑到到期為止，絕不二次扣素材、絕不因素材不足提早結束。新列一律由 `start` 寫入正確的 `now + per`，不受此回填影響。

2. `start` 語意改變。參數 `count` 改為「初始運行時數 hours」（非素材數）：驗證 `1 <= hours <= MAX_HOURS(24)`；要求手上該素材 ≥ 1 並只扣 1（t=0，沿用 `_spend_own_material(count=1)`）；`expires_at = now + hours × per`；`next_material_time = now + per`；`completion_time` 不變。條件式 INSERT 需一併寫入 `next_material_time`。互斥/`BEGIN IMMEDIATE` 序列化沿用不變。

3. `refuel` 拆為兩個純調時間函式（皆不碰素材、皆 `BEGIN IMMEDIATE` 重讀後寫入，沿用決策 #7）：
   - `add_time(db, user_id, tool_type, hours, now)`：驗證 `1 <= hours <= max_add_hours(expires_at, now)`；`expires_at += hours × per`。
   - `subtract_time(db, user_id, tool_type, hours, now)`：驗證 `hours >= 1`；重讀 `remaining = expires_at − now`；若 `hours × per >= remaining` → `end()`（停止工具，減到底即停）；否則 `expires_at −= hours × per`。
   移除 `refuel`（orphan cleanup）。`max_add_materials` 更名 `max_add_hours`（數學不變，cap 改 `MAX_HOURS × per`）；新增 `max_subtract_hours(expires_at, now) = ceil(remaining / per)`（最大的那一階即停）。

4. env 更名。`AUTO_TOOL_MAX_MATERIALS`（6）→ `AUTO_TOOL_MAX_HOURS`（24），語意由「上限素材數」轉為「上限剩餘小時數」。`AUTO_TOOL_SECONDS_PER_MATERIAL`（3600）保留（1 素材仍換 1 小時運行）。同步四處：`config.REQUIRED_KEYS`、`.env.example`、`tests/support.ALL_TEST_ENV`、`tests/test_v2_config_validation.py`；manager 內 `_max_materials()` → `_max_hours()`。

5. `settle_auto_tool_cycles` 改為雙時鐘時間序合併結算。產出週期時鐘（`completion_time`，步進 `effective_cycle_seconds`）與素材 tick 時鐘（`next_material_time`，步進 `per`）依時間先後交錯處理：
   - 產出週期有效條件：`completion_time <= min(now, expires_at)`（同現行）。
   - 素材 tick 有效條件：`next_material_time <= now` 且 `next_material_time < expires_at`（嚴格小於到期，避免在到期整點多扣一個不會運行的小時）。
   - 每輪取「最早的有效事件」處理；平手（同時刻）時素材 tick 先（該小時素材先付、供該小時產出使用）。
   - 產出週期受 `MAX_CYCLES_PER_SETTLEMENT` 限制：當最早事件是產出週期但已達 cap → break（留 backlog 給下次 sweep，不得越過未結算的產出去先扣後續素材，維持時間序正確）。
   - 素材 tick 以條件式 UPDATE（`WHERE 該素材 >= 1`）扣 1；`rowcount == 0`（扣不到）→ `end()` 立即停止並跳出（進行中未完成週期丟棄，不做 partial）。
   - 正回饋沿用：某產出週期若在素材 tick 之前完成並掉落該工具素材，因同交易內串行處理，可供緊接著的素材 tick 使用。
   - 收尾 `end` 條件（沿用並延伸）：未因扣不到素材而停止時，`caught_up = (completion_time > min(now,expires_at)) 且 (無有效素材 tick 待處理)`；`now >= expires_at 且 caught_up` 才 `end`。cap 命中留 backlog 時不 `end`。
   - 舊列（`next_material_time` NULL）依決策 #1 回填為該列 `expires_at`（視為已預付、素材 tick 不觸發）。
   - 新增 manager 寫入輔助 `advance_material_tick(db, user_id, tool_type, next_material_time)`（更新 `next_material_time` + `updated_at`），維持 table 寫入封裝於 manager（SSOT）。

6. Watcher 掃描條件擴充（`engine.py` 改）。原掃描僅 `player_auto_tools.completion_time <= now`，只看產出時鐘；因 `effective_cycle_seconds` 僅保證 ≥ 60s、不保證 ≤ 1h（`ACTION_CYCLE_MINUTES` 可設 > 60），素材時鐘可能密於產出時鐘，且到期（`expires_at`）本身不在觸發條件內，會造成已到期/已耗盡素材的工具在背景 stale-occupancy 佔住工具槽，直到下次 `completion_time` 到或玩家開介面才釋放。因此掃描條件改為 `completion_time <= ? OR next_material_time <= ? OR expires_at <= ?`（`ORDER BY user_id, tool_type` 沿用），確保素材 tick 與到期在背景也能及時觸發結算與 `end`。`player_auto_tools` 列數小（每玩家至多數列），OR 條件全表掃描成本可忽略，不新增索引。

7. UI 以有號 delta 統一。`start`/`add`/`subtract` 共用一個確認 custom_id 帶有號整數 delta：`auto_tool_confirm:{tool}:{delta}:{target|none}`。閒置工具選取 → 單一「初始運行時數」下拉（+1..+MAX_HOURS，delta 正）；運行中工具選取 → 兩個下拉「加時間」（+1..+max_add_hours）與「減時間」（−1..−max_subtract_hours，最大階即停止），避免單一下拉超過 Discord 25 選項上限。confirm 路由：工具未運行 → `start(hours=delta)`；運行中 → `delta>0` 呼叫 `add_time`、`delta<0` 呼叫 `subtract_time`。ActionRow 數：建設啟動 = 工具+目標+時數+按鈕(4)；運行中調整 = 工具+加+減+按鈕(4)，均 ≤5。

## Key Assumptions

- 「每小時扣素材」的「小時」= `SECONDS_PER_MATERIAL`（預設 3600），與產出週期無關；沿用同一常數。
- 素材扣除與產出週期於結算時依時間先後交錯：某產出週期若在素材 tick 之前完成並掉落該工具素材，可用於支付緊接著的素材 tick（正回饋，沿用既有「素材掉落可延長」為預期行為）。
- 素材耗盡或減時間到底而停止時，`now >= 停止時間` 才 `end`；進行中未完成的產出週期一律丟棄，不做 partial（比照現有到期行為）。
- start 需手上 ≥ 1 素材，t=0 扣掉它；`next_material_time` 起始為 `started_at + per`。
- 加/減時間以 1 小時為單位；加時間上限使 `remaining ≤ 24h`；減時間使 `remaining ≤ 0` 時即停止工具。

## Tasks

依賴圖：
```
T1 schema ─┐
T2 env  ───┴─→ T3 auto_tool_manager ─→ T4 settlement ─→ T6 cog ─→ T7 docs
                     └────────────────→ T5 ui ──────────┘
```
T1／T2 互相獨立可並行。T3 依賴 T1（欄位）＋T2（env）。T4 依賴 T1、T3。T5 依賴 T3。T6 依賴 T4、T5。T7 依賴全部。

- [x] Task 1: schema — `player_auto_tools.next_material_time` 欄位 + 冪等遷移 [可與 T2 並行]
  - Files: `src/database/schema.py`
  - Tests: `tests/test_v2_schema_initialization.py` — 新表建立含 `next_material_time`；既有 DB 經 `_migrate_v2_columns` 補欄（`PRAGMA table_info` 檢查後 ALTER）；重複呼叫 `init_db()` 冪等
  - Depends on: 無
  - Acceptance: `CREATE TABLE player_auto_tools` 定義新增 `next_material_time TEXT`（nullable）；`_migrate_v2_columns` 對 `player_auto_tools` 加 `PRAGMA table_info` 檢查，缺欄則 `ALTER TABLE player_auto_tools ADD COLUMN next_material_time TEXT`；既有 schema 測試全通過

- [x] Task 2: env 更名 — `AUTO_TOOL_MAX_MATERIALS` → `AUTO_TOOL_MAX_HOURS=24` [可與 T1 並行]
  - Files: `src/core/config.py`, `.env.example`
  - Tests: `tests/support.py`（`ALL_TEST_ENV`）改 key、`tests/test_v2_config_validation.py` 改涵蓋的 key
  - Depends on: 無
  - Acceptance: `REQUIRED_KEYS` 以 `AUTO_TOOL_MAX_HOURS` 取代 `AUTO_TOOL_MAX_MATERIALS`；`.env.example` 改為 `AUTO_TOOL_MAX_HOURS=24`（保留 `AUTO_TOOL_SECONDS_PER_MATERIAL=3600`）；`tests/support.py` 與 config 驗證測試同步；既有 config 測試全通過

- [x] Task 3: auto_tool_manager — start 改時數/扣 1、add_time/subtract_time、max_add_hours/max_subtract_hours、advance_material_tick、移除 refuel
  - Files: `src/managers/auto_tool_manager.py`
  - Tests: `tests/test_auto_tool_manager.py` — start（要求 ≥1 素材、只扣 1、`expires_at=now+hours×per`、`next_material_time=now+per`、`hours` 出界 raise）、素材為 0 raise、互斥雙向沿用；`add_time`（`1..max_add_hours`、上限 24h、不扣素材）；`subtract_time`（減不到底 → 縮短、減到底/超過 → `end`、不扣素材、不退素材）；`max_add_hours`（cap 24h：剩餘 23:01→0、剩餘 0:01→23）、`max_subtract_hours`（剩餘 01:01→2）；`advance_material_tick` 寫入
  - Depends on: T1, T2
  - Acceptance: 依架構決策 #2/#3；`_max_hours()` 取 `AUTO_TOOL_MAX_HOURS`；`start(count→hours)` 只扣 1 素材、寫 `next_material_time`；新增 `add_time`/`subtract_time`（皆 `BEGIN IMMEDIATE` 重讀後寫、try/except rollback）、`max_add_hours`/`max_subtract_hours`/`advance_material_tick`；移除 `refuel` 與 `max_add_materials`（更名）；不 import `core.settlement`

- [x] Task 4: settlement + engine — settle_auto_tool_cycles 雙時鐘時間序合併結算 + 素材 tick + 舊列遷移；Watcher 掃描條件擴充
  - Files: `src/core/settlement.py`, `src/core/engine.py`
  - Tests: `tests/test_engine_settlement.py` — 素材 tick 每小時扣 1；扣不到即 `end`（進行中週期丟棄）；產出週期與素材 tick 依時間先後交錯（平手素材先）；正回饋（產出掉素材可供緊接 tick）；cap 命中留 backlog 不越過未結算產出去扣素材、不 `end`；`next_material_time` 為 NULL 的舊列回填為 `expires_at`（視為已預付、不再扣、不提早結束）；到期整點不多扣（`next<expires` 嚴格）；到期 + caught_up 才 `end`；並發 `add_time`/`subtract_time` 調整後 settle 不誤刪（沿用 `BEGIN IMMEDIATE`）；Watcher 以 `next_material_time <= now` 或 `expires_at <= now` 觸發背景結算/`end`。注意：既有 `test_engine_settlement.py` 內 raw `INSERT INTO player_auto_tools (...)` helper（約 L1298）需一併補 `next_material_time` 欄位，否則既有測試機械性失敗
  - Depends on: T1, T3
  - Acceptance: 依架構決策 #5 重寫合併迴圈；素材 tick 有效條件 `next_material_time <= now and < expires_at`；扣 1 用條件式 UPDATE，`rowcount==0` → `end` 並跳出；`end` 收尾條件延伸為含「無待處理素材 tick」；舊列 `next_material_time` NULL 回填 `expires_at`（決策 #1）；`engine.py` auto-tool 掃描條件改為 `completion_time <= ? OR next_material_time <= ? OR expires_at <= ?`（`ORDER BY user_id, tool_type` 沿用，決策 #6）

- [x] Task 5: ui_renderer — 啟動選時數、運行中加/減時間下拉、embed 顯示素材可撐時數
  - Files: `src/cogs/ui_renderer.py`
  - Tests: `tests/test_discord_commands.py` — 閒置工具：單一「初始運行時數」下拉 1..MAX_HOURS，delta 正；運行中工具：兩下拉「加時間」1..max_add_hours 與「減時間」1..max_subtract_hours（最大階標示停止）；confirm custom_id `auto_tool_confirm:{tool}:{delta}:{target|none}`；embed 顯示各運行工具剩餘到期 + 手上該素材可撐時數；上限文案改 24 小時
  - Depends on: T3
  - Acceptance: 依架構決策 #7；`build_auto_tool_components` 參數改以 `selected_delta`、`max_add`、`max_subtract` 驅動；`build_auto_tool_embed` 顯示素材可撐時數（傳入 materials）；ActionRow ≤ 5；既有 UI 測試調整後全通過

- [x] Task 6: actions cog — confirm delta 路由 + 開介面補算沿用
  - Files: `src/cogs/actions.py`
  - Tests: `tests/test_discord_commands.py` — `auto_tool_confirm:{tool}:{delta}:{target}` 解析有號 delta；未運行 → `start(hours=delta)`、運行中 `delta>0` → `add_time`、`delta<0` → `subtract_time`；失敗顯示統一錯誤且不改狀態；`_render_auto_tool` 傳 `max_add`/`max_subtract`/materials；`_render_main` 開介面補算沿用
  - Depends on: T4, T5
  - Acceptance: `auto_tool_confirm` 解析 delta（含負值）並路由至 start/add_time/subtract_time；`_render_auto_tool` 依選取工具是否運行計算 `max_add_hours`/`max_subtract_hours` 並傳入；`_render_auto_tool` 內 `get_env_int("AUTO_TOOL_MAX_MATERIALS")`（約 L286）改讀 `AUTO_TOOL_MAX_HOURS`（決策 #4 的 caller，勿遺漏）；own-interaction 與 guild 驗證沿用；既有 cog 測試調整後全通過

- [x] Task 7: 文件更新
  - Files: `docs/managers/auto-tool-manager.md`, `docs/db-schema.md`, `docs/engine/cycle-engine.md`, `docs/engine/formula.md`, `docs/discord/ui-renderer.md`, `docs/discord/command-handler.md`
  - Tests: 無（純文件）
  - Depends on: T1–T6
  - Acceptance: `auto-tool-manager.md` 改寫為隨用隨扣模型（`next_material_time`、start 扣 1、add/subtract_time、雙時鐘合併結算、素材耗盡中斷、24h 上限、env 更名）；`db-schema.md` 新增欄位；`cycle-engine.md` 更新自動工具結算段（雙時鐘、素材 tick、Watcher 觸發不變）；`formula.md` env 表更名；`ui-renderer.md`／`command-handler.md` 反映新 UI/路由；所有改動文件 `last_reviewed` 更新為 2026-07-20

## Review Issues

codex-reviewer（背景 codex exec，唯讀 diff 審查）；完整測試套件 `uv run python -m pytest -q` 568 passed, 3 subtests passed。

- [x] [Minor] `source_paths` 未涵蓋 `src/core/engine.py`（T4 改了 Watcher 掃描條件，屬架構決策 #6）。→ 已補入 frontmatter `source_paths`。

無 Critical/Major。狀態設為 Reviewed。

## Plan Review Issues
- [x] [Critical] 舊的運行中 auto-tool 無安全遷移策略：回填 `started_at + per` 會對已預付時數重扣素材、甚至提早 `end`。→ 決策 #1 改為：舊列（`next_material_time` NULL）回填為該列 `expires_at`；因素材 tick 條件為 `next_material_time < expires_at`，回填成 `expires_at` 使其永不觸發，舊列以已付時數跑到到期、絕不二次扣素材。Task 4 測試同步。
- [x] [Medium] Decision #6「Watcher 不改也夠」推理不嚴謹（`effective_cycle_seconds` 不保證 ≤1h，到期不在觸發條件內 → 背景 stale-occupancy）。→ 決策 #6 改為擴充 Watcher 掃描條件為 `completion_time <= ? OR next_material_time <= ? OR expires_at <= ?`；`engine.py` 納入 Task 4 檔案清單。
- [x] [Low] rename/remove 影響面不完整：(a) Task 4 測試描述改為 `add_time`/`subtract_time`；(b) Task 6 acceptance 補列 `src/cogs/actions.py` L286 讀 `AUTO_TOOL_MAX_MATERIALS` 的 caller 改為 `AUTO_TOOL_MAX_HOURS`；(c) Task 4 測試明列 `tests/test_engine_settlement.py` 的 raw `INSERT INTO player_auto_tools` helper 需補 `next_material_time`。

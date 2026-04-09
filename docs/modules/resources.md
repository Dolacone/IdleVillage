# Module: Resources and Exploration

定義資源獲取、探索機制以及行動週期 (Action Cycle) 採集機制.

### 1. 閒置狀態 (Idle State)
- 觸發: 玩家狀態為 `idle`.
- 消耗: 無 (不消耗村莊資源).
- 品質 (Quality): 固定為 50%.
- 產出公式: `int(50 * Stats_Eff * 0.5 * Building_Eff * Time_Ratio)`.
- 屬性掛鉤: 觀察 (PER) + 知識 (KNO).

### 2. 資源採集 (Gathering)
- 觸發: 玩家選擇一個有效資源節點並提交 `gather` 指令.
- 行動週期 (Action Cycle):
  - 啟動預扣: 週期開始時, 立即從村莊倉庫扣除糧食 (數量: `max(1, 10 - Food_Eff_Level)`).
  - 產出結算: 週期結束後計算產出並直接存入村莊倉庫.
- 產出公式: `int(50 * Stats_Eff * Quality_Eff * Building_Eff * Time_Ratio)`.
  - 基礎速率 (Base): 50 / 週期.
  - 素質係數 (Stats_Eff): `(屬性 A + 屬性 B) / 2 / 100`.
  - 品質係數 (Quality_Eff): `max(75, 節點品質) / 100`. (品質採百分比制, 例如 120 代表 120%)
  - 建築加成 (Building_Eff): `1.0 + (加工等級 * 0.1)`.
  - 時間占比 (Time_Ratio): `實際持續分鐘 / ACTION_CYCLE_MINUTES`.

### 3. 探索發現規則 (Exploring Discovery)
- 判定頻率: 每個行動週期 (Cycle) 結算時執行一次.
- 節點限制: 每個村莊每種資源類型 (Food, Wood, Stone) 僅存在一個永久節點.
- 成功機率: P(Found) = (PER + KNO) / 4 * 1%.
- 資源類型: 糧食、木材、石材機率均等 (1/3).
- 資源存量 (Stock): 
  - 發現量: random(min=(PER + KNO) * 5, max=(PER + KNO) * 10).
  - 最大上限 (Cap): 每個節點存量上限為 8,000.
  - 溢出處理: 累積後的存量若超過 8,000, 溢出部分將被捨棄, 僅保留至 8,000.
- 資源品質 (Quality): 
  - 生成公式: 高斯分佈, 平均值 (mu) 為玩家素質平均值, 標準差 (sigma) 為 50, 鉗制於 75.
  - 加權平均公式 (Weighted Average): New_Quality = floor((Old_Quality * Old_Stock + Found_Quality * Found_Stock) / (Old_Stock + Found_Stock)).
  - 比例調整: 即使存量已滿 (8,000), 發現新資源時仍需使用完整的 Found_Stock 進行品質加權計算, 以反映新資源對現有資源池品質的影響.
  - 備註: 若節點原先不存在 (或存量為 0), 則直接採用本次生成的品質.
- 發現通知: 不發送公告頻道訊息. 探索成果僅更新資料庫中的節點存量與品質, 並在後續 UI / 查詢中反映.

### 4. 平衡性參數 (Balance Numbers)
- 基礎產出速率: 50 / 週期 (Cycle).
- 有效期: 無 (Permanent until depleted).
- 存量為 0: 節點依然保留於資料庫, 但顯示為 Out of Stock 且無法執行 gather 行動.
- 採集者處理 (Depletion Behavior):
  - 結算判定: 當玩家執行結算時, 若目標節點存量已為 0, 該次行動產出為 0, 且玩家狀態強制轉變為 idle.
  - 部分產出: 若目標節點存量小於玩家應得產出, 玩家僅獲得當前剩餘存量, 隨後節點轉為 Out of Stock, 玩家狀態轉變為 idle.
  - 狀態轉變通知: 當玩家因資源耗盡而被迫轉為 idle 時, 系統應發送通知並標註該玩家.

## Changelog
- 2026.04.07.00: Implemented 1-hour cycle gathering and exploring. - See [2026.04.07.00.md](../changelogs/2026.04.07.00.md)
- 2026.04.08.00: Updated to Cycle-based logic, Gaussian discovery quality, and refined stock formulas. - See [2026.04.08.00.md](../changelogs/2026.04.08.00.md)
- 2026.04.08.02: Increased base output from 20 to 50. - See [2026.04.08.02.md](../changelogs/2026.04.08.02.md)
- 2026.04.09.00: Switched to permanent singleton resource nodes with weighted average quality and stock accumulation. - See [2026.04.09.00.md](../changelogs/2026.04.09.00.md)

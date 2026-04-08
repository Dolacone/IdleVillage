# Module: Resources and Exploration

定義資源獲取、探索機制以及行動週期 (Action Cycle) 採集機制.

### 1. 閒置狀態 (Idle State)
- 觸發: 玩家狀態為 `idle`.
- 消耗: 無 (不消耗村莊資源).
- 品質 (Quality): 固定為 50%.
- 產出公式: `int(20 * Stats_Eff * 0.5 * Building_Eff * Time_Ratio)`.
- 屬性掛鉤: 觀察 (PER) + 知識 (KNO).

### 2. 資源採集 (Gathering)
- 觸發: 玩家選擇一個有效資源節點並提交 `gather` 指令.
- 行動週期 (Action Cycle):
  - 啟動預扣: 週期開始時, 立即從村莊倉庫扣除糧食 (數量: `max(1, 10 - Food_Eff_Level)`).
  - 產出結算: 週期結束後計算產出並直接存入村莊倉庫.
- 產出公式: `int(20 * Stats_Eff * Quality_Eff * Building_Eff * Time_Ratio)`.
  - 基礎速率 (Base): 20 / 週期.
  - 素質係數 (Stats_Eff): `(屬性 A + 屬性 B) / 2 / 100`.
  - 品質係數 (Quality_Eff): `max(10, 節點品質) / 100`. (品質採百分比制, 例如 120 代表 120%)
  - 建築加成 (Building_Eff): `1.0 + (加工等級 * 0.1)`.
  - 時間占比 (Time_Ratio): `實際持續分鐘 / ACTION_CYCLE_MINUTES`.

### 3. 探索發現規則 (Exploring Discovery)
- 判定頻率: 每個行動週期 (Cycle) 結算時執行一次.
- 成功機率: $P(\text{Found}) = 1 / (1 + n^2)$.
  - $n$: 當前村莊存在的活躍資源節點數量.
- 資源類型: 糧食、木材、石材機率均等 (1/3).
- 資源節點資料結構: 僅需保存 `type`, `quality`, `remaining_amount`, `expiry_time`, 不再保存 `level`.
- 資源品質 (Quality): 
  - 依據玩家素質 `(PER + KNO) / 2` 進行高斯分佈 (Gaussian) 隨機生成.
  - 平均值 ($\mu$): 玩家素質平均值. (例如素質 100 則 $\mu=100$)
  - 標準差 ($\sigma$): 50.
  - 钳制處理 (Clamp): `max(10, Quality)`.
- 資源存量 (Stock): 
  - 公式: `random(min=(PER + KNO) * 10, max=(PER + KNO) * 20)`.
- 發現通知: 任何新發現的節點皆必須發送訊息至村莊公告頻道 (Village Announcement Channel).

### 4. 平衡性參數 (Balance Numbers)
- 基礎產出速率: 20 / 週期 (Cycle).
- 節點有效期: 發現後 48 小時.

## Changelog
- 2026.04.07.00: Implemented 1-hour cycle gathering and exploring. - See [2026.04.07.00.md](../changelogs/2026.04.07.00.md)
- 2026.04.08.00: Updated to Cycle-based logic, Gaussian discovery quality, and refined stock formulas. - See [2026.04.08.00.md](../changelogs/2026.04.08.00.md)

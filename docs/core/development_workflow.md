# Development Workflow & Changelog Standards

## 1. Versioning System (CalVer)
- Format: `YYYY.MM.DD.NN`
- `YYYY.MM.DD`: Current date (e.g., 2026.04.06)
- `NN`: Sequential number starting from `00` (e.g., `00`, `01`, `02`).
- A new version is defined whenever a Change Plan is created (start of a feature branch).

## 2. Change Plan & Lifecycle
Every significant change must follow this lifecycle.

### Phase 1: Planning
- File: `docs/changelogs/YYYY.MM.DD.NN.md`
- Initial Status: `Draft`
- Action: AI creates the file defining Objectives, Proposed Changes, Affected Files, and Verification Plan.
- Approval: User reviews and approves the plan.

### Phase 2: Implementation
- Status: `In-Progress`
- Action: AI implements changes in a feature branch (e.g., `feat/2026.04.06.00`).
- Commit: Every commit message must include the version, e.g., `[2026.04.06.00] feat: implement ...`.

### Phase 3: Finalization
- Action: AI updates all affected documents (see below).
- Status: `Done` only after all required tests pass and staging verification passes.
- Action: AI may prepare document updates and summaries before release, but should only update the Change Plan file status to `Done` after the post-test and post-staging gate is satisfied.
- Merge: Branch is ready for merging into `master`.

## 3. Document Synchronization
Every documentation file in `docs/` (except changelogs) MUST contain a `## Changelog` section at the end.
- Format: `- YYYY.MM.DD.NN: [Short summary of changes] - See [YYYY.MM.DD.NN.md](../changelogs/YYYY.MM.DD.NN.md)`
- AI is responsible for appending this entry to all modified docs before finalizing the Change Plan.

## 4. Change Plan Template
```markdown
# Change Plan & Changelog: YYYY.MM.DD.NN

- Status: [Draft | In-Progress | Done]

## 1. Objectives
- [Short description]

## 2. Proposed Changes
- [ ] Task 1
- [ ] Task 2

## 3. Affected Files
- `path/to/file.py`

## 4. Verification Plan
- [ ] Step 1
- [ ] Step 2

---

## 5. Changelog
<!-- Summary added when status is changed to Done -->
```

## 5. 偵錯與日誌規範 (Logging & Debugging)
為了追蹤非同步操作與複雜結算邏輯, 系統必須將日誌輸出至 `stdout`, 格式如下:
`[REQ_ID] [USER_ID/SYSTEM] {TYPE}: {MESSAGE}`
- **REQ_ID**: 每個 Slash Command 或 Watcher Task 的唯一 UUID.
- **USER_ID**: 觸發者的 Discord ID (系統任務則為 `SYSTEM`).
- **TYPE**: 日誌類別 (CMD, RESP, COST, SETTLE, STATUS, ERROR).
- **追蹤重點**:
  - 指令輸入與回傳結果 (CMD/RESP).
  - 資源扣除明細 (COST: food, wood, stone).
  - 行動結算產出 (SETTLE: xp_gained, resources_gained).
  - 狀態變更 (STATUS: from X to Y).

## 6. 開發者測試 (Developer Testing)
- **週期加速**: 測試期間建議設定 `ACTION_CYCLE_MINUTES=1` 並將 Watcher Heartbeat 設為 60s 以快速驗證邏輯.
- **SSOT 遵循**: 任何邏輯調整必須先反映在 `docs/` 文件中, 才能進入實作.
- **日誌對齊**: 測試時應優先檢視 `stdout` 以確認資源扣除與結算次數是否符合預期.

## Changelog
- 2026.04.06.00: Clarified and then finalized the workflow around the current flat `src/` service layout and required document synchronization. - See [2026.04.06.00.md](../changelogs/2026.04.06.00.md)
- 2026.04.07.00: Updated to reflect 1-hour lease model and stats recalculation logic. - See [2026.04.07.00.md](../changelogs/2026.04.07.00.md)
- 2026.04.08.00: Standardized structured logging format and added developer testing guidance. - See [2026.04.08.00.md](../changelogs/2026.04.08.00.md)

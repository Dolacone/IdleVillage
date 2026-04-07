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
- Commit: Every commit message must include the version, e.g., `feat: [2026.04.06.00] implement ...`.

### Phase 3: Finalization
- Action: AI updates all affected documents (see below).
- Status: `Done` only after all required tests pass and staging verification passes.
- Action: AI may prepare document updates and summaries before release, but should only update the Change Plan file status to `Done` after the post-test and post-staging gate is satisfied.
- Merge: Branch is ready for merging into `master`.

## 3. Document Synchronization
Every documentation file in `docs/` (except changelogs) MUST contain a `## Changelog` section at the end.
- Format: `- YYYY.MM.DD.NN: [Short summary of changes] - See [YYYY.MM.DD.NN.md](../../changelogs/YYYY.MM.DD.NN.md)`
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

## Changelog
- 2026.04.06.00: Clarified and then finalized the workflow around the current flat `src/` service layout and required document synchronization. See [2026.04.06.00.md](../../changelogs/2026.04.06.00.md)

- 2026.04.07.00: Updated to reflect 1-hour lease model and stats recalculation logic. See [2026.04.07.00.md](../../changelogs/2026.04.07.00.md)

---
title: "Gear Upgrade Modes: 墊檔 and 鐵齒"
status: Ready-to-implement
created: 2026-05-15
doc_type: change
last_reviewed: 2026-05-15
source_paths: []
scope: "Tracks this change from design through review."
---

## Problem Statement

How might we give players strategic control over risk/reward in gear upgrades, beyond the single default upgrade path?

## Recommended Direction

Add two optional upgrade modes selectable at upgrade time, alongside the existing 標準 (normal) mode:

**墊檔 (Buffer)**
- Cost: ceil(target_level / 2) materials + 1 AP
- Effect: no roll — pity (failure count) +1 immediately, gear level unchanged
- Use case: player wants to build up pity safely at half material cost

**鐵齒 (All-in)**
- Cost: 1 material + 1 AP
- Effect: normal roll at current rate; on failure pity resets to 0 (not +1)
- Use case: player bets on success with minimal material spend, but risks losing all accumulated pity

Both modes share the same preconditions as 標準 (gear < cap, AP >= 1, sufficient materials).

## Key Assumptions

- [ ] 墊檔 still costs 1 AP (to keep AP as the pace-limiter)
- [ ] 墊檔 material cost is ceil(target_level / 2), minimum 1
- [ ] 鐵齒 on success behaves identically to 標準 (gear +1, pity reset to 0)
- [ ] Both modes are accessible from the same upgrade UI/command
- [ ] Display label: 標準 / 墊檔 / 鐵齒; backend enum: normal / buffer / risky

## MVP Scope

- `gear_manager`: add `mode` parameter to `attempt_upgrade()` and `get_upgrade_info()` supporting `"normal"` / `"buffer"` / `"risky"`
- `get_upgrade_info()`: expose material cost per mode in the preview
- UI / command layer: let player choose mode when initiating an upgrade
- Tests for all three modes

## Tasks

- [x] Task 1: Add `mode` parameter to `gear_manager.attempt_upgrade()` and `get_upgrade_info()`
- [ ] Task 2: Add gear_manager tests for buffer and risky modes
- [ ] Task 3: Update UI components and command handler to support mode selection

## Not Doing

- Combining modes simultaneously
- Adjusting success rate for any mode
- Different AP costs per mode — all modes cost 1 AP

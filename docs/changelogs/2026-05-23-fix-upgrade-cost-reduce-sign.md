---
title: "Fix: upgrade_cost_reduce affix displays with negative sign"
status: Ready-to-review
created: 2026-05-23
doc_type: change
last_reviewed: 2026-05-23
source_paths:
  - src/cogs/ui_renderer.py
  - src/core/notification.py
  - tests/test_discord_notifications.py
  - tests/test_discord_commands.py
scope: "Fix display sign for reduce-type affixes in both the gear embed and affix notifications."
---

## Problem Statement

`upgrade_cost_reduce` affixes display as "+5%" in both the gear embed (`_build_affix_section`) and affix event notifications (`_format_event`). The spec in `docs/managers/affix-manager.md` defines this affix as "強化素材消耗 -X%", so the sign must be negative.

Both display paths hard-code `+` without inspecting the affix type.

## Recommended Direction

**Chosen: define a constant set of reduce-type affixes and derive sign at render time.**

At both render sites, check whether `affix_type` is in a `REDUCE_AFFIX_TYPES` set; if so, use `-`, otherwise `+`. The set lives in `ui_renderer.py` (shared constant, since both files already import or can access it, but `notification.py` needs it too — duplicate the set as a module-level constant in each file to avoid a cross-module import).

Alternatives excluded:
- Encode sign in the DB value as negative integers: breaks existing data, adds ambiguity for `get_affix_bonuses` callers.
- Use a display-mapping dict keyed by affix_type: overkill for a boolean decision; harder to extend later.

## Key Assumptions

- Only `upgrade_cost_reduce` has a negative display sign today. Future reduce-type affixes should be added to the set explicitly.
- `value` stored in DB is always positive; sign is a display concern only.

## MVP Scope / Not Doing

- Fix `_build_affix_section` in `ui_renderer.py`
- Fix `_format_event` affix branch in `notification.py`
- Add failing tests for both locations (notification tests already written by bug skill)
- Not doing: `cycle_time_reduce` — spec says "行動週期縮短 X%" without specifying sign; existing test asserts `+2%` and is not contradicted by the spec document. Out of scope.
- Not doing: unify the two constants into a shared module (single caller each, no duplication risk yet)

## Tasks

- [x] Task 1: Fix `notification.py` affix sign + ensure pre-written tests pass
  - `notification.py` line 182 hard-codes `+`; add `REDUCE_AFFIX_TYPES = {"upgrade_cost_reduce"}` and derive sign
  - Acceptance: `TestAffixNotificationSign` all pass; `test_positive_affix_still_uses_plus_sign` still passes
- [x] Task 2: Fix `ui_renderer.py` `_build_affix_section` sign + add test
  - `ui_renderer.py` line 343 hard-codes `+`; add `REDUCE_AFFIX_TYPES = {"upgrade_cost_reduce"}` and derive sign
  - Acceptance: new test for `upgrade_cost_reduce` slot shows `-X%`; existing tests `test_filled_slot_shows_affix_type_and_value` and `test_multiple_slots_mixed` still pass

"""
settlement.py — v2 cycle settlement orchestration.

Public entrypoints:
  settle_complete_cycles(user_id, now)   — watcher / refresh trigger
  change_action(user_id, new_action, new_target, now) — action-change trigger
  settle_burst(user_id, now) -> bool     — burst trigger (returns False if insufficient AP)

Each entrypoint opens its own DB connection and manages the transaction boundary.
Internal helpers accept an open aiosqlite connection and do not commit.
"""

import math
import random
from datetime import datetime, timedelta

from core.config import get_env_float, get_env_int
from core.formula import (
    VALID_ACTIONS,
    action_costs,
    compute_output,
    effective_cycle_seconds,
)
from core.utils import dt_str, parse_dt
from database.schema import get_connection
from managers import affix_manager, auto_tool_manager, building_manager, player_manager, resource_manager, stage_manager, trial_manager


# ---------------------------------------------------------------------------
# Internal orchestration helpers (not public API)
# ---------------------------------------------------------------------------

def _effective_material_drop_rate(base_rate: float, stage_type: str, action: str, affix_material_drop_pct: int = 0) -> float:
    rate = base_rate * 2 if (stage_type == "upgrade" or stage_type == action) else base_rate
    return min(1.0, rate + affix_material_drop_pct / 100.0)


async def _read_player(db, user_id: str) -> dict | None:
    async with db.execute("SELECT * FROM players WHERE user_id=?", (user_id,)) as cur:
        row = await cur.fetchone()
        if row is None:
            return None
        cols = [d[0] for d in cur.description]
        return dict(zip(cols, row))


# ---------------------------------------------------------------------------
# Core single-cycle logic
# ---------------------------------------------------------------------------

async def _read_building_levels(db) -> dict[str, int]:
    """Return {building_type: level} for all buildings."""
    levels: dict[str, int] = {}
    async with db.execute("SELECT building_type, level FROM buildings") as cur:
        async for row in cur:
            levels[row[0]] = row[1]
    return levels


async def _run_one_cycle(
    db, user_id: str, cycle_end_time: datetime, *,
    action: str, action_target: str | None = None,
    write_player_timestamps: bool = True,
    affix_bonuses: dict | None = None,
) -> list[dict]:
    """
    Resolve one complete cycle for an action stream (manual action or auto-tool).

    Callers pass an explicit settlement context:
      action                — action type driving this cycle (must be a valid action)
      action_target         — target building for action="building" (else ignored)
      write_player_timestamps — True for the manual action (updates players.completion_time
                               / last_update_time); False for burst and auto-tool (the caller
                               advances its own timing).
    cycle_end_time is the effective timestamp for stage/overtime checks and drops.
    affix_bonuses: pre-queried bonuses for this action's tool; queried internally only when
    None and write_player_timestamps is True.
    Material drops, stage progress and trial contribution are attributed to user_id.
    Returns a list of notification events emitted during this cycle.
    """
    events: list[dict] = []
    building_pre_events: list[dict] = []  # buffered until after stage events

    if action is None or action not in VALID_ACTIONS:
        return events

    if affix_bonuses is None and write_player_timestamps:
        affix_bonuses = await affix_manager.get_affix_bonuses(db, user_id, action)
    if affix_bonuses is None:
        affix_bonuses = {t: 0 for t in affix_manager.AFFIX_TYPES}

    # Deduct resource costs, detect shortage
    costs = action_costs(action)
    shortage_flag = False
    for resource, cost in costs.items():
        current = await resource_manager.balance(db, resource)
        if current < cost:
            shortage_flag = True
        await resource_manager.withdraw(db, resource, cost, cycle_end_time)

    # Compute raw output and apply shortage penalty to settlement output
    output = await compute_output(db, user_id, action, affix_efficiency_pct=affix_bonuses["efficiency"])
    settlement_output = math.floor(output * 0.5) if shortage_flag else output

    # Overtime detection — must happen BEFORE add_progress which may reset stage state
    stage_pre = await stage_manager.get_stage_info(db)
    if stage_pre:
        overtime_threshold = get_env_int("STAGE_OVERTIME_SECONDS")
        stage_started = parse_dt(stage_pre["stage_started_at"])
        elapsed = (cycle_end_time - stage_started).total_seconds()
        stage_type_pre = stage_pre.get("current_stage_type", "")
        action_relevant = (stage_type_pre == "upgrade") or (action == stage_type_pre)
        if (elapsed > overtime_threshold
                and not stage_pre.get("overtime_notified", 0)
                and action_relevant):
            events.append({
                "type": "overtime",
                "stages_cleared": stage_pre["stages_cleared"],
                "progress": stage_pre["current_stage_progress"],
                "target": stage_pre["current_stage_target"],
            })

    # Distribute settlement_output (with building upgrade detection)
    if action == "gathering":
        await resource_manager.deposit(db, "food", settlement_output, cycle_end_time)
        await resource_manager.deposit(db, "wood", settlement_output, cycle_end_time)
    elif action == "combat":
        await resource_manager.deposit(db, "knowledge", settlement_output, cycle_end_time)
    elif action in ("building", "research"):
        target_building = (
            "research_lab" if action == "research" else action_target
        )
        stages_cleared = await stage_manager.get_stages_cleared(db)

        async with db.execute(
            "SELECT level FROM buildings WHERE building_type=?", (target_building,)
        ) as cur:
            row = await cur.fetchone()
        pre_level = row[0] if row else 0

        await building_manager.add_xp(db, target_building, settlement_output, stages_cleared, cycle_end_time)

        async with db.execute(
            "SELECT level FROM buildings WHERE building_type=?", (target_building,)
        ) as cur:
            row = await cur.fetchone()
        post_level = row[0] if row else 0

        xp_per = get_env_int("BUILDING_XP_PER_LEVEL")
        for lvl in range(pre_level + 1, post_level + 1):
            building_pre_events.append({
                "type": "building_upgrade",
                "building_type": target_building,
                "old_level": lvl - 1,
                "new_level": lvl,
                "next_xp_req": (lvl + 1) * xp_per,
            })

    # Stage progress uses pre-penalty output
    new_stages_cleared = await stage_manager.add_progress(db, action, output, cycle_end_time)

    if new_stages_cleared is not None:
        stage_post = await stage_manager.get_stage_info(db)
        events.append({
            "type": "stage_clear",
            "stages_cleared": new_stages_cleared,
            "next_stage_type": stage_post.get("current_stage_type", ""),
            "next_target": stage_post.get("current_stage_target", 0),
        })

        # If upgrade stage cleared (every 5th), emit upgrade_stage_clear and check buildings
        if new_stages_cleared % 5 == 0:
            old_cap = (new_stages_cleared - 1) // 5 + 1
            new_cap = new_stages_cleared // 5 + 1
            events.append({
                "type": "upgrade_stage_clear",
                "round": new_stages_cleared // 5,
                "old_cap": old_cap,
                "new_cap": new_cap,
                "next_stage_type": stage_post.get("current_stage_type", ""),
                "next_target": stage_post.get("current_stage_target", 0),
            })

            buildings_before = await _read_building_levels(db)
            await building_manager.check_all_upgrades(db, new_stages_cleared, cycle_end_time)
            buildings_after = await _read_building_levels(db)

            xp_per = get_env_int("BUILDING_XP_PER_LEVEL")
            for btype, pre_lv in buildings_before.items():
                post_lv = buildings_after.get(btype, pre_lv)
                for lvl in range(pre_lv + 1, post_lv + 1):
                    events.append({
                        "type": "building_upgrade",
                        "building_type": btype,
                        "old_level": lvl - 1,
                        "new_level": lvl,
                        "next_xp_req": (lvl + 1) * xp_per,
                    })

    # Emit buffered building upgrades (from add_xp) after stage events
    events.extend(building_pre_events)

    # Village trial progress — parallel to and independent of stage progress.
    # Uses the same pre-shortage-penalty output as stage progress (all action types count).
    trial_event = await trial_manager.add_progress(db, output, user_id, cycle_end_time)
    if trial_event is not None:
        events.append(trial_event)

    # Material drop — boosted when stage type matches action or is upgrade.
    # Use stage_pre (read before add_progress) so a stage clear in this cycle
    # doesn't shift the rate to the next stage's type.
    base_rate = get_env_float("MATERIAL_DROP_RATE")
    stage_type = stage_pre.get("current_stage_type", "") if stage_pre else ""
    drop_rate = _effective_material_drop_rate(base_rate, stage_type, action, affix_material_drop_pct=affix_bonuses["material_drop"])
    if random.random() < drop_rate:
        await player_manager.add_material(db, user_id, action, 1, cycle_end_time)

    # Update player cycle timestamps (manual action only; burst/auto-tool advance elsewhere)
    if write_player_timestamps:
        now_str = dt_str(cycle_end_time)
        effective_secs = effective_cycle_seconds(affix_bonuses["cycle_time_reduce"])
        new_completion = dt_str(cycle_end_time + timedelta(seconds=effective_secs))
        await db.execute(
            "UPDATE players SET last_update_time=?, completion_time=?, updated_at=? WHERE user_id=?",
            (now_str, new_completion, now_str, user_id),
        )

    return events


# ---------------------------------------------------------------------------
# Public entrypoints
# ---------------------------------------------------------------------------

async def settle_complete_cycles(user_id: str, now: datetime) -> list[dict]:
    """
    Catch up all overdue complete cycles for user_id, up to MAX_CYCLES_PER_SETTLEMENT.
    Triggered by the watcher and by the refresh/dashboard path.
    Returns a list of notification events emitted during settlement.
    """
    events: list[dict] = []
    async with get_connection() as db:
        player = await _read_player(db, user_id)
        if player is None or player["action"] is None or player["completion_time"] is None:
            return events

        completion_time = parse_dt(player["completion_time"])
        if completion_time > now:
            return events

        action = player["action"]
        action_target = player["action_target"]
        affix_bonuses = await affix_manager.get_affix_bonuses(db, user_id, action)
        effective_secs = effective_cycle_seconds(affix_bonuses["cycle_time_reduce"])
        max_cycles = get_env_int("MAX_CYCLES_PER_SETTLEMENT")
        cycle_end = completion_time
        cycles_done = 0

        while cycle_end <= now and cycles_done < max_cycles:
            cycle_events = await _run_one_cycle(
                db, user_id, cycle_end,
                action=action, action_target=action_target, affix_bonuses=affix_bonuses,
            )
            events.extend(cycle_events)
            cycle_end += timedelta(seconds=effective_secs)
            cycles_done += 1

        await db.commit()

    return events


async def settle_auto_tool_cycles(user_id: str, tool_type: str, now: datetime) -> list[dict]:
    """
    Catch up all overdue complete cycles for one auto-tool, up to MAX_CYCLES_PER_SETTLEMENT.
    Each cycle reuses the action resolver with the auto-tool's own context (no player
    timestamp writes). Only cycles whose completion falls within the paid window
    (completion_time <= min(now, expires_at)) are settled; once the auto-tool has fully
    expired and is caught up, its row is deleted (the tool frees up). Returns events.

    Runs under BEGIN IMMEDIATE so the expires_at read and the end() decision serialize with
    a concurrent refuel/start/change_action (Architecture Decision #7): a refuel that extends
    expires_at either commits before this holds the lock (so we read the fresh, longer expiry
    and do not end the tool) or waits until this transaction commits — it can never be lost.
    """
    events: list[dict] = []
    async with get_connection() as db:
        await db.execute("BEGIN IMMEDIATE")
        row = await auto_tool_manager.get(db, user_id, tool_type)
        if row is None:
            return events

        expires_at = parse_dt(row["expires_at"])
        action_target = row["action_target"]
        bonuses = await affix_manager.get_affix_bonuses(db, user_id, tool_type)
        effective_secs = effective_cycle_seconds(bonuses["cycle_time_reduce"])
        max_cycles = get_env_int("MAX_CYCLES_PER_SETTLEMENT")
        deadline = min(now, expires_at)

        cycle_end = parse_dt(row["completion_time"])
        cycles_done = 0
        while cycle_end <= deadline and cycles_done < max_cycles:
            cycle_events = await _run_one_cycle(
                db, user_id, cycle_end,
                action=tool_type, action_target=action_target,
                write_player_timestamps=False, affix_bonuses=bonuses,
            )
            events.extend(cycle_events)
            next_completion = cycle_end + timedelta(seconds=effective_secs)
            await auto_tool_manager.advance_cycle(db, user_id, tool_type, cycle_end, next_completion)
            cycle_end = next_completion
            cycles_done += 1

        # End (free the tool) once fully expired and caught up. "Caught up" means the loop
        # stopped because the next cycle falls beyond the paid window (cycle_end > deadline),
        # NOT because the per-tick cap was hit with backlog still inside the window.
        caught_up = cycle_end > deadline
        if now >= expires_at and caught_up:
            await auto_tool_manager.end(db, user_id, tool_type)

        await db.commit()

    return events


async def change_action(
    user_id: str, new_action: str | None, new_target: str | None, now: datetime
) -> list[dict]:
    """
    Atomic action-change: settle overdue full cycles, run optional partial cycle for
    the old action, then write the new action and reset cycle timing.

    new_target must be a building enum for action='building', else pass None.
    Pass new_action=None to clear the action.
    Returns a list of notification events emitted during the full-cycle catch-up.
    """
    if new_action is not None and new_action not in VALID_ACTIONS:
        raise ValueError(f"Invalid action: {new_action!r}")

    if new_action == "building":
        from managers.building_manager import BUILDING_TYPES
        if new_target not in BUILDING_TYPES:
            raise ValueError(f"Invalid building target: {new_target!r}. Must be one of {BUILDING_TYPES}")

    events: list[dict] = []
    async with get_connection() as db:
        # Write lock before the guard read so a concurrent auto-tool start serializes
        # against this action change (Architecture Decision #7).
        await db.execute("BEGIN IMMEDIATE")
        player = await _read_player(db, user_id)
        if player is None:
            return events

        # Mutual exclusion: a tool currently running as an auto-tool cannot be chosen as
        # the manual action. Fail fast here; the final action UPDATE below is also made
        # conditional on the same predicate so a concurrent auto-tool start cannot slip in.
        if new_action is not None and await auto_tool_manager.is_active(db, user_id, new_action):
            raise ValueError(f"Cannot set action {new_action!r}: it is running as an auto-tool")

        old_action = player["action"]
        completion_time_str = player["completion_time"]
        last_update_time_str = player["last_update_time"]

        # Step 1: Catch-up full cycles for old action
        old_affix_bonuses = None
        if old_action is not None and completion_time_str is not None:
            old_affix_bonuses = await affix_manager.get_affix_bonuses(db, user_id, old_action)
            old_effective_secs = effective_cycle_seconds(old_affix_bonuses["cycle_time_reduce"])
            completion_time = parse_dt(completion_time_str)
            max_cycles = get_env_int("MAX_CYCLES_PER_SETTLEMENT")
            cycle_end = completion_time
            cycles_done = 0
            while cycle_end <= now and cycles_done < max_cycles:
                cycle_events = await _run_one_cycle(
                    db, user_id, cycle_end,
                    action=old_action, action_target=player["action_target"],
                    affix_bonuses=old_affix_bonuses,
                )
                events.extend(cycle_events)
                cycle_end += timedelta(seconds=old_effective_secs)
                cycles_done += 1
            # Re-read player after catch-up (timestamps may have changed)
            player = await _read_player(db, user_id)
            last_update_time_str = player["last_update_time"]

        # Step 2: Partial cycle for old action (skipped if first-time, no old action,
        # or old_action is no longer a recognized action, e.g. residual pre-removal state)
        if old_action is not None and old_action in VALID_ACTIONS and last_update_time_str is not None:
            last_update = parse_dt(last_update_time_str)
            if old_affix_bonuses is None:
                old_affix_bonuses = await affix_manager.get_affix_bonuses(db, user_id, old_action)
            old_effective_secs = effective_cycle_seconds(old_affix_bonuses["cycle_time_reduce"])
            elapsed = (now - last_update).total_seconds()
            ratio = min(max(elapsed / old_effective_secs, 0.0), 1.0)

            costs = action_costs(old_action)
            shortage_flag = False
            for resource, cost in costs.items():
                partial_cost = math.floor(cost * ratio)
                current = await resource_manager.balance(db, resource)
                if current < partial_cost:
                    shortage_flag = True
                await resource_manager.withdraw(db, resource, partial_cost, now)

            output = await compute_output(db, user_id, old_action, affix_efficiency_pct=old_affix_bonuses["efficiency"])
            partial_output = math.floor(output * ratio)
            settlement_output = math.floor(partial_output * 0.5) if shortage_flag else partial_output

            if old_action == "gathering":
                await resource_manager.deposit(db, "food", settlement_output, now)
                await resource_manager.deposit(db, "wood", settlement_output, now)
            elif old_action == "combat":
                await resource_manager.deposit(db, "knowledge", settlement_output, now)
            elif old_action in ("building", "research"):
                target_building = (
                    "research_lab" if old_action == "research" else player["action_target"]
                )
                stages_cleared = await stage_manager.get_stages_cleared(db)
                await building_manager.add_xp(db, target_building, settlement_output, stages_cleared, now)

            # Stage progress uses pre-penalty partial_output; no material drop for partial
            await stage_manager.add_progress(db, old_action, partial_output, now)

            # Village trial progress — parallel to stage progress, same pre-penalty basis
            trial_event = await trial_manager.add_progress(db, partial_output, user_id, now)
            if trial_event is not None:
                events.append(trial_event)

        # Step 3: Write new action and reset cycle timing
        now_str = dt_str(now)
        actual_target = new_target if new_action == "building" else None
        if new_action is not None:
            new_affix_bonuses = await affix_manager.get_affix_bonuses(db, user_id, new_action)
            new_effective_secs = effective_cycle_seconds(new_affix_bonuses["cycle_time_reduce"])
            new_completion = dt_str(now + timedelta(seconds=new_effective_secs))
            # Conditional on the auto-tool exclusion (race-safe against a concurrent start).
            cur = await db.execute(
                """UPDATE players
                   SET action=?, action_target=?, completion_time=?,
                       last_update_time=?, updated_at=?
                   WHERE user_id=?
                     AND NOT EXISTS (
                         SELECT 1 FROM player_auto_tools WHERE user_id=? AND tool_type=?
                     )""",
                (new_action, actual_target, new_completion, now_str, now_str, user_id, user_id, new_action),
            )
            if cur.rowcount != 1:
                raise ValueError(f"Cannot set action {new_action!r}: it is running as an auto-tool")
        else:
            await db.execute(
                """UPDATE players
                   SET action=NULL, action_target=NULL, completion_time=NULL,
                       last_update_time=?, updated_at=?
                   WHERE user_id=?""",
                (now_str, now_str, user_id),
            )

        await db.commit()

    return events


async def settle_burst(user_id: str, now: datetime) -> tuple[bool, list[dict]]:
    """
    Burst: spend 1 AP and immediately settle 3 independent complete cycles.
    completion_time and last_update_time are NOT updated.
    Returns (False, []) if the player has insufficient AP or no active action,
    otherwise (True, events) with all notification events from the 3 cycles.
    """
    events: list[dict] = []
    async with get_connection() as db:
        player = await _read_player(db, user_id)
        if player is None or player["action"] is None:
            return False, events

        ap = await player_manager.get_ap(db, user_id, now)
        if ap < 1:
            return False, events

        await player_manager.spend_ap(db, user_id, 1, now)

        burst_affix_bonuses = await affix_manager.get_affix_bonuses(db, user_id, player["action"])
        for _ in range(3):
            cycle_events = await _run_one_cycle(
                db, user_id, now,
                action=player["action"], action_target=player["action_target"],
                write_player_timestamps=False, affix_bonuses=burst_affix_bonuses,
            )
            events.extend(cycle_events)

        await db.commit()
        return True, events

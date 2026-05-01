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
)
from core.utils import dt_str, parse_dt
from database.schema import get_connection
from managers import building_manager, player_manager, resource_manager, stage_manager


# ---------------------------------------------------------------------------
# Internal orchestration helpers (not public API)
# ---------------------------------------------------------------------------

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

async def _run_one_cycle(
    db, user_id: str, cycle_end_time: datetime, update_timestamps: bool = True
) -> None:
    """
    Resolve one complete cycle for user_id.
    cycle_end_time is used as the effective timestamp for stage/overtime checks.
    When update_timestamps=False (burst), last_update_time and completion_time are not written.
    """
    player = await _read_player(db, user_id)
    if player is None or player["action"] is None:
        return

    action: str = player["action"]

    # Deduct resource costs, detect shortage
    costs = action_costs(action)
    shortage_flag = False
    for resource, cost in costs.items():
        current = await resource_manager.balance(db, resource)
        if current < cost:
            shortage_flag = True
        await resource_manager.withdraw(db, resource, cost, cycle_end_time)

    # Compute raw output and apply shortage penalty to settlement output
    output = await compute_output(db, user_id, action)
    settlement_output = math.floor(output * 0.5) if shortage_flag else output

    # Distribute settlement_output
    if action == "gathering":
        await resource_manager.deposit(db, "food", settlement_output, cycle_end_time)
        await resource_manager.deposit(db, "wood", settlement_output, cycle_end_time)
    elif action == "combat":
        await resource_manager.deposit(db, "knowledge", settlement_output, cycle_end_time)
    elif action in ("building", "research"):
        target_building = (
            "research_lab" if action == "research" else player["action_target"]
        )
        stages_cleared = await stage_manager.get_stages_cleared(db)
        await building_manager.add_xp(db, target_building, settlement_output, stages_cleared, cycle_end_time)

    # Stage progress uses pre-penalty output
    new_stages_cleared = await stage_manager.add_progress(db, action, output, cycle_end_time)

    # If upgrade stage was cleared, re-check all building upgrade eligibility
    if new_stages_cleared is not None and new_stages_cleared % 5 == 0:
        await building_manager.check_all_upgrades(db, new_stages_cleared, cycle_end_time)

    # Material drop
    drop_rate = get_env_float("MATERIAL_DROP_RATE")
    if random.random() < drop_rate:
        await player_manager.add_material(db, user_id, action, 1, cycle_end_time)

    # Update player cycle timestamps
    if update_timestamps:
        new_completion = dt_str(
            cycle_end_time + timedelta(minutes=get_env_int("ACTION_CYCLE_MINUTES"))
        )
        await db.execute(
            "UPDATE players SET last_update_time=?, completion_time=?, updated_at=? WHERE user_id=?",
            (dt_str(cycle_end_time), new_completion, dt_str(cycle_end_time), user_id),
        )


# ---------------------------------------------------------------------------
# Public entrypoints
# ---------------------------------------------------------------------------

async def settle_complete_cycles(user_id: str, now: datetime) -> None:
    """
    Catch up all overdue complete cycles for user_id, up to MAX_CYCLES_PER_SETTLEMENT.
    Triggered by the watcher and by the refresh/dashboard path.
    """
    async with get_connection() as db:
        player = await _read_player(db, user_id)
        if player is None or player["action"] is None or player["completion_time"] is None:
            return

        completion_time = parse_dt(player["completion_time"])
        if completion_time > now:
            return

        cycle_mins = get_env_int("ACTION_CYCLE_MINUTES")
        max_cycles = get_env_int("MAX_CYCLES_PER_SETTLEMENT")
        cycle_end = completion_time
        cycles_done = 0

        while cycle_end <= now and cycles_done < max_cycles:
            await _run_one_cycle(db, user_id, cycle_end)
            cycle_end += timedelta(minutes=cycle_mins)
            cycles_done += 1

        await db.commit()


async def change_action(
    user_id: str, new_action: str | None, new_target: str | None, now: datetime
) -> None:
    """
    Atomic action-change: settle overdue full cycles, run optional partial cycle for
    the old action, then write the new action and reset cycle timing.

    new_target must be a building enum for action='building', else pass None.
    Pass new_action=None to clear the action.
    """
    if new_action is not None and new_action not in VALID_ACTIONS:
        raise ValueError(f"Invalid action: {new_action!r}")

    if new_action == "building":
        from managers.building_manager import BUILDING_TYPES
        if new_target not in BUILDING_TYPES:
            raise ValueError(f"Invalid building target: {new_target!r}. Must be one of {BUILDING_TYPES}")

    async with get_connection() as db:
        player = await _read_player(db, user_id)
        if player is None:
            return

        old_action = player["action"]
        completion_time_str = player["completion_time"]
        last_update_time_str = player["last_update_time"]

        # Step 1: Catch-up full cycles for old action
        if old_action is not None and completion_time_str is not None:
            completion_time = parse_dt(completion_time_str)
            cycle_mins = get_env_int("ACTION_CYCLE_MINUTES")
            max_cycles = get_env_int("MAX_CYCLES_PER_SETTLEMENT")
            cycle_end = completion_time
            cycles_done = 0
            while cycle_end <= now and cycles_done < max_cycles:
                await _run_one_cycle(db, user_id, cycle_end)
                cycle_end += timedelta(minutes=cycle_mins)
                cycles_done += 1
            # Re-read player after catch-up (timestamps may have changed)
            player = await _read_player(db, user_id)
            last_update_time_str = player["last_update_time"]

        # Step 2: Partial cycle for old action (skipped if first-time or no old action)
        if old_action is not None and last_update_time_str is not None:
            last_update = parse_dt(last_update_time_str)
            cycle_secs = get_env_int("ACTION_CYCLE_MINUTES") * 60
            elapsed = (now - last_update).total_seconds()
            ratio = min(max(elapsed / cycle_secs, 0.0), 1.0)

            costs = action_costs(old_action)
            shortage_flag = False
            for resource, cost in costs.items():
                partial_cost = math.floor(cost * ratio)
                current = await resource_manager.balance(db, resource)
                if current < partial_cost:
                    shortage_flag = True
                await resource_manager.withdraw(db, resource, partial_cost, now)

            output = await compute_output(db, user_id, old_action)
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

        # Step 3: Write new action and reset cycle timing
        now_str = dt_str(now)
        actual_target = new_target if new_action == "building" else None
        if new_action is not None:
            new_completion = dt_str(now + timedelta(minutes=get_env_int("ACTION_CYCLE_MINUTES")))
            await db.execute(
                """UPDATE players
                   SET action=?, action_target=?, completion_time=?,
                       last_update_time=?, updated_at=?
                   WHERE user_id=?""",
                (new_action, actual_target, new_completion, now_str, now_str, user_id),
            )
        else:
            await db.execute(
                """UPDATE players
                   SET action=NULL, action_target=NULL, completion_time=NULL,
                       last_update_time=?, updated_at=?
                   WHERE user_id=?""",
                (now_str, now_str, user_id),
            )

        await db.commit()


async def settle_burst(user_id: str, now: datetime) -> bool:
    """
    Burst: spend 1 AP and immediately settle 3 independent complete cycles.
    completion_time and last_update_time are NOT updated.
    Returns False if the player has insufficient AP or no active action.
    """
    async with get_connection() as db:
        player = await _read_player(db, user_id)
        if player is None or player["action"] is None:
            return False

        ap = await player_manager.get_ap(db, user_id, now)
        if ap < 1:
            return False

        await player_manager.spend_ap(db, user_id, 1, now)

        for _ in range(3):
            await _run_one_cycle(db, user_id, now, update_timestamps=False)

        await db.commit()
        return True

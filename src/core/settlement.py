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
from datetime import datetime, timedelta, timezone

from core.config import get_env_float, get_env_int
from core.formula import (
    ACTION_FACILITY_BUILDING,
    ACTION_MATERIAL_COL,
    STAGE_TYPES,
    VALID_ACTIONS,
    action_costs,
    compute_output,
)
from database.schema import get_connection


# ---------------------------------------------------------------------------
# Datetime helpers
# ---------------------------------------------------------------------------

def _parse_dt(s: str) -> datetime:
    """Parse UTC ISO-8601 text. Always returns an aware datetime."""
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _dt_str(dt: datetime) -> str:
    """Serialise datetime to UTC ISO-8601 text."""
    return dt.astimezone(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Stage target helper
# ---------------------------------------------------------------------------

def _compute_stage_target(stages_cleared: int) -> int:
    """
    Compute the target progress for the stage that starts after stages_cleared clears.
    stages_cleared is the count *after* the most recent clear.
    """
    round_number = stages_cleared // 5 + 1
    stage_index = stages_cleared % 5
    base = get_env_int("STAGE_BASE_TARGET")
    growth = get_env_float("STAGE_TARGET_GROWTH_PER_ROUND")
    difficulty = math.floor(base * (1 + (round_number - 1) * growth))
    if stage_index == 4:
        multiplier = get_env_float("UPGRADE_STAGE_TARGET_MULTIPLIER")
        return math.floor(difficulty * multiplier)
    return difficulty


# ---------------------------------------------------------------------------
# DB helpers — resource, building, stage, player
# ---------------------------------------------------------------------------

async def _get_resource(db, resource_type: str) -> int:
    async with db.execute(
        "SELECT amount FROM village_resources WHERE resource_type=?", (resource_type,)
    ) as cur:
        row = await cur.fetchone()
    return row[0] if row else 0


async def _set_resource(db, resource_type: str, amount: int, ts: datetime) -> None:
    await db.execute(
        "UPDATE village_resources SET amount=?, updated_at=? WHERE resource_type=?",
        (amount, _dt_str(ts), resource_type),
    )


async def _add_resource(db, resource_type: str, amount: int, ts: datetime) -> None:
    current = await _get_resource(db, resource_type)
    await _set_resource(db, resource_type, current + amount, ts)


async def _get_stages_cleared(db) -> int:
    async with db.execute("SELECT stages_cleared FROM stage_state WHERE id=1") as cur:
        row = await cur.fetchone()
    return row[0] if row else 0


async def _read_player(db, user_id: str) -> dict | None:
    async with db.execute("SELECT * FROM players WHERE user_id=?", (user_id,)) as cur:
        row = await cur.fetchone()
        if row is None:
            return None
        cols = [d[0] for d in cur.description]
        return dict(zip(cols, row))


async def _get_ap(db, user_id: str, now: datetime) -> int:
    async with db.execute(
        "SELECT ap_full_time FROM players WHERE user_id=?", (user_id,)
    ) as cur:
        row = await cur.fetchone()
    if row is None:
        return 0
    ap_cap = get_env_int("AP_CAP")
    ap_full_time = _parse_dt(row[0])
    if now >= ap_full_time:
        return ap_cap
    recovery_mins = get_env_int("AP_RECOVERY_MINUTES")
    remaining_secs = (ap_full_time - now).total_seconds()
    remaining_ap = math.ceil(remaining_secs / (recovery_mins * 60))
    return max(0, ap_cap - remaining_ap)


async def _spend_ap(db, user_id: str, amount: int, now: datetime) -> None:
    async with db.execute(
        "SELECT ap_full_time FROM players WHERE user_id=?", (user_id,)
    ) as cur:
        row = await cur.fetchone()
    if row is None:
        return
    recovery_mins = get_env_int("AP_RECOVERY_MINUTES")
    ap_full_time = _parse_dt(row[0])
    new_ap_full_time = max(now, ap_full_time) + timedelta(minutes=amount * recovery_mins)
    await db.execute(
        "UPDATE players SET ap_full_time=?, updated_at=? WHERE user_id=?",
        (_dt_str(new_ap_full_time), _dt_str(now), user_id),
    )


# ---------------------------------------------------------------------------
# Building helpers
# ---------------------------------------------------------------------------

async def _add_building_xp(
    db, building_type: str, xp: int, stages_cleared: int, ts: datetime
) -> None:
    """
    Add XP to a building and run the upgrade loop against the current level_cap.
    If already at level_cap, clamp xp_progress to level × BUILDING_XP_PER_LEVEL.
    """
    async with db.execute(
        "SELECT level, xp_progress FROM buildings WHERE building_type=?", (building_type,)
    ) as cur:
        row = await cur.fetchone()
    if row is None:
        return

    level, xp_progress = row
    level_cap = stages_cleared // 5 + 1
    xp_per = get_env_int("BUILDING_XP_PER_LEVEL")

    if level >= level_cap:
        max_xp = level * xp_per
        clamped = min(xp_progress + xp, max_xp)
        await db.execute(
            "UPDATE buildings SET xp_progress=?, updated_at=? WHERE building_type=?",
            (clamped, _dt_str(ts), building_type),
        )
        return

    xp_progress += xp
    while level < level_cap:
        required = (level + 1) * xp_per
        if xp_progress >= required:
            xp_progress -= required
            level += 1
        else:
            break

    # If we are now at cap, clamp any overflow
    if level >= level_cap:
        xp_progress = min(xp_progress, level * xp_per)

    await db.execute(
        "UPDATE buildings SET level=?, xp_progress=?, updated_at=? WHERE building_type=?",
        (level, xp_progress, _dt_str(ts), building_type),
    )


async def _check_all_building_upgrades(
    db, stages_cleared: int, ts: datetime
) -> None:
    """Re-check every building for upgrade eligibility after level_cap increases."""
    for building_type in ACTION_FACILITY_BUILDING.values():
        await _add_building_xp(db, building_type, 0, stages_cleared, ts)


# ---------------------------------------------------------------------------
# Stage progress
# ---------------------------------------------------------------------------

async def _add_stage_progress(
    db, action: str, output: int, effective_time: datetime
) -> int | None:
    """
    Add output to stage progress if this action type is relevant.
    Applies overtime multiplier if the stage has run past STAGE_OVERTIME_SECONDS.

    Returns new stages_cleared (int) if a stage was cleared, or None if not.
    """
    async with db.execute("SELECT * FROM stage_state WHERE id=1") as cur:
        row = await cur.fetchone()
        if row is None:
            return None
        cols = [d[0] for d in cur.description]
        state = dict(zip(cols, row))

    stage_type = state["current_stage_type"]

    # Upgrade stage accepts all actions; normal stages accept only the matching action
    if stage_type == "upgrade":
        counts = True
    else:
        counts = action == stage_type

    if not counts:
        return None

    stage_started = _parse_dt(state["stage_started_at"])
    elapsed_secs = (effective_time - stage_started).total_seconds()
    overtime_threshold = get_env_int("STAGE_OVERTIME_SECONDS")

    if elapsed_secs > overtime_threshold:
        multiplier = get_env_float("STAGE_OVERTIME_PROGRESS_MULTIPLIER")
        progress_to_add = math.floor(output * multiplier)
        new_notified = 1
    else:
        progress_to_add = output
        new_notified = state["overtime_notified"]

    new_progress = state["current_stage_progress"] + progress_to_add
    target = state["current_stage_target"]
    now_str = _dt_str(effective_time)

    if new_progress >= target:
        new_stages_cleared = state["stages_cleared"] + 1
        new_stage_index = new_stages_cleared % 5
        new_stage_type = STAGE_TYPES[new_stage_index]
        new_target = _compute_stage_target(new_stages_cleared)
        await db.execute(
            """UPDATE stage_state SET
               stages_cleared=?, current_stage_index=?, current_stage_type=?,
               current_stage_progress=0, current_stage_target=?,
               stage_started_at=?, overtime_notified=0, updated_at=?
               WHERE id=1""",
            (new_stages_cleared, new_stage_index, new_stage_type, new_target, now_str, now_str),
        )
        return new_stages_cleared

    await db.execute(
        "UPDATE stage_state SET current_stage_progress=?, overtime_notified=?, updated_at=? WHERE id=1",
        (new_progress, new_notified, now_str),
    )
    return None


# ---------------------------------------------------------------------------
# Material drop
# ---------------------------------------------------------------------------

async def _roll_material(
    db, user_id: str, action: str, ts: datetime
) -> None:
    drop_rate = get_env_float("MATERIAL_DROP_RATE")
    if random.random() < drop_rate:
        col = ACTION_MATERIAL_COL[action]
        await db.execute(
            f"UPDATE players SET {col} = {col} + 1, updated_at=? WHERE user_id=?",
            (_dt_str(ts), user_id),
        )


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
        current = await _get_resource(db, resource)
        if current < cost:
            shortage_flag = True
        await _set_resource(db, resource, max(0, current - cost), cycle_end_time)

    # Compute raw output and apply shortage penalty to settlement output
    output = await compute_output(db, user_id, action)
    settlement_output = math.floor(output * 0.5) if shortage_flag else output

    # Distribute settlement_output
    if action == "gathering":
        await _add_resource(db, "food", settlement_output, cycle_end_time)
        await _add_resource(db, "wood", settlement_output, cycle_end_time)
    elif action == "combat":
        await _add_resource(db, "knowledge", settlement_output, cycle_end_time)
    elif action in ("building", "research"):
        target_building = (
            "research_lab" if action == "research" else player["action_target"]
        )
        stages_cleared = await _get_stages_cleared(db)
        await _add_building_xp(db, target_building, settlement_output, stages_cleared, cycle_end_time)

    # Stage progress uses pre-penalty output
    new_stages_cleared = await _add_stage_progress(db, action, output, cycle_end_time)

    # If upgrade stage was cleared, re-check all building upgrade eligibility
    if new_stages_cleared is not None and new_stages_cleared % 5 == 0:
        await _check_all_building_upgrades(db, new_stages_cleared, cycle_end_time)

    # Material drop
    await _roll_material(db, user_id, action, cycle_end_time)

    # Update player cycle timestamps
    if update_timestamps:
        new_completion = _dt_str(
            cycle_end_time + timedelta(minutes=get_env_int("ACTION_CYCLE_MINUTES"))
        )
        await db.execute(
            "UPDATE players SET last_update_time=?, completion_time=?, updated_at=? WHERE user_id=?",
            (_dt_str(cycle_end_time), new_completion, _dt_str(cycle_end_time), user_id),
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

        completion_time = _parse_dt(player["completion_time"])
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

    async with get_connection() as db:
        player = await _read_player(db, user_id)
        if player is None:
            return

        old_action = player["action"]
        completion_time_str = player["completion_time"]
        last_update_time_str = player["last_update_time"]

        # Step 1: Catch-up full cycles for old action
        if old_action is not None and completion_time_str is not None:
            completion_time = _parse_dt(completion_time_str)
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
            last_update = _parse_dt(last_update_time_str)
            cycle_secs = get_env_int("ACTION_CYCLE_MINUTES") * 60
            elapsed = (now - last_update).total_seconds()
            ratio = min(max(elapsed / cycle_secs, 0.0), 1.0)

            costs = action_costs(old_action)
            shortage_flag = False
            for resource, cost in costs.items():
                partial_cost = math.floor(cost * ratio)
                current = await _get_resource(db, resource)
                if current < partial_cost:
                    shortage_flag = True
                await _set_resource(db, resource, max(0, current - partial_cost), now)

            output = await compute_output(db, user_id, old_action)
            partial_output = math.floor(output * ratio)
            settlement_output = math.floor(partial_output * 0.5) if shortage_flag else partial_output

            if old_action == "gathering":
                await _add_resource(db, "food", settlement_output, now)
                await _add_resource(db, "wood", settlement_output, now)
            elif old_action == "combat":
                await _add_resource(db, "knowledge", settlement_output, now)
            elif old_action in ("building", "research"):
                target_building = (
                    "research_lab" if old_action == "research" else player["action_target"]
                )
                stages_cleared = await _get_stages_cleared(db)
                await _add_building_xp(db, target_building, settlement_output, stages_cleared, now)

            # Stage progress uses pre-penalty partial_output; no material drop for partial
            await _add_stage_progress(db, old_action, partial_output, now)

        # Step 3: Write new action and reset cycle timing
        now_str = _dt_str(now)
        actual_target = new_target if new_action == "building" else None
        if new_action is not None:
            new_completion = _dt_str(now + timedelta(minutes=get_env_int("ACTION_CYCLE_MINUTES")))
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

        ap = await _get_ap(db, user_id, now)
        if ap < 1:
            return False

        await _spend_ap(db, user_id, 1, now)

        for _ in range(3):
            await _run_one_cycle(db, user_id, now, update_timestamps=False)

        await db.commit()
        return True

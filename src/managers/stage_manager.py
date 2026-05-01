"""
stage_manager — five-stage loop, progress, overtime, and clear logic.

All functions accept an open aiosqlite connection.
The caller is responsible for committing the transaction.
"""

import math
from datetime import datetime

from core.config import get_env_float, get_env_int
from core.utils import dt_str, parse_dt

STAGE_TYPES = ("gathering", "building", "combat", "research", "upgrade")


def compute_stage_target(stages_cleared: int) -> int:
    """
    Return the progress target for the stage that begins after stages_cleared clears.
    stages_cleared is the count AFTER the most recent clear.
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


async def get_stages_cleared(db) -> int:
    """Return the total number of stages cleared so far."""
    async with db.execute("SELECT stages_cleared FROM stage_state WHERE id=1") as cur:
        row = await cur.fetchone()
    return row[0] if row else 0


async def get_stage_info(db) -> dict:
    """Return full current stage state as a dict."""
    async with db.execute("SELECT * FROM stage_state WHERE id=1") as cur:
        row = await cur.fetchone()
        if row is None:
            return {}
        cols = [d[0] for d in cur.description]
        return dict(zip(cols, row))


async def add_progress(
    db, action: str, output: int, effective_time: datetime
) -> int | None:
    """
    Add output to stage progress if the action type is relevant to the current stage.
    - Normal stage: only the matching action type counts.
    - Upgrade stage (index 4): all action types count.
    Applies STAGE_OVERTIME_PROGRESS_MULTIPLIER if the stage is in overtime.
    Excess progress on clear is discarded. At most one stage clear per call.

    Returns new stages_cleared (int) if a stage was cleared, else None.
    """
    async with db.execute("SELECT * FROM stage_state WHERE id=1") as cur:
        row = await cur.fetchone()
        if row is None:
            return None
        cols = [d[0] for d in cur.description]
        state = dict(zip(cols, row))

    stage_type = state["current_stage_type"]

    if stage_type == "upgrade":
        counts = True
    else:
        counts = action == stage_type

    if not counts:
        return None

    stage_started = parse_dt(state["stage_started_at"])
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
    now_str = dt_str(effective_time)

    if new_progress >= target:
        new_stages_cleared = state["stages_cleared"] + 1
        new_stage_index = new_stages_cleared % 5
        new_stage_type = STAGE_TYPES[new_stage_index]
        new_target = compute_stage_target(new_stages_cleared)
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

"""
trial_manager — global village trial: open, progress, timeout, and reward distribution.

All functions accept an open aiosqlite connection.
The caller is responsible for committing the transaction.
"""

import math
import random
from datetime import datetime

from core.config import get_env_int
from core.utils import dt_str, parse_dt
from managers import player_manager, resource_manager

TRIAL_RESOURCE_TYPES = ("food", "wood", "knowledge")


class TrialStartError(ValueError):
    """Raised when a trial cannot be started for a known business reason."""

    _REASONS = {"active", "cooldown", "invalid_target", "stale_target"}

    def __init__(self, reason: str):
        if reason not in self._REASONS:
            raise ValueError(f"Unknown trial start reason: {reason}")
        self.reason = reason
        super().__init__(reason)


def get_cooldown_deadline_unix(ended_at_str: str | None) -> int | None:
    """Return the unix timestamp when the trial cooldown ends, or None if not on cooldown."""
    if not ended_at_str:
        return None

    cooldown = get_env_int("TRIAL_COOLDOWN_SECONDS")
    return int(parse_dt(ended_at_str).timestamp()) + cooldown


def is_cooldown_active(ended_at_str: str | None, now: datetime) -> bool:
    """Return whether the trial cooldown is still in effect at `now`."""
    if not ended_at_str:
        return False

    cooldown = get_env_int("TRIAL_COOLDOWN_SECONDS")
    elapsed = (now - parse_dt(ended_at_str)).total_seconds()
    return elapsed < cooldown


async def get_trial_info(db) -> dict:
    """Return the full current trial_state row as a dict."""
    async with db.execute("SELECT * FROM trial_state WHERE id=1") as cur:
        row = await cur.fetchone()
        if row is None:
            return {}
        cols = [d[0] for d in cur.description]
        return dict(zip(cols, row))


async def get_contribution(db, user_id: str) -> int:
    """Return the player's accumulated contribution in the current trial."""
    async with db.execute(
        "SELECT contribution FROM trial_contributions WHERE user_id=?", (user_id,)
    ) as cur:
        row = await cur.fetchone()
    return row[0] if row else 0


async def _clear_contributions(db) -> None:
    await db.execute("DELETE FROM trial_contributions")


def get_max_trial_target(resources: dict[str, int]) -> int:
    """Return the largest configured target supported after reserving each resource."""
    step = get_env_int("TRIAL_TARGET_STEP")
    reserve = get_env_int("TRIAL_RESOURCE_RESERVE")
    available = [max(resources.get(resource_type, 0) - reserve, 0) for resource_type in TRIAL_RESOURCE_TYPES]
    if step <= 0:
        return 0
    return max(available) // step * step


async def get_eligible_resource_types(db, target: int) -> list[str]:
    """Return resources whose balance can pay target while preserving the reserve."""
    reserve = get_env_int("TRIAL_RESOURCE_RESERVE")
    eligible = []
    for resource_type in TRIAL_RESOURCE_TYPES:
        if await resource_manager.balance(db, resource_type) - reserve >= target:
            eligible.append(resource_type)
    return eligible


async def start_trial(db, now: datetime, target: int) -> dict:
    """
    Open a new village trial at target. The resource type is chosen uniformly at random
    among resources that can pay target while preserving the reserve.

    Preconditions (raises TrialStartError if unmet; no resources are spent on failure):
      - no trial is currently active
      - TRIAL_COOLDOWN_SECONDS has elapsed since the last trial ended (if any)
      - target is a positive multiple of TRIAL_TARGET_STEP
      - target is no greater than the latest maximum target

    Returns the new trial_state dict.
    """
    try:
        await db.execute("BEGIN IMMEDIATE")
        info = await get_trial_info(db)
        if info.get("is_active"):
            raise TrialStartError("active")

        if is_cooldown_active(info.get("ended_at"), now):
            raise TrialStartError("cooldown")

        step = get_env_int("TRIAL_TARGET_STEP")
        if not isinstance(target, int) or isinstance(target, bool) or target <= 0 or step <= 0 or target % step:
            raise TrialStartError("invalid_target")

        resources = {
            resource_type: await resource_manager.balance(db, resource_type)
            for resource_type in TRIAL_RESOURCE_TYPES
        }
        max_target = get_max_trial_target(resources)
        if target > max_target:
            raise TrialStartError("stale_target")

        eligible = await get_eligible_resource_types(db, target)
        resource_type = random.choice(eligible)

        await resource_manager.withdraw(db, resource_type, target, now)
        await _clear_contributions(db)

        now_str = dt_str(now)
        await db.execute(
            """UPDATE trial_state SET
               is_active=1, resource_type=?, target=?, progress=0,
               started_at=?, updated_at=?
               WHERE id=1""",
            (resource_type, target, now_str, now_str),
        )
        return await get_trial_info(db)
    except Exception:
        await db.rollback()
        raise


async def _fail_trial(db, info: dict, ended_at: datetime) -> dict:
    """Mark the active trial as failed (timeout). Resources are not refunded."""
    now_str = dt_str(ended_at)
    await db.execute(
        "UPDATE trial_state SET is_active=0, ended_at=?, updated_at=? WHERE id=1",
        (now_str, now_str),
    )
    await _clear_contributions(db)
    return {
        "type": "trial_fail",
        "target": info["target"],
        "resource_type": info["resource_type"],
        "progress": info["progress"],
    }


async def _succeed_trial(db, info: dict, ended_at: datetime) -> dict:
    """Distribute rewards by contribution ratio (ceil per participant) and close the trial."""
    async with db.execute(
        "SELECT user_id, contribution FROM trial_contributions ORDER BY contribution DESC"
    ) as cur:
        rows = await cur.fetchall()

    total_contribution = sum(contribution for _, contribution in rows)
    divisor = get_env_int("TRIAL_REWARD_DIVISOR")
    reward_pool = info["target"] / divisor

    participants = []
    total_awarded = 0
    for participant_id, contribution in rows:
        reward = math.ceil(contribution / total_contribution * reward_pool)
        if reward > 0:
            await player_manager.add_universal_material(db, participant_id, reward, ended_at)
        total_awarded += reward
        participants.append({"user_id": participant_id, "contribution": contribution, "reward": reward})

    now_str = dt_str(ended_at)
    await db.execute(
        "UPDATE trial_state SET is_active=0, ended_at=?, updated_at=? WHERE id=1",
        (now_str, now_str),
    )
    await _clear_contributions(db)

    return {
        "type": "trial_success",
        "target": info["target"],
        "resource_type": info["resource_type"],
        "total_awarded": total_awarded,
        "participants": participants,
    }


async def add_progress(db, output: int, user_id: str, effective_time: datetime) -> dict | None:
    """
    Add output to trial progress and to the player's contribution, regardless of action type.

    If effective_time is already past the trial's TRIAL_DURATION_SECONDS deadline, the trial is
    failed instead and this output is NOT counted (the trial is already over).

    Returns None (no-op or still in progress), a trial_fail event, or a trial_success event.
    """
    info = await get_trial_info(db)
    if not info.get("is_active"):
        return None

    started_at = parse_dt(info["started_at"])
    duration = get_env_int("TRIAL_DURATION_SECONDS")
    if (effective_time - started_at).total_seconds() > duration:
        return await _fail_trial(db, info, effective_time)

    now_str = dt_str(effective_time)
    new_progress = info["progress"] + output
    await db.execute(
        "UPDATE trial_state SET progress=?, updated_at=? WHERE id=1",
        (new_progress, now_str),
    )
    await db.execute(
        "INSERT OR IGNORE INTO trial_contributions (user_id, contribution, updated_at) VALUES (?, 0, ?)",
        (user_id, now_str),
    )
    await db.execute(
        "UPDATE trial_contributions SET contribution = contribution + ?, updated_at=? WHERE user_id=?",
        (output, now_str, user_id),
    )

    if new_progress >= info["target"]:
        info["progress"] = new_progress
        return await _succeed_trial(db, info, effective_time)
    return None


async def check_timeout(db, now: datetime) -> dict | None:
    """
    Watcher-tick backstop: fail the trial if it is active and past its deadline.
    Independent of any player's settlement — catches the case where no one acts at all.
    """
    info = await get_trial_info(db)
    if not info.get("is_active"):
        return None

    started_at = parse_dt(info["started_at"])
    duration = get_env_int("TRIAL_DURATION_SECONDS")
    if (now - started_at).total_seconds() > duration:
        return await _fail_trial(db, info, now)
    return None

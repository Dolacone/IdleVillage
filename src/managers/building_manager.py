"""
building_manager — four village buildings, XP, upgrade, and level cap logic.

All functions accept an open aiosqlite connection.
The caller is responsible for committing the transaction.
"""

from datetime import datetime

from core.config import get_env_int
from core.utils import dt_str

BUILDING_TYPES = ("gathering_field", "workshop", "hunting_ground", "research_lab")


def get_level_cap(stages_cleared: int) -> int:
    """Return the current building level cap: floor(stages_cleared / 5) + 1."""
    return stages_cleared // 5 + 1


async def get_level(db, building_type: str) -> int:
    """Return the current level of a building."""
    async with db.execute(
        "SELECT level FROM buildings WHERE building_type=?", (building_type,)
    ) as cur:
        row = await cur.fetchone()
    return row[0] if row else 0


async def get_xp(db, building_type: str) -> int:
    """Return the current XP progress of a building toward the next level."""
    async with db.execute(
        "SELECT xp_progress FROM buildings WHERE building_type=?", (building_type,)
    ) as cur:
        row = await cur.fetchone()
    return row[0] if row else 0


async def add_xp(
    db, building_type: str, xp: int, stages_cleared: int, ts: datetime
) -> None:
    """
    Add XP to a building and run the upgrade loop against the current level_cap.
    - If already at level_cap: clamp xp_progress to level × BUILDING_XP_PER_LEVEL.
    - Excess XP from an upgrade carries to the next level's progress bar.
    - If the new level reaches level_cap, clamp any remaining overflow.
    """
    async with db.execute(
        "SELECT level, xp_progress FROM buildings WHERE building_type=?", (building_type,)
    ) as cur:
        row = await cur.fetchone()
    if row is None:
        return

    level, xp_progress = row
    level_cap = get_level_cap(stages_cleared)
    xp_per = get_env_int("BUILDING_XP_PER_LEVEL")

    if level >= level_cap:
        clamped = min(xp_progress + xp, level * xp_per)
        await db.execute(
            "UPDATE buildings SET xp_progress=?, updated_at=? WHERE building_type=?",
            (clamped, dt_str(ts), building_type),
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

    if level >= level_cap:
        xp_progress = min(xp_progress, level * xp_per)

    await db.execute(
        "UPDATE buildings SET level=?, xp_progress=?, updated_at=? WHERE building_type=?",
        (level, xp_progress, dt_str(ts), building_type),
    )


async def check_all_upgrades(db, stages_cleared: int, ts: datetime) -> None:
    """
    Re-check every building for upgrade eligibility.
    Called after the level_cap increases (upgrade stage cleared).
    Adding 0 XP triggers the upgrade loop without changing accumulated progress.
    """
    for building_type in BUILDING_TYPES:
        await add_xp(db, building_type, 0, stages_cleared, ts)

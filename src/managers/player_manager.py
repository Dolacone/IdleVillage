"""
player_manager — AP model, material balances, gear levels, and pity counters.

All functions accept an open aiosqlite connection.
The caller is responsible for committing the transaction.
"""

import math
from datetime import datetime, timedelta

from core.config import get_env_int
from core.formula import ACTION_GEAR_COL, ACTION_MATERIAL_COL
from core.utils import dt_str, parse_dt

GEAR_TYPES = ("gathering", "building", "combat", "research")


# ---------------------------------------------------------------------------
# AP helpers
# ---------------------------------------------------------------------------

async def get_ap(db, user_id: str, now: datetime) -> int:
    """
    Derive current AP from ap_full_time.
    Returns AP_CAP when ap_full_time is in the past, otherwise computes the
    number of AP already recovered: AP_CAP - ceil(remaining_seconds / recovery_seconds).
    """
    async with db.execute(
        "SELECT ap_full_time FROM players WHERE user_id=?", (user_id,)
    ) as cur:
        row = await cur.fetchone()
    if row is None:
        return 0
    ap_cap = get_env_int("AP_CAP")
    ap_full_time = parse_dt(row[0])
    if now >= ap_full_time:
        return ap_cap
    recovery_mins = get_env_int("AP_RECOVERY_MINUTES")
    remaining_secs = (ap_full_time - now).total_seconds()
    remaining_ap = math.ceil(remaining_secs / (recovery_mins * 60))
    return max(0, ap_cap - remaining_ap)


async def spend_ap(db, user_id: str, amount: int, now: datetime) -> None:
    """
    Deduct AP by extending ap_full_time.
    New ap_full_time = max(now, current_ap_full_time) + amount × AP_RECOVERY_MINUTES.
    """
    async with db.execute(
        "SELECT ap_full_time FROM players WHERE user_id=?", (user_id,)
    ) as cur:
        row = await cur.fetchone()
    if row is None:
        return
    recovery_mins = get_env_int("AP_RECOVERY_MINUTES")
    ap_full_time = parse_dt(row[0])
    new_ap_full_time = max(now, ap_full_time) + timedelta(minutes=amount * recovery_mins)
    await db.execute(
        "UPDATE players SET ap_full_time=?, updated_at=? WHERE user_id=?",
        (dt_str(new_ap_full_time), dt_str(now), user_id),
    )


# ---------------------------------------------------------------------------
# Material helpers
# ---------------------------------------------------------------------------

async def add_material(db, user_id: str, gear_type: str, amount: int, ts: datetime) -> None:
    """Add amount to the player's material balance for the given gear type."""
    col = ACTION_MATERIAL_COL[gear_type]
    await db.execute(
        f"UPDATE players SET {col} = {col} + ?, updated_at=? WHERE user_id=?",
        (amount, dt_str(ts), user_id),
    )


async def spend_material(
    db, user_id: str, gear_type: str, amount: int, ts: datetime
) -> bool:
    """
    Deduct amount from the player's material balance.
    Returns True if successful, False if insufficient materials.
    """
    col = ACTION_MATERIAL_COL[gear_type]
    async with db.execute(
        f"SELECT {col} FROM players WHERE user_id=?", (user_id,)
    ) as cur:
        row = await cur.fetchone()
    if row is None or row[0] < amount:
        return False
    await db.execute(
        f"UPDATE players SET {col} = {col} - ?, updated_at=? WHERE user_id=?",
        (amount, dt_str(ts), user_id),
    )
    return True


# ---------------------------------------------------------------------------
# Gear level helpers
# ---------------------------------------------------------------------------

async def get_gear_level(db, user_id: str, gear_type: str) -> int:
    """Return the player's current gear level for the given type."""
    col = ACTION_GEAR_COL[gear_type]
    async with db.execute(
        f"SELECT {col} FROM players WHERE user_id=?", (user_id,)
    ) as cur:
        row = await cur.fetchone()
    return row[0] if row else 0


async def set_gear_level(
    db, user_id: str, gear_type: str, level: int, ts: datetime
) -> None:
    """Set the player's gear level for the given type."""
    col = ACTION_GEAR_COL[gear_type]
    await db.execute(
        f"UPDATE players SET {col}=?, updated_at=? WHERE user_id=?",
        (level, dt_str(ts), user_id),
    )


# ---------------------------------------------------------------------------
# Pity helpers
# ---------------------------------------------------------------------------

async def get_pity(db, user_id: str, gear_type: str) -> int:
    """Return the player's current pity counter for the given gear type."""
    col = f"pity_{gear_type}"
    async with db.execute(
        f"SELECT {col} FROM players WHERE user_id=?", (user_id,)
    ) as cur:
        row = await cur.fetchone()
    return row[0] if row else 0


async def set_pity(
    db, user_id: str, gear_type: str, count: int, ts: datetime
) -> None:
    """Set the player's pity counter for the given gear type."""
    col = f"pity_{gear_type}"
    await db.execute(
        f"UPDATE players SET {col}=?, updated_at=? WHERE user_id=?",
        (count, dt_str(ts), user_id),
    )

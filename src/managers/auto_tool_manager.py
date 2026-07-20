"""
auto_tool_manager — per-tool background action streams ("auto-tools").

A player may run up to one auto-tool per tool type, provided that tool is not their
current manual action and not already an auto-tool.

Material is spent pay-as-you-go, not prepaid: `start` spends exactly 1 of the tool's own
material (no universal-material fallback) to cover the first hour, and settlement deducts
1 more at each subsequent hour boundary (`next_material_time`). Remaining runtime is a
player-set clock (`expires_at`), decoupled from materials and adjustable via add_time /
subtract_time (which never touch materials); it is capped at AUTO_TOOL_MAX_HOURS hours.
Running out of material at an hour tick stops the tool. While active it settles on its own
cycle timer, fully equivalent to a manual action (see core/settlement.settle_auto_tool_cycles).

All functions accept an open aiosqlite connection; the caller commits. This module must
NOT import core.settlement (settlement imports this module) — cycle timing comes from
core.formula.effective_cycle_seconds.
"""

from datetime import datetime, timedelta
import math

from core.config import get_env_int
from core.formula import VALID_ACTIONS, effective_cycle_seconds
from core.utils import dt_str, parse_dt
from managers import affix_manager

TOOL_TYPES = VALID_ACTIONS
BUILD_TARGETS = ("gathering_field", "workshop", "hunting_ground")

_MATERIAL_COL = {
    "gathering": "materials_gathering",
    "building": "materials_building",
    "combat": "materials_combat",
    "research": "materials_research",
}


def _seconds_per_material() -> int:
    return get_env_int("AUTO_TOOL_SECONDS_PER_MATERIAL")


def _max_hours() -> int:
    return get_env_int("AUTO_TOOL_MAX_HOURS")


def _cap_seconds() -> int:
    return _seconds_per_material() * _max_hours()


def max_add_hours(expires_at_str: str | None, now: datetime) -> int:
    """
    Whole hours that may still be added to remaining time without exceeding the runtime cap.

    max_add = floor((cap_seconds - remaining_seconds) / seconds_per_material), floored at 0.
    remaining_seconds = max(0, expires_at - now); for a fresh activation (no row) pass None
    -> remaining 0 -> max_add == AUTO_TOOL_MAX_HOURS.
    """
    per = _seconds_per_material()
    remaining = 0.0
    if expires_at_str:
        remaining = max(0.0, (parse_dt(expires_at_str) - now).total_seconds())
    return max(0, math.floor((_cap_seconds() - remaining) / per))


def max_subtract_hours(expires_at_str: str | None, now: datetime) -> int:
    """
    Whole-hour steps offered for reducing remaining time; the largest step stops the tool.

    max_sub = ceil(remaining_seconds / seconds_per_material). Reducing by any step whose
    seconds >= remaining stops the tool (remaining -> 0); the top step always does.
    """
    if not expires_at_str:
        return 0
    per = _seconds_per_material()
    remaining = max(0.0, (parse_dt(expires_at_str) - now).total_seconds())
    return max(0, math.ceil(remaining / per))


async def get(db, user_id: str, tool_type: str) -> dict | None:
    """Return the active auto-tool row for (user_id, tool_type), or None."""
    async with db.execute(
        "SELECT * FROM player_auto_tools WHERE user_id=? AND tool_type=?",
        (user_id, tool_type),
    ) as cur:
        row = await cur.fetchone()
        if row is None:
            return None
        cols = [d[0] for d in cur.description]
        return dict(zip(cols, row))


async def list_active(db, user_id: str) -> list[dict]:
    """Return all active auto-tool rows for the player, ordered by tool_type."""
    async with db.execute(
        "SELECT * FROM player_auto_tools WHERE user_id=? ORDER BY tool_type",
        (user_id,),
    ) as cur:
        rows = await cur.fetchall()
        cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in rows]


async def get_active_tool_types(db, user_id: str) -> set[str]:
    """Return the set of tool types currently running as auto-tools for the player."""
    async with db.execute(
        "SELECT tool_type FROM player_auto_tools WHERE user_id=?", (user_id,)
    ) as cur:
        rows = await cur.fetchall()
    return {r[0] for r in rows}


async def is_active(db, user_id: str, tool_type: str) -> bool:
    """Return whether the given tool is currently an active auto-tool."""
    async with db.execute(
        "SELECT 1 FROM player_auto_tools WHERE user_id=? AND tool_type=?",
        (user_id, tool_type),
    ) as cur:
        return await cur.fetchone() is not None


async def get_idle_tools(db, user_id: str) -> list[str]:
    """Return tool types that are neither the player's manual action nor an active auto-tool."""
    async with db.execute("SELECT action FROM players WHERE user_id=?", (user_id,)) as cur:
        row = await cur.fetchone()
    manual = row[0] if row else None
    active = await get_active_tool_types(db, user_id)
    return [t for t in TOOL_TYPES if t != manual and t not in active]


async def _spend_own_material(db, user_id: str, tool_type: str, count: int, now_str: str) -> None:
    """Atomically deduct `count` of the tool's own material; raise if insufficient.

    Uses a conditional UPDATE (WHERE balance >= count) so the check and the decrement are
    one statement. Auto-tools never draw on universal material.
    """
    col = _MATERIAL_COL[tool_type]
    spent = await db.execute(
        f"UPDATE players SET {col} = {col} - ?, updated_at=? WHERE user_id=? AND {col} >= ?",
        (count, now_str, user_id, count),
    )
    if spent.rowcount != 1:
        raise ValueError(f"Insufficient {tool_type} material: need {count}")


async def start(
    db, user_id: str, tool_type: str, hours: int, action_target: str | None, now: datetime
) -> None:
    """
    Activate an auto-tool for tool_type with `hours` of initial remaining time.

    Spends exactly 1 of the tool's own material up front (covers the first hour, t=0);
    subsequent hours are charged by settlement at each `next_material_time` tick.

    Raises ValueError if: tool_type invalid; hours out of [1, AUTO_TOOL_MAX_HOURS]; building
    target invalid; tool is the player's manual action or already an auto-tool; the player
    holds no unit of that material. The exclusion is enforced race-safely by a conditional
    INSERT (its WHERE NOT EXISTS / action-distinct predicate is evaluated against committed
    state after acquiring the write lock), so a concurrent manual-action change cannot
    double-assign.
    """
    if tool_type not in TOOL_TYPES:
        raise ValueError(f"Invalid tool_type: {tool_type!r}")
    if hours < 1 or hours > max_add_hours(None, now):
        raise ValueError(f"Invalid hours: {hours}")

    effective_target = _resolve_target(tool_type, action_target)  # validates building target
    per = _seconds_per_material()
    now_str = dt_str(now)
    expires_at = dt_str(now + timedelta(seconds=hours * per))
    next_material_time = dt_str(now + timedelta(seconds=per))

    # Acquire the write lock before the guard reads so concurrent start/add/subtract/
    # change_action serialize (Architecture Decision #7); the caller commits on success. On
    # failure we roll back so the caller's connection is left clean (no dangling transaction).
    await db.execute("BEGIN IMMEDIATE")
    try:
        # cycle_time_reduce affix scoped to this tool, mirroring manual-action timing.
        bonuses = await affix_manager.get_affix_bonuses(db, user_id, tool_type)
        completion_time = dt_str(now + timedelta(seconds=effective_cycle_seconds(bonuses["cycle_time_reduce"])))

        # Race-safe exclusion: insert only if no existing auto-tool for this tool AND the
        # player's manual action is a different tool (or None). SQLite `IS NOT` is null-safe.
        cur = await db.execute(
            """
            INSERT INTO player_auto_tools
                (user_id, tool_type, action_target, completion_time, last_update_time,
                 expires_at, started_at, next_material_time, updated_at)
            SELECT ?, ?, ?, ?, ?, ?, ?, ?, ?
            WHERE NOT EXISTS (
                    SELECT 1 FROM player_auto_tools WHERE user_id=? AND tool_type=?
                  )
              AND (SELECT action FROM players WHERE user_id=?) IS NOT ?
              AND EXISTS (SELECT 1 FROM players WHERE user_id=?)
            """,
            (
                user_id, tool_type, effective_target, completion_time, now_str,
                expires_at, now_str, next_material_time, now_str,
                user_id, tool_type,
                user_id, tool_type,
                user_id,
            ),
        )
        if cur.rowcount != 1:
            raise ValueError(
                f"Cannot start auto-tool {tool_type!r}: tool is in use (manual action or already auto) "
                f"or player not found"
            )

        # First hour's material (t=0). Pay-as-you-go; the rest is charged by settlement.
        await _spend_own_material(db, user_id, tool_type, 1, now_str)
    except Exception:
        await db.rollback()
        raise


async def add_time(db, user_id: str, tool_type: str, hours: int, now: datetime) -> None:
    """
    Extend a running auto-tool's remaining time by `hours` hours. Spends NO material
    (material is charged hourly by settlement, not on adjustment).

    Raises ValueError if the tool is not active or hours is out of [1, max_add_hours].
    New remaining time never exceeds the cap because hours <= max_add_hours.
    """
    # Write lock first so a concurrent add/subtract/start re-reads the committed expires_at
    # and its cap check sees the true remaining time (Architecture Decision #7). On failure
    # roll back so the caller's connection has no dangling open transaction.
    await db.execute("BEGIN IMMEDIATE")
    try:
        row = await get(db, user_id, tool_type)
        if row is None:
            raise ValueError(f"Auto-tool {tool_type!r} is not active")
        if hours < 1 or hours > max_add_hours(row["expires_at"], now):
            raise ValueError(f"Invalid add hours: {hours}")

        now_str = dt_str(now)
        per = _seconds_per_material()
        new_expires = dt_str(parse_dt(row["expires_at"]) + timedelta(seconds=hours * per))
        await db.execute(
            "UPDATE player_auto_tools SET expires_at=?, updated_at=? WHERE user_id=? AND tool_type=?",
            (new_expires, now_str, user_id, tool_type),
        )
    except Exception:
        await db.rollback()
        raise


async def subtract_time(db, user_id: str, tool_type: str, hours: int, now: datetime) -> None:
    """
    Reduce a running auto-tool's remaining time by `hours` hours. Spends/refunds NO material.

    If the reduction meets or exceeds the remaining time, the tool stops (row deleted) —
    reducing to the bottom is how a player stops an auto-tool. Raises ValueError if the tool
    is not active or hours < 1.
    """
    # Write lock first so this serializes with concurrent add/subtract/start and with the
    # settlement's expires_at read / end() decision (Architecture Decision #7).
    await db.execute("BEGIN IMMEDIATE")
    try:
        if hours < 1:
            raise ValueError(f"Invalid subtract hours: {hours}")
        row = await get(db, user_id, tool_type)
        if row is None:
            raise ValueError(f"Auto-tool {tool_type!r} is not active")

        per = _seconds_per_material()
        now_str = dt_str(now)
        remaining = (parse_dt(row["expires_at"]) - now).total_seconds()
        if hours * per >= remaining:
            await end(db, user_id, tool_type)  # reduce-to-bottom stops the tool
        else:
            new_expires = dt_str(parse_dt(row["expires_at"]) - timedelta(seconds=hours * per))
            await db.execute(
                "UPDATE player_auto_tools SET expires_at=?, updated_at=? WHERE user_id=? AND tool_type=?",
                (new_expires, now_str, user_id, tool_type),
            )
    except Exception:
        await db.rollback()
        raise


async def advance_cycle(
    db, user_id: str, tool_type: str, cycle_end_time: datetime, next_completion: datetime
) -> None:
    """Record that a cycle ending at cycle_end_time settled; set the next completion_time."""
    ts = dt_str(cycle_end_time)
    await db.execute(
        """UPDATE player_auto_tools
           SET last_update_time=?, completion_time=?, updated_at=?
           WHERE user_id=? AND tool_type=?""",
        (ts, dt_str(next_completion), ts, user_id, tool_type),
    )


async def advance_material_tick(
    db, user_id: str, tool_type: str, next_material_time: datetime
) -> None:
    """Record the next hour boundary at which a material will be charged."""
    ts = dt_str(next_material_time)
    await db.execute(
        """UPDATE player_auto_tools
           SET next_material_time=?, updated_at=?
           WHERE user_id=? AND tool_type=?""",
        (ts, ts, user_id, tool_type),
    )


async def end(db, user_id: str, tool_type: str) -> None:
    """Stop an auto-tool and free the tool (delete its row)."""
    await db.execute(
        "DELETE FROM player_auto_tools WHERE user_id=? AND tool_type=?",
        (user_id, tool_type),
    )


def _resolve_target(tool_type: str, action_target: str | None) -> str | None:
    """Building auto-tools require a valid build target; research maps to research_lab."""
    if tool_type == "research":
        return "research_lab"
    if tool_type == "building":
        if action_target not in BUILD_TARGETS:
            raise ValueError(f"Invalid building target: {action_target!r}. Must be one of {BUILD_TARGETS}")
        return action_target
    return None

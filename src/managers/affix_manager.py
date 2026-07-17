"""
affix_manager — tool affix slot management, extraction, and bonus aggregation.

All functions accept an open aiosqlite connection.
The caller is responsible for committing the transaction.
"""

import math
import random
from datetime import datetime

from core.config import get_env_int
from core.formula import ACTION_MATERIAL_COL
from core.utils import dt_str
from managers import player_manager

GEAR_TYPES = ("gathering", "building", "combat", "research")
AFFIX_TYPES = (
    "efficiency",
    "material_drop",
    "upgrade_success",
    "upgrade_cost_reduce",
    "upgrade_ap_refund",
    "upgrade_material_refund",
    "cycle_time_reduce",
)
AFFIX_VALUE_MIN = 1
AFFIX_VALUE_MAX = 5


def slot_count(gear_level: int) -> int:
    """Return number of unlocked affix slots for a given gear level."""
    interval = get_env_int("AFFIX_SLOT_INTERVAL")
    return math.floor(gear_level / interval)


async def get_affixes(db, user_id: str, gear_type: str) -> list[dict]:
    """Return list of {slot_index, affix_type, value} for all filled slots."""
    async with db.execute(
        "SELECT slot_index, affix_type, value FROM gear_affixes "
        "WHERE user_id=? AND gear_type=? ORDER BY slot_index",
        (user_id, gear_type),
    ) as cur:
        rows = await cur.fetchall()
    return [{"slot_index": r[0], "affix_type": r[1], "value": r[2]} for r in rows]


async def get_affix_bonuses(db, user_id: str, gear_type: str) -> dict[str, int]:
    """Return aggregated bonus values by affix type (same-type affixes stack)."""
    bonuses = {t: 0 for t in AFFIX_TYPES}
    affixes = await get_affixes(db, user_id, gear_type)
    for a in affixes:
        bonuses[a["affix_type"]] += a["value"]
    return bonuses


async def extract_affix(db, user_id: str, gear_type: str, gear_level: int, now: datetime) -> dict:
    """
    Extract one affix into the first empty slot.

    Costs AFFIX_EXTRACT_COST of the corresponding material; own-type material is
    spent first, any shortfall is drawn from universal material.
    Raises ValueError if:
      - gear_type is invalid
      - no slots unlocked (gear_level < AFFIX_SLOT_INTERVAL)
      - all unlocked slots are filled
      - own-type + universal materials are insufficient
    Returns {slot_index, affix_type, value}.
    """
    if gear_type not in GEAR_TYPES:
        raise ValueError(f"Invalid gear_type: {gear_type!r}")

    slots = slot_count(gear_level)
    if slots == 0:
        raise ValueError(f"No affix slots unlocked at gear level {gear_level}")

    existing = await get_affixes(db, user_id, gear_type)
    filled = {a["slot_index"] for a in existing}
    empty_slot = next((i for i in range(slots) if i not in filled), None)
    if empty_slot is None:
        raise ValueError("All affix slots are full; clear one before extracting")

    cost = get_env_int("AFFIX_EXTRACT_COST")
    mats = await player_manager.get_material(db, user_id, gear_type)
    universal = await player_manager.get_universal_material(db, user_id)
    if mats + universal < cost:
        raise ValueError(
            f"Insufficient materials: need {cost}, have {mats} "
            f"(+{universal} universal)"
        )
    from_type = min(cost, mats)
    if from_type > 0:
        await player_manager.spend_material(db, user_id, gear_type, from_type, now)
    shortfall = cost - from_type
    if shortfall > 0:
        await player_manager.spend_universal_material(db, user_id, shortfall, now)

    affix_type = random.choice(AFFIX_TYPES)
    value = random.randint(AFFIX_VALUE_MIN, AFFIX_VALUE_MAX)

    await db.execute(
        "INSERT INTO gear_affixes (user_id, gear_type, slot_index, affix_type, value) VALUES (?,?,?,?,?)",
        (user_id, gear_type, empty_slot, affix_type, value),
    )
    return {"slot_index": empty_slot, "affix_type": affix_type, "value": value}


async def clear_affix(db, user_id: str, gear_type: str, slot_index: int, gear_level: int, now: datetime) -> dict:
    """
    Clear the affix at slot_index.

    Costs AFFIX_CLEAR_COST of the corresponding material; own-type material is
    spent first, any shortfall is drawn from universal material.
    Raises ValueError if:
      - gear_type is invalid
      - slot_index is out of unlocked range
      - slot is empty
      - own-type + universal materials are insufficient
    Returns {affix_type, value} of the cleared affix.
    """
    if gear_type not in GEAR_TYPES:
        raise ValueError(f"Invalid gear_type: {gear_type!r}")

    slots = slot_count(gear_level)
    if slot_index < 0 or slot_index >= slots:
        raise ValueError(f"slot_index {slot_index} out of unlocked range [0, {slots})")

    existing = await get_affixes(db, user_id, gear_type)
    target = next((a for a in existing if a["slot_index"] == slot_index), None)
    if target is None:
        raise ValueError(f"Slot {slot_index} is already empty")

    cost = get_env_int("AFFIX_CLEAR_COST")
    mats = await player_manager.get_material(db, user_id, gear_type)
    universal = await player_manager.get_universal_material(db, user_id)
    if mats + universal < cost:
        raise ValueError(
            f"Insufficient materials: need {cost}, have {mats} "
            f"(+{universal} universal)"
        )
    from_type = min(cost, mats)
    if from_type > 0:
        await player_manager.spend_material(db, user_id, gear_type, from_type, now)
    shortfall = cost - from_type
    if shortfall > 0:
        await player_manager.spend_universal_material(db, user_id, shortfall, now)

    await db.execute(
        "DELETE FROM gear_affixes WHERE user_id=? AND gear_type=? AND slot_index=?",
        (user_id, gear_type, slot_index),
    )
    return {"affix_type": target["affix_type"], "value": target["value"]}


async def clear_all_affixes(db, user_id: str, gear_type: str, now: datetime) -> None:
    """Remove all affixes for this tool. No material cost. Called on risky failure."""
    await db.execute(
        "DELETE FROM gear_affixes WHERE user_id=? AND gear_type=?",
        (user_id, gear_type),
    )

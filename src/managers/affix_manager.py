"""
affix_manager — tool affix slot management, extraction, and bonus aggregation.

All functions accept an open aiosqlite connection.
The caller is responsible for committing the transaction.
"""

import asyncio
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


async def _spend_with_universal_fallback(
    db, user_id: str, gear_type: str, cost: int, now: datetime
) -> None:
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
    await _spend_with_universal_fallback(db, user_id, gear_type, cost, now)

    affix_type = random.choice(AFFIX_TYPES)
    value = random.randint(AFFIX_VALUE_MIN, AFFIX_VALUE_MAX)

    await db.execute(
        "INSERT INTO gear_affixes (user_id, gear_type, slot_index, affix_type, value) VALUES (?,?,?,?,?)",
        (user_id, gear_type, empty_slot, affix_type, value),
    )
    return {"slot_index": empty_slot, "affix_type": affix_type, "value": value}


async def auto_extract_affix(
    db, user_id: str, gear_type: str, gear_level: int, now: datetime, *,
    target_affix_type=None, min_value=1, material_source="tool", expected_slot: int | None = None,
) -> dict:
    """Draw until a target affix appears or the selected material budget runs out."""
    if gear_type not in GEAR_TYPES:
        raise ValueError(f"Invalid gear_type: {gear_type!r}")
    if not isinstance(gear_level, int) or isinstance(gear_level, bool) or gear_level < 0:
        raise ValueError(f"Invalid gear_level: {gear_level!r}")
    if target_affix_type is not None and target_affix_type not in AFFIX_TYPES:
        raise ValueError(f"Invalid target_affix_type: {target_affix_type!r}")
    if not isinstance(min_value, int) or isinstance(min_value, bool) or min_value not in range(1, 6):
        raise ValueError(f"Invalid min_value: {min_value!r}")
    if material_source not in ("tool", "universal"):
        raise ValueError(f"Invalid material_source: {material_source!r}")
    if expected_slot is not None and (
        not isinstance(expected_slot, int) or isinstance(expected_slot, bool) or expected_slot < 0
    ):
        raise ValueError(f"Invalid expected_slot: {expected_slot!r}")

    slots = slot_count(gear_level)
    if slots == 0:
        raise ValueError(f"No affix slots unlocked at gear level {gear_level}")
    existing = await get_affixes(db, user_id, gear_type)
    filled = {a["slot_index"] for a in existing}
    initial_slot = next((i for i in range(slots) if i not in filled), None)
    if initial_slot is None:
        raise ValueError("All affix slots are full; clear one before extracting")
    if expected_slot is not None and expected_slot != initial_slot:
        raise ValueError(f"Expected slot {expected_slot} does not match first empty slot {initial_slot}")

    cost_per_attempt = 1 if material_source == "tool" else 5
    initial_balance = (
        await player_manager.get_material(db, user_id, gear_type)
        if material_source == "tool"
        else await player_manager.get_universal_material(db, user_id)
    )
    initial_budget = initial_balance // cost_per_attempt
    if initial_budget < 1:
        raise ValueError("Insufficient selected material for one extraction")

    match = None
    simulated_attempts = 0
    while simulated_attempts < initial_budget:
        affix_type = random.choice(AFFIX_TYPES)
        value = random.randint(AFFIX_VALUE_MIN, AFFIX_VALUE_MAX)
        simulated_attempts += 1
        if (target_affix_type is None or affix_type == target_affix_type) and value >= min_value:
            match = {"affix_type": affix_type, "value": value}
            break
        if simulated_attempts % 100 == 0:
            await asyncio.sleep(0)

    await db.execute("BEGIN IMMEDIATE")
    actual_level = await player_manager.get_gear_level(db, user_id, gear_type)
    actual_slots = slot_count(actual_level)
    latest = await get_affixes(db, user_id, gear_type)
    latest_filled = {a["slot_index"] for a in latest}
    empty_slot = next((i for i in range(actual_slots) if i not in latest_filled), None)
    if empty_slot != initial_slot:
        raise ValueError("First empty affix slot changed during extraction")

    latest_balance = (
        await player_manager.get_material(db, user_id, gear_type)
        if material_source == "tool"
        else await player_manager.get_universal_material(db, user_id)
    )
    attempts = min(simulated_attempts, latest_balance // cost_per_attempt)
    if attempts < 1:
        raise ValueError("Insufficient selected material for one extraction")
    if simulated_attempts > attempts:
        match = None
    material_spent = attempts * cost_per_attempt
    if material_source == "tool":
        paid = await player_manager.spend_material(db, user_id, gear_type, material_spent, now)
    else:
        paid = await player_manager.spend_universal_material(db, user_id, material_spent, now)
    if not paid:
        raise ValueError("Insufficient selected material for extraction")

    affix = None
    if match is not None:
        affix = {"slot_index": empty_slot, **match}
        await db.execute(
            "INSERT INTO gear_affixes (user_id, gear_type, slot_index, affix_type, value) VALUES (?,?,?,?,?)",
            (user_id, gear_type, empty_slot, match["affix_type"], match["value"]),
        )
    return {
        "affix": affix,
        "attempts": attempts,
        "material_spent": material_spent,
        "material_source": material_source,
    }


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
    await _spend_with_universal_fallback(db, user_id, gear_type, cost, now)

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

"""
gear_manager — gear upgrade attempts, success rate, and pity system.

attempt_upgrade() and get_upgrade_info() accept an open aiosqlite connection.
The caller is responsible for committing the transaction.
"""

import random
from datetime import datetime

from core.config import get_env_float, get_env_int
from managers import building_manager, player_manager

GEAR_TYPES = ("gathering", "building", "combat", "research")


def _compute_rate(gear_level: int, pity_count: int) -> float:
    """
    Compute the final upgrade success rate.

    base_rate  = max(GEAR_MIN_SUCCESS_RATE, 1.0 - gear_level × GEAR_RATE_LOSS_PER_LEVEL)
    final_rate = min(1.0, base_rate + pity_count × GEAR_PITY_BONUS)
    """
    min_rate = get_env_float("GEAR_MIN_SUCCESS_RATE")
    loss_per = get_env_float("GEAR_RATE_LOSS_PER_LEVEL")
    pity_bonus = get_env_float("GEAR_PITY_BONUS")
    base_rate = max(min_rate, 1.0 - gear_level * loss_per)
    return min(1.0, base_rate + pity_count * pity_bonus)


async def get_upgrade_info(db, user_id: str, gear_type: str, now: datetime) -> dict:
    """
    Return upgrade preview information for the given gear type.

    Returns a dict with:
      gear_level     — current level
      target_level   — level after a successful upgrade
      material_cost  — number of materials required (= target_level)
      rate           — computed success rate (float 0.0–1.0)
      pity           — current pity counter
      ap             — current AP
      can_attempt    — True if all preconditions are met
      gear_cap       — current gear cap (research_lab level)
    """
    gear_level = await player_manager.get_gear_level(db, user_id, gear_type)
    gear_cap = await building_manager.get_level(db, "research_lab")
    ap = await player_manager.get_ap(db, user_id, now)
    pity = await player_manager.get_pity(db, user_id, gear_type)
    target_level = gear_level + 1
    material_cost = target_level
    rate = _compute_rate(gear_level, pity)

    from core.formula import ACTION_MATERIAL_COL
    mat_col = ACTION_MATERIAL_COL[gear_type]
    async with db.execute(
        f"SELECT {mat_col} FROM players WHERE user_id=?", (user_id,)
    ) as cur:
        row = await cur.fetchone()
    materials = row[0] if row else 0

    can_attempt = (
        gear_level < gear_cap
        and ap >= 1
        and materials >= material_cost
    )
    return {
        "gear_level": gear_level,
        "target_level": target_level,
        "material_cost": material_cost,
        "rate": rate,
        "pity": pity,
        "ap": ap,
        "can_attempt": can_attempt,
        "gear_cap": gear_cap,
        "materials": materials,
    }


async def attempt_upgrade(db, user_id: str, gear_type: str, now: datetime) -> dict:
    """
    Attempt a gear upgrade for the player.

    Preconditions (raises ValueError if unmet):
      - gear_level < research_lab level (gear cap)
      - player has >= 1 AP
      - player has >= target_level materials of gear_type

    Deducts 1 AP and target_level materials unconditionally (no refund on failure).
    Rolls against final_rate:
      - Success: gear_level += 1, pity reset to 0
      - Failure: pity += 1

    Returns {"success": bool, "new_level": int, "rate": float}
    """
    gear_level = await player_manager.get_gear_level(db, user_id, gear_type)
    gear_cap = await building_manager.get_level(db, "research_lab")

    if gear_level >= gear_cap:
        raise ValueError(f"Gear {gear_type!r} is already at cap (level {gear_cap})")

    ap = await player_manager.get_ap(db, user_id, now)
    if ap < 1:
        raise ValueError("Insufficient AP")

    target_level = gear_level + 1
    material_cost = target_level

    from core.formula import ACTION_MATERIAL_COL
    mat_col = ACTION_MATERIAL_COL[gear_type]
    async with db.execute(
        f"SELECT {mat_col} FROM players WHERE user_id=?", (user_id,)
    ) as cur:
        row = await cur.fetchone()
    materials = row[0] if row else 0
    if materials < material_cost:
        raise ValueError(f"Insufficient materials: need {material_cost}, have {materials}")

    # Deduct resources (non-refundable)
    await player_manager.spend_ap(db, user_id, 1, now)
    await player_manager.spend_material(db, user_id, gear_type, material_cost, now)

    # Roll
    pity = await player_manager.get_pity(db, user_id, gear_type)
    rate = _compute_rate(gear_level, pity)
    success = random.random() < rate

    if success:
        await player_manager.set_gear_level(db, user_id, gear_type, target_level, now)
        await player_manager.set_pity(db, user_id, gear_type, 0, now)
        new_level = target_level
        pity_after = 0
    else:
        await player_manager.set_pity(db, user_id, gear_type, pity + 1, now)
        new_level = gear_level
        pity_after = pity + 1

    return {
        "success": success,
        "new_level": new_level,
        "current_level": gear_level,
        "rate": rate,
        "pity_after": pity_after,
    }

"""
gear_manager — gear upgrade attempts, success rate, and pity system.

attempt_upgrade() and get_upgrade_info() accept an open aiosqlite connection.
The caller is responsible for committing the transaction.
"""

import math
import random
from datetime import datetime

from core.config import get_env_float, get_env_int
from core.formula import ACTION_MATERIAL_COL
from core.utils import dt_str
from managers import affix_manager, building_manager, player_manager

GEAR_TYPES = ("gathering", "building", "combat", "research")
UPGRADE_MODES = ("normal", "buffer", "risky")
RATE_PRECISION = 10


def _normalize_rate(rate: float) -> float:
    return round(rate, RATE_PRECISION)


def _compute_rate(gear_level: int, pity_count: int, risky_failed_levels: int = 0, mode: str = "normal") -> float:
    """
    Compute the final upgrade success rate.

    base_rate  = max(GEAR_MIN_SUCCESS_RATE, 1.0 - gear_level × GEAR_RATE_LOSS_PER_LEVEL)

    # standard / risky:
    final_rate = min(1.0, base_rate + pity_count × GEAR_PITY_BONUS + risky_failed_levels × 0.0001)

    # buffer:
    final_rate = min(1.0, base_rate + pity_count × GEAR_PITY_BONUS)
    """
    min_rate = get_env_float("GEAR_MIN_SUCCESS_RATE")
    loss_per = get_env_float("GEAR_RATE_LOSS_PER_LEVEL")
    pity_bonus = get_env_float("GEAR_PITY_BONUS")
    base_rate = max(min_rate, _normalize_rate(1.0 - gear_level * loss_per))
    rate = _normalize_rate(base_rate + pity_count * pity_bonus)
    if mode in ("normal", "risky"):
        rate = _normalize_rate(rate + risky_failed_levels * 0.0001)
    return min(1.0, rate)


def _material_cost(target_level: int, mode: str, upgrade_cost_reduce_pct: int = 0) -> int:
    """Return material cost for the given upgrade mode and target level, after affix reduction."""
    if mode == "buffer":
        base = max(1, math.ceil(target_level / 2))
    elif mode == "risky":
        base = 1
    else:
        base = target_level
    if upgrade_cost_reduce_pct > 0:
        return max(1, math.floor(base * (1 - upgrade_cost_reduce_pct / 100.0)))
    return base


async def _get_materials(db, user_id: str, gear_type: str) -> int:
    """Return the player's current material count for the given gear type."""
    mat_col = ACTION_MATERIAL_COL[gear_type]
    async with db.execute(
        f"SELECT {mat_col} FROM players WHERE user_id=?", (user_id,)
    ) as cur:
        row = await cur.fetchone()
    return row[0] if row else 0


async def _get_risky_failed_levels(db, user_id: str) -> int:
    """Return the player's current risky_failed_levels value."""
    async with db.execute(
        "SELECT risky_failed_levels FROM players WHERE user_id=?", (user_id,)
    ) as cur:
        row = await cur.fetchone()
    return row[0] if row else 0


async def _add_risky_failed_levels(db, user_id: str, amount: int, now: datetime) -> None:
    """Increment the player's risky_failed_levels by amount."""
    await db.execute(
        "UPDATE players SET risky_failed_levels = risky_failed_levels + ?, updated_at=? WHERE user_id=?",
        (amount, dt_str(now), user_id),
    )


async def sacrifice_material(db, user_id: str, gear_type: str, amount: int, now: datetime) -> dict:
    """
    Sacrifice materials to directly increase risky_failed_levels (permanent success rate bonus).

    Preconditions (raises ValueError if unmet):
      - amount >= 1
      - player has >= amount materials of the given gear_type

    Does NOT consume AP and does NOT raise any notification events.

    Returns {"type": "sacrifice", "sacrificed": amount, "gear_type": gear_type, "risky_failed_levels_after": int}.
    """
    if amount < 1:
        raise ValueError("amount must be at least 1")

    materials = await _get_materials(db, user_id, gear_type)
    if materials < amount:
        raise ValueError(f"Insufficient materials: need {amount}, have {materials}")

    risky_before = await _get_risky_failed_levels(db, user_id)
    await player_manager.spend_material(db, user_id, gear_type, amount, now)
    await _add_risky_failed_levels(db, user_id, amount, now)

    return {
        "type": "sacrifice",
        "sacrificed": amount,
        "gear_type": gear_type,
        "risky_failed_levels_after": risky_before + amount,
    }


async def get_upgrade_info(db, user_id: str, gear_type: str, now: datetime, mode: str = "normal") -> dict:
    """
    Return upgrade preview information for the given gear type and mode.

    Returns a dict with:
      gear_level     — current level
      target_level   — level after a successful upgrade
      material_cost  — number of materials required (mode-dependent)
      rate           — computed success rate (float 0.0–1.0)
      pity           — current pity counter
      ap             — current AP
      can_attempt    — True if all preconditions are met
      gear_cap       — current gear cap (research_lab level)
      mode           — upgrade mode ("normal" / "buffer" / "risky")
      [normal and risky only]
      risky_failed_levels — accumulated failed levels
      risky_bonus_pct     — bonus percentage from risky_failed_levels
    """
    if mode not in UPGRADE_MODES:
        raise ValueError(f"Invalid upgrade mode: {mode!r}")

    gear_level = await player_manager.get_gear_level(db, user_id, gear_type)
    gear_cap = await building_manager.get_level(db, "research_lab")
    ap = await player_manager.get_ap(db, user_id, now)
    pity = await player_manager.get_pity(db, user_id, gear_type)
    risky_failed_levels = await _get_risky_failed_levels(db, user_id)
    bonuses = await affix_manager.get_affix_bonuses(db, user_id, gear_type)
    target_level = gear_level + 1
    material_cost = _material_cost(target_level, mode, upgrade_cost_reduce_pct=bonuses["upgrade_cost_reduce"])
    base_rate = _compute_rate(gear_level, pity, risky_failed_levels=risky_failed_levels, mode=mode)
    rate = min(1.0, base_rate + bonuses["upgrade_success"] / 100.0)

    materials = await _get_materials(db, user_id, gear_type)

    can_attempt = (
        gear_level < gear_cap
        and ap >= 1
        and materials >= material_cost
    )
    result = {
        "gear_level": gear_level,
        "target_level": target_level,
        "material_cost": material_cost,
        "rate": rate,
        "pity": pity,
        "ap": ap,
        "can_attempt": can_attempt,
        "gear_cap": gear_cap,
        "materials": materials,
        "mode": mode,
    }
    if mode in ("normal", "risky"):
        result["risky_failed_levels"] = risky_failed_levels
        result["risky_bonus_pct"] = round(risky_failed_levels * 0.01, 2)
    return result


async def attempt_upgrade(db, user_id: str, gear_type: str, now: datetime, mode: str = "normal") -> dict:
    """
    Attempt a gear upgrade for the player.

    Preconditions (raises ValueError if unmet):
      - valid mode ("normal" / "buffer" / "risky")
      - gear_level < research_lab level (gear cap)
      - player has >= 1 AP
      - player has >= material_cost materials for the chosen mode

    Modes:
      normal — spend target_level materials, roll; success: gear+1 pity=0, failure: pity+1
      buffer — spend ceil(target_level/2) materials, no roll; pity+1 immediately
      risky  — spend 1 material, roll;
                success: gear +1, pity=0
                failure: gear=0, pity=0, risky_failed_levels += current_level

    Returns a result dict with success, new_level, level_gain, pity_before, pity_after, rate, mode.
    """
    if mode not in UPGRADE_MODES:
        raise ValueError(f"Invalid upgrade mode: {mode!r}")

    gear_level = await player_manager.get_gear_level(db, user_id, gear_type)
    gear_cap = await building_manager.get_level(db, "research_lab")

    if gear_level >= gear_cap:
        raise ValueError(f"Gear {gear_type!r} is already at cap (level {gear_cap})")

    ap = await player_manager.get_ap(db, user_id, now)
    if ap < 1:
        raise ValueError("Insufficient AP")

    target_level = gear_level + 1
    bonuses = await affix_manager.get_affix_bonuses(db, user_id, gear_type)
    material_cost = _material_cost(target_level, mode, upgrade_cost_reduce_pct=bonuses["upgrade_cost_reduce"])

    materials = await _get_materials(db, user_id, gear_type)
    if materials < material_cost:
        raise ValueError(f"Insufficient materials: need {material_cost}, have {materials}")

    await player_manager.spend_ap(db, user_id, 1, now)
    await player_manager.spend_material(db, user_id, gear_type, material_cost, now)

    pity = await player_manager.get_pity(db, user_id, gear_type)
    risky_failed_levels = await _get_risky_failed_levels(db, user_id)
    base_rate = _compute_rate(gear_level, pity, risky_failed_levels=risky_failed_levels, mode=mode)
    rate = min(1.0, base_rate + bonuses["upgrade_success"] / 100.0)

    if mode == "buffer":
        await player_manager.set_pity(db, user_id, gear_type, pity + 1, now)
        return {
            "success": False,
            "new_level": gear_level,
            "level_gain": 0,
            "current_level": gear_level,
            "target_level": target_level,
            "rate": rate,
            "pity_before": pity,
            "pity_after": pity + 1,
            "mode": mode,
        }

    success = random.random() < rate

    ap_refunded = False
    material_refunded = False

    if success:
        level_gain = 1
        new_level = gear_level + level_gain
        await player_manager.set_gear_level(db, user_id, gear_type, new_level, now)
        await player_manager.set_pity(db, user_id, gear_type, 0, now)
        pity_after = 0
        if bonuses["upgrade_ap_refund"] > 0 and random.random() < bonuses["upgrade_ap_refund"] / 100.0:
            await player_manager.refund_ap(db, user_id, 1, now)
            ap_refunded = True
        if bonuses["upgrade_material_refund"] > 0 and random.random() < bonuses["upgrade_material_refund"] / 100.0:
            await player_manager.add_material(db, user_id, gear_type, material_cost, now)
            material_refunded = True
    elif mode == "risky":
        await _add_risky_failed_levels(db, user_id, gear_level, now)
        await player_manager.set_gear_level(db, user_id, gear_type, 0, now)
        await player_manager.set_pity(db, user_id, gear_type, 0, now)
        await affix_manager.clear_all_affixes(db, user_id, gear_type, now)
        new_level = 0
        level_gain = 0
        pity_after = 0
    else:
        await player_manager.set_pity(db, user_id, gear_type, pity + 1, now)
        new_level = gear_level
        level_gain = 0
        pity_after = pity + 1

    return {
        "success": success,
        "new_level": new_level,
        "level_gain": level_gain,
        "current_level": gear_level,
        "target_level": target_level,
        "rate": rate,
        "pity_before": pity,
        "pity_after": pity_after,
        "mode": mode,
        "ap_refunded": ap_refunded,
        "material_refunded": material_refunded,
    }

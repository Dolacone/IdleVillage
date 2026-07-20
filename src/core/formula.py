"""
formula.py — action output calculations and action config maps.
All balance values are read from environment variables at call time.
"""

import math

from core.config import get_env_float, get_env_int

VALID_ACTIONS = ("gathering", "building", "combat", "research")

# Stage type stored values by index 0–4. Index 4 is the upgrade stage.
STAGE_TYPES = ("gathering", "building", "combat", "research", "upgrade")

# players column that holds gear level per action
ACTION_GEAR_COL = {
    "gathering": "gear_gathering",
    "building": "gear_building",
    "combat": "gear_combat",
    "research": "gear_research",
}

# players column that holds material count per action
ACTION_MATERIAL_COL = {
    "gathering": "materials_gathering",
    "building": "materials_building",
    "combat": "materials_combat",
    "research": "materials_research",
}

# buildings row that acts as facility per action
ACTION_FACILITY_BUILDING = {
    "gathering": "gathering_field",
    "building": "workshop",
    "combat": "hunting_ground",
    "research": "research_lab",
}


def effective_cycle_seconds(cycle_time_reduce_pct: int = 0) -> int:
    """Return effective cycle duration in seconds after applying cycle_time_reduce affix.

    Floored to an integer; never below 60 seconds. Shared by manual-action settlement
    and auto-tool settlement so both advance on the same timing formula.
    """
    base_secs = get_env_int("ACTION_CYCLE_MINUTES") * 60
    reduced = math.floor(base_secs * (1 - cycle_time_reduce_pct / 100.0))
    return max(60, reduced)


def action_costs(action: str) -> dict[str, int]:
    """Return {resource_type: amount} consumed per complete cycle for this action."""
    costs: dict[str, int] = {"food": get_env_int("FOOD_COST")}
    if action in ("building", "combat"):
        costs["wood"] = get_env_int("WOOD_COST")
    elif action == "research":
        costs["knowledge"] = get_env_int("KNOWLEDGE_COST")
    return costs


async def compute_output(db, user_id: str, action: str, affix_efficiency_pct: int = 0) -> int:
    """
    Return floor(BASE_OUTPUT × (1 + stage_bonus + gear_bonus + facility_bonus + affix_efficiency)).
    affix_efficiency_pct is the summed efficiency affix value for the current action's tool.
    """
    base = get_env_int("BASE_OUTPUT")
    stage_bonus_per = get_env_float("STAGE_BONUS_PER_CLEAR")
    gear_bonus_per = get_env_float("GEAR_BONUS_PER_LEVEL")
    facility_bonus_per = get_env_float("FACILITY_BONUS_PER_LEVEL")

    async with db.execute("SELECT stages_cleared FROM stage_state WHERE id=1") as cur:
        row = await cur.fetchone()
    stages_cleared = row[0] if row else 0

    gear_col = ACTION_GEAR_COL[action]
    async with db.execute(
        f"SELECT {gear_col} FROM players WHERE user_id=?", (user_id,)
    ) as cur:
        row = await cur.fetchone()
    gear_level = row[0] if row else 0

    facility = ACTION_FACILITY_BUILDING[action]
    async with db.execute(
        "SELECT level FROM buildings WHERE building_type=?", (facility,)
    ) as cur:
        row = await cur.fetchone()
    facility_level = row[0] if row else 0

    upgrade_clears = stages_cleared // 5
    bonus = (
        upgrade_clears * stage_bonus_per
        + gear_level * gear_bonus_per
        + facility_level * facility_bonus_per
        + affix_efficiency_pct / 100.0
    )
    return math.floor(base * (1 + bonus))

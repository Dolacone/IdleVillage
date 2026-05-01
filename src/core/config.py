import os

REQUIRED_KEYS = [
    "DISCORD_TOKEN",
    "DISCORD_GUILD_ID",
    "DATABASE_PATH",
    "ANNOUNCEMENT_CHANNEL_ID",
    "ADMIN_IDS",
    "ACTION_CYCLE_MINUTES",
    "WATCHER_HEARTBEAT_SECONDS",
    "MAX_CYCLES_PER_SETTLEMENT",
    "REFRESH_COOLDOWN_SECONDS",
    "BASE_OUTPUT",
    "FOOD_COST",
    "WOOD_COST",
    "KNOWLEDGE_COST",
    "MATERIAL_DROP_RATE",
    "ADMIN_RESOURCE_DELTA_SMALL",
    "ADMIN_RESOURCE_DELTA_LARGE",
    "STAGE_BONUS_PER_CLEAR",
    "GEAR_BONUS_PER_LEVEL",
    "FACILITY_BONUS_PER_LEVEL",
    "AP_CAP",
    "AP_RECOVERY_MINUTES",
    "STAGE_BASE_TARGET",
    "STAGE_TARGET_GROWTH_PER_ROUND",
    "UPGRADE_STAGE_TARGET_MULTIPLIER",
    "STAGE_OVERTIME_SECONDS",
    "STAGE_OVERTIME_PROGRESS_MULTIPLIER",
    "BUILDING_XP_PER_LEVEL",
    "GEAR_PITY_BONUS",
    "GEAR_MIN_SUCCESS_RATE",
    "GEAR_RATE_LOSS_PER_LEVEL",
]


def validate_env() -> bool:
    missing = [key for key in REQUIRED_KEYS if not os.getenv(key, "").strip()]
    if missing:
        for key in missing:
            print(f"Missing required environment variable: {key}")
        return False
    return True


def get_env_str(key: str) -> str:
    return os.getenv(key, "")


def get_env_int(key: str) -> int:
    try:
        return int(os.getenv(key, "0").strip())
    except ValueError:
        return 0


def get_env_float(key: str) -> float:
    try:
        return float(os.getenv(key, "0").strip())
    except ValueError:
        return 0.0


def get_database_path() -> str:
    return get_env_str("DATABASE_PATH") or "data/village.db"


def get_discord_guild_id() -> str:
    return get_env_str("DISCORD_GUILD_ID")


def get_announcement_channel_id() -> str:
    return get_env_str("ANNOUNCEMENT_CHANNEL_ID")


def get_action_cycle_minutes() -> int:
    return max(1, get_env_int("ACTION_CYCLE_MINUTES"))


def get_stage_base_target() -> int:
    return get_env_int("STAGE_BASE_TARGET")


def get_admin_ids():
    raw_value = get_env_str("ADMIN_IDS")
    admin_ids = set()
    for part in raw_value.split(","):
        candidate = part.strip()
        if not candidate:
            continue
        try:
            admin_ids.add(int(candidate))
        except ValueError:
            continue
    return admin_ids


def is_admin(user_id: int) -> bool:
    return int(user_id) in get_admin_ids()


def get_primary_admin_id() -> int:
    return min(get_admin_ids())

import os


def _find_env_example_path() -> str | None:
    """
    Locate .env.example by walking up from this file's directory.

    Depth differs by context: in the repo it's two levels above src/core/config.py
    (repo root); in the Docker image (WORKDIR /app, src/ contents copied flat into
    /app) it's one level above /app/core/config.py. Searching handles both without
    hardcoding either layout.
    """
    directory = os.path.dirname(os.path.abspath(__file__))
    for _ in range(6):
        candidate = os.path.join(directory, ".env.example")
        if os.path.isfile(candidate):
            return candidate
        parent = os.path.dirname(directory)
        if parent == directory:
            break
        directory = parent
    return None


def _load_env_example_defaults() -> dict:
    """Parse .env.example as fallback defaults for keys left blank in the real environment."""
    defaults = {}
    path = _find_env_example_path()
    if not path:
        return defaults
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                defaults[key.strip()] = value.strip()
    except OSError:
        pass
    return defaults


_ENV_EXAMPLE_DEFAULTS = _load_env_example_defaults()

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
    "AFFIX_SLOT_INTERVAL",
    "AFFIX_EXTRACT_COST",
    "AFFIX_CLEAR_COST",
    "TRIAL_DURATION_SECONDS",
    "TRIAL_COOLDOWN_SECONDS",
    "TRIAL_TARGET_AMOUNT",
    "TRIAL_REWARD_DIVISOR",
    "AUTO_TOOL_SECONDS_PER_MATERIAL",
    "AUTO_TOOL_MAX_HOURS",
]


def _resolve_raw(key: str) -> str:
    """Return the env var value, falling back to .env.example's default when blank/missing."""
    value = os.getenv(key, "").strip()
    if value:
        return value
    return _ENV_EXAMPLE_DEFAULTS.get(key, "")


def validate_env() -> bool:
    missing = [key for key in REQUIRED_KEYS if not _resolve_raw(key)]
    if missing:
        for key in missing:
            print(f"Missing required environment variable: {key}")
        return False
    return True


def get_env_str(key: str) -> str:
    return _resolve_raw(key)


def get_env_int(key: str) -> int:
    try:
        return int(_resolve_raw(key) or "0")
    except ValueError:
        return 0


def get_env_float(key: str) -> float:
    try:
        return float(_resolve_raw(key) or "0")
    except ValueError:
        return 0.0


def get_discord_token() -> str:
    return get_env_str("DISCORD_TOKEN")


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

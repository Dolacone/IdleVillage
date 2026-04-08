import os


DEFAULT_ALLOWED_OWNER_ID = 151517260622594048
DEFAULT_ACTION_CYCLE_MINUTES = 60


def get_admin_ids():
    raw_value = os.getenv("ADMIN_IDS", "").strip()
    if not raw_value:
        return {DEFAULT_ALLOWED_OWNER_ID}

    admin_ids = set()
    for part in raw_value.split(","):
        candidate = part.strip()
        if not candidate:
            continue
        try:
            admin_ids.add(int(candidate))
        except ValueError:
            continue

    return admin_ids or {DEFAULT_ALLOWED_OWNER_ID}


def is_admin(user_id: int) -> bool:
    return int(user_id) in get_admin_ids()


def get_primary_admin_id() -> int:
    return min(get_admin_ids())


def get_action_cycle_minutes() -> int:
    raw_value = os.getenv("ACTION_CYCLE_MINUTES", str(DEFAULT_ACTION_CYCLE_MINUTES)).strip()
    try:
        minutes = int(raw_value)
    except ValueError:
        minutes = DEFAULT_ACTION_CYCLE_MINUTES
    return max(1, minutes)

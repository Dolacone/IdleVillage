"""Shared datetime helpers for v2 modules."""

from datetime import datetime, timezone


def parse_dt(s: str) -> datetime:
    """Parse UTC ISO-8601 text. Always returns an aware datetime."""
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def dt_str(dt: datetime) -> str:
    """Serialise datetime to UTC ISO-8601 text."""
    return dt.astimezone(timezone.utc).isoformat()

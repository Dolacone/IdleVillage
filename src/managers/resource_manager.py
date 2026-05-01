"""
resource_manager — village shared resource pool (food, wood, knowledge).

All functions accept an open aiosqlite connection.
The caller is responsible for committing the transaction.
"""

from datetime import datetime

from core.utils import dt_str

RESOURCE_TYPES = ("food", "wood", "knowledge")


async def balance(db, resource_type: str) -> int:
    """Return current amount of the given resource."""
    async with db.execute(
        "SELECT amount FROM village_resources WHERE resource_type=?", (resource_type,)
    ) as cur:
        row = await cur.fetchone()
    return row[0] if row else 0


async def can_afford(db, resource_type: str, amount: int) -> bool:
    """Return True if the village has at least amount of the resource."""
    return await balance(db, resource_type) >= amount


async def deposit(db, resource_type: str, amount: int, ts: datetime) -> None:
    """Add amount to the resource pool."""
    current = await balance(db, resource_type)
    await db.execute(
        "UPDATE village_resources SET amount=?, updated_at=? WHERE resource_type=?",
        (current + amount, dt_str(ts), resource_type),
    )


async def withdraw(db, resource_type: str, amount: int, ts: datetime) -> None:
    """Deduct amount from the resource pool (floored at 0)."""
    current = await balance(db, resource_type)
    await db.execute(
        "UPDATE village_resources SET amount=?, updated_at=? WHERE resource_type=?",
        (max(0, current - amount), dt_str(ts), resource_type),
    )

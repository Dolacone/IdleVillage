import asyncio
import math
import os
import shutil
from datetime import datetime

import aiosqlite

DB_PATH = os.getenv("DATABASE_PATH", "data/village.db")

RESOURCE_TYPES = ("food", "wood", "stone")
BUFF_FOOD_EFFICIENCY = 1
BUFF_STORAGE_CAPACITY = 2
BUFF_RESOURCE_YIELD = 3
BUFF_IDS = (BUFF_FOOD_EFFICIENCY, BUFF_STORAGE_CAPACITY, BUFF_RESOURCE_YIELD)
STATS_BASE_VALUE = 50
LEGACY_VILLAGE_COLUMNS = (
    "food",
    "wood",
    "stone",
    "food_efficiency_xp",
    "storage_capacity_xp",
    "resource_yield_xp",
)


async def _table_columns(db, table_name: str):
    async with db.execute(f"PRAGMA table_info({table_name})") as cursor:
        return await cursor.fetchall()


async def _table_exists(db, table_name: str):
    async with db.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table' AND name = ?
        """,
        (table_name,),
    ) as cursor:
        return await cursor.fetchone() is not None


async def _create_current_tables(db):
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS villages (
            id INTEGER PRIMARY KEY,
            last_tick_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            announcement_channel_id TEXT,
            announcement_message_id TEXT,
            last_announcement_updated TIMESTAMP
        )
        """
    )

    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS village_resources (
            village_id INTEGER NOT NULL,
            resource_type TEXT NOT NULL,
            amount INTEGER DEFAULT 0,
            PRIMARY KEY (village_id, resource_type),
            FOREIGN KEY (village_id) REFERENCES villages(id)
        )
        """
    )

    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS buffs (
            village_id INTEGER NOT NULL,
            buff_id INTEGER NOT NULL,
            xp INTEGER DEFAULT 0,
            PRIMARY KEY (village_id, buff_id),
            FOREIGN KEY (village_id) REFERENCES villages(id)
        )
        """
    )

    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS players (
            discord_id INTEGER NOT NULL,
            village_id INTEGER NOT NULL,
            last_message_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_command_time TIMESTAMP DEFAULT '',
            status TEXT DEFAULT 'idle',
            target_id INTEGER,
            last_update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completion_time TIMESTAMP,
            PRIMARY KEY (discord_id, village_id),
            FOREIGN KEY (village_id) REFERENCES villages(id)
        )
        """
    )

    await db.execute(
        f"""
        CREATE TABLE IF NOT EXISTS player_stats (
            player_discord_id INTEGER NOT NULL,
            village_id INTEGER NOT NULL,
            strength INTEGER DEFAULT {STATS_BASE_VALUE},
            agility INTEGER DEFAULT {STATS_BASE_VALUE},
            perception INTEGER DEFAULT {STATS_BASE_VALUE},
            knowledge INTEGER DEFAULT {STATS_BASE_VALUE},
            endurance INTEGER DEFAULT {STATS_BASE_VALUE},
            last_calc_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (player_discord_id, village_id),
            FOREIGN KEY (player_discord_id, village_id) REFERENCES players(discord_id, village_id)
        )
        """
    )

    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS player_actions_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_discord_id INTEGER NOT NULL,
            village_id INTEGER NOT NULL,
            action_type TEXT,
            start_time TIMESTAMP,
            end_time TIMESTAMP,
            FOREIGN KEY (player_discord_id, village_id) REFERENCES players(discord_id, village_id)
        )
        """
    )

    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS resource_nodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            village_id INTEGER,
            type TEXT,
            quality INTEGER,
            remaining_amount INTEGER,
            expiry_time TIMESTAMP,
            FOREIGN KEY (village_id) REFERENCES villages(id)
        )
        """
    )

    await db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_actions_log_player
        ON player_actions_log (player_discord_id, village_id, end_time DESC, id DESC)
        """
    )


async def _seed_village_defaults(
    db,
    village_id: int,
    *,
    food: int = 1000,
    wood: int = 1000,
    stone: int = 1000,
    food_efficiency_xp: int = 0,
    storage_capacity_xp: int = 0,
    resource_yield_xp: int = 0,
):
    await db.executemany(
        """
        INSERT INTO village_resources (village_id, resource_type, amount)
        VALUES (?, ?, ?)
        ON CONFLICT(village_id, resource_type) DO NOTHING
        """,
        (
            (village_id, "food", int(food)),
            (village_id, "wood", int(wood)),
            (village_id, "stone", int(stone)),
        ),
    )
    await db.executemany(
        """
        INSERT INTO buffs (village_id, buff_id, xp)
        VALUES (?, ?, ?)
        ON CONFLICT(village_id, buff_id) DO NOTHING
        """,
        (
            (village_id, 1, int(food_efficiency_xp)),
            (village_id, 2, int(storage_capacity_xp)),
            (village_id, 3, int(resource_yield_xp)),
        ),
    )


async def _normalize_existing_villages(db):
    async with db.execute("SELECT id FROM villages") as cursor:
        village_rows = await cursor.fetchall()

    for (village_id,) in village_rows:
        await _seed_village_defaults(db, int(village_id))


async def _needs_destructive_migration(db):
    if not await _table_exists(db, "villages"):
        return False

    village_columns = await _table_columns(db, "villages")
    village_names = {column[1] for column in village_columns}

    return any(column_name in village_names for column_name in LEGACY_VILLAGE_COLUMNS)


def _backup_database_file():
    if not os.path.exists(DB_PATH):
        return None

    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    backup_path = f"{DB_PATH}.{timestamp}.2026.04.09.01.bak"
    shutil.copy2(DB_PATH, backup_path)
    return backup_path


async def _migrate_resource_nodes_to_singletons(db):
    async with db.execute(
        """
        SELECT id, remaining_amount
        FROM resource_nodes
        """
    ) as cursor:
        all_nodes = await cursor.fetchall()

    for node_id, remaining_amount in all_nodes:
        normalized_amount = max(0, min(8000, int(remaining_amount or 0)))
        await db.execute(
            """
            UPDATE resource_nodes
            SET remaining_amount = ?, expiry_time = NULL
            WHERE id = ?
            """,
            (normalized_amount, node_id),
        )

    async with db.execute(
        """
        SELECT village_id, type
        FROM resource_nodes
        GROUP BY village_id, type
        HAVING COUNT(*) > 1
        """
    ) as cursor:
        duplicate_groups = await cursor.fetchall()

    for village_id, node_type in duplicate_groups:
        async with db.execute(
            """
            SELECT id, quality, remaining_amount
            FROM resource_nodes
            WHERE village_id = ?
              AND type = ?
            ORDER BY id ASC
            """,
            (village_id, node_type),
        ) as cursor:
            nodes = await cursor.fetchall()

        if len(nodes) <= 1:
            continue

        node_ids = [node_id for node_id, _quality, _remaining_amount in nodes]
        placeholders = ", ".join("?" for _ in node_ids)
        async with db.execute(
            f"""
            SELECT target_id, COUNT(*)
            FROM players
            WHERE village_id = ?
              AND status = 'gathering'
              AND target_id IN ({placeholders})
            GROUP BY target_id
            ORDER BY COUNT(*) DESC, target_id ASC
            LIMIT 1
            """,
            (village_id, *node_ids),
        ) as cursor:
            targeted_node = await cursor.fetchone()

        keeper_id = targeted_node[0] if targeted_node else node_ids[0]
        keeper_quality = next(
            int(quality or 0)
            for node_id, quality, _remaining_amount in nodes
            if node_id == keeper_id
        )

        total_stock = sum(max(0, int(remaining_amount or 0)) for _node_id, _quality, remaining_amount in nodes)
        if total_stock > 0:
            weighted_quality = math.floor(
                sum(
                    int(quality or 0) * max(0, int(remaining_amount or 0))
                    for _node_id, quality, remaining_amount in nodes
                ) / total_stock
            )
        else:
            weighted_quality = keeper_quality

        merged_stock = min(8000, total_stock)
        await db.execute(
            """
            UPDATE resource_nodes
            SET quality = ?, remaining_amount = ?, expiry_time = NULL
            WHERE id = ?
            """,
            (weighted_quality, merged_stock, keeper_id),
        )

        duplicate_ids = [node_id for node_id in node_ids if node_id != keeper_id]
        if duplicate_ids:
            duplicate_placeholders = ", ".join("?" for _ in duplicate_ids)
            await db.execute(
                f"""
                UPDATE players
                SET target_id = ?
                WHERE village_id = ?
                  AND status = 'gathering'
                  AND target_id IN ({duplicate_placeholders})
                """,
                (keeper_id, village_id, *duplicate_ids),
            )
            await db.execute(
                f"""
                DELETE FROM resource_nodes
                WHERE id IN ({duplicate_placeholders})
                """,
                tuple(duplicate_ids),
            )


async def _migrate_village_storage_schema(db):
    if not await _table_exists(db, "villages"):
        return

    await _create_current_tables(db)
    village_columns = await _table_columns(db, "villages")
    existing_names = {column[1] for column in village_columns}
    has_legacy_columns = any(column_name in existing_names for column_name in LEGACY_VILLAGE_COLUMNS)

    if not has_legacy_columns:
        await _normalize_existing_villages(db)
        return

    async with db.execute(
        """
        SELECT
            id,
            COALESCE(food, 1000),
            COALESCE(wood, 1000),
            COALESCE(stone, 1000),
            COALESCE(food_efficiency_xp, 0),
            COALESCE(storage_capacity_xp, 0),
            COALESCE(resource_yield_xp, 0)
        FROM villages
        """
    ) as cursor:
        villages = await cursor.fetchall()

    for village in villages:
        await _seed_village_defaults(
            db,
            village[0],
            food=village[1],
            wood=village[2],
            stone=village[3],
            food_efficiency_xp=village[4],
            storage_capacity_xp=village[5],
            resource_yield_xp=village[6],
        )

    await db.execute("PRAGMA foreign_keys = OFF")
    await db.execute("DROP TABLE IF EXISTS villages_new")
    await db.execute(
        """
        CREATE TABLE villages_new (
            id INTEGER PRIMARY KEY,
            last_tick_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            announcement_channel_id TEXT,
            announcement_message_id TEXT,
            last_announcement_updated TIMESTAMP
        )
        """
    )
    await db.execute(
        """
        INSERT INTO villages_new (
            id, last_tick_time, announcement_channel_id, announcement_message_id, last_announcement_updated
        )
        SELECT
            id,
            last_tick_time,
            announcement_channel_id,
            announcement_message_id,
            last_announcement_updated
        FROM villages
        """
    )
    await db.execute("DROP TABLE villages")
    await db.execute("ALTER TABLE villages_new RENAME TO villages")
    await db.execute("PRAGMA foreign_keys = ON")
    await _normalize_existing_villages(db)


async def init_db():
    """Initializes the SQLite database with the required schemas."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

    async with aiosqlite.connect(DB_PATH) as db:
        if await _needs_destructive_migration(db):
            _backup_database_file()

        await _create_current_tables(db)
        await _migrate_village_storage_schema(db)
        await _migrate_resource_nodes_to_singletons(db)

        await db.commit()


def get_connection():
    """Returns a new aiosqlite connection/context manager.
    Use either:
    async with get_connection() as db:
    or:
    db = await get_connection()
    """
    return aiosqlite.connect(DB_PATH)


if __name__ == "__main__":
    asyncio.run(init_db())
    print("Database schema initialized successfully.")

import os
from datetime import datetime, timedelta

import aiosqlite

from core.config import get_action_cycle_minutes

DB_PATH = os.getenv("DATABASE_PATH", "data/village.db")

RESOURCE_TYPES = ("food", "wood", "stone", "gold")
BUFF_FOOD_EFFICIENCY = 1
BUFF_STORAGE_CAPACITY = 2
BUFF_RESOURCE_YIELD = 3
BUFF_HUNTING = 4
BUFF_IDS = (BUFF_FOOD_EFFICIENCY, BUFF_STORAGE_CAPACITY, BUFF_RESOURCE_YIELD, BUFF_HUNTING)
STATS_BASE_VALUE = 50
TOKEN_TYPES = ("gathering", "exploring", "building", "attacking")
PLAYER_BUFF_TYPES = TOKEN_TYPES


async def _ensure_column(db, table_name: str, column_name: str, definition: str):
    async with db.execute(f"PRAGMA table_info({table_name})") as cursor:
        columns = await cursor.fetchall()
    existing_names = {column[1] for column in columns}
    if column_name not in existing_names:
        await db.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")


async def _table_columns(db, table_name: str):
    async with db.execute(f"PRAGMA table_info({table_name})") as cursor:
        columns = await cursor.fetchall()
    return [column[1] for column in columns]


async def _table_exists(db, table_name: str):
    async with db.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table'
          AND name = ?
        """,
        (table_name,),
    ) as cursor:
        return await cursor.fetchone() is not None


async def _migrate_monsters_table_if_needed(db):
    if not await _table_exists(db, "monsters"):
        return

    columns = await _table_columns(db, "monsters")
    if "expires_at" not in columns:
        return

    await db.execute("ALTER TABLE monsters RENAME TO monsters_legacy_2026_04_13")
    await db.execute(
        """
        CREATE TABLE monsters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            village_id INTEGER NOT NULL UNIQUE,
            name TEXT NOT NULL,
            reward_resource_type TEXT NOT NULL DEFAULT 'food',
            quality INTEGER NOT NULL,
            hp INTEGER NOT NULL,
            max_hp INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (village_id) REFERENCES villages(id)
        )
        """
    )
    await db.execute(
        """
        INSERT INTO monsters (id, village_id, name, reward_resource_type, quality, hp, max_hp, created_at)
        SELECT
            id,
            village_id,
            COALESCE(name, 'Monsters'),
            COALESCE(reward_resource_type, 'food'),
            quality,
            hp,
            max_hp,
            COALESCE(created_at, CURRENT_TIMESTAMP)
        FROM monsters_legacy_2026_04_13
        """
    )
    await db.execute("DROP TABLE monsters_legacy_2026_04_13")


def _parse_timestamp(value):
    if not value:
        return None
    return datetime.fromisoformat(value)


def _action_cycle_seconds():
    return get_action_cycle_minutes() * 60


def _action_deltas(action_type: str):
    mapping = {
        "idle": (0, 0, 1, 1, 0),
        "gathering_food": (0, 0, 1, 1, 0),
        "gathering_wood": (1, 0, 0, 0, 1),
        "gathering_stone": (1, 0, 0, 0, 1),
        "exploring": (0, 1, 1, 0, 0),
        "building": (0, 0, 0, 1, 1),
        "attack": (1, 1, 0, 0, 0),
    }
    return mapping.get(action_type)


async def _create_player_actions_log_table(db):
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS player_actions_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_discord_id INTEGER NOT NULL,
            village_id INTEGER NOT NULL,
            strength_delta INTEGER NOT NULL DEFAULT 0,
            agility_delta INTEGER NOT NULL DEFAULT 0,
            perception_delta INTEGER NOT NULL DEFAULT 0,
            knowledge_delta INTEGER NOT NULL DEFAULT 0,
            endurance_delta INTEGER NOT NULL DEFAULT 0,
            cycle_end_time TIMESTAMP NOT NULL,
            FOREIGN KEY (player_discord_id, village_id) REFERENCES players(discord_id, village_id)
        )
        """
    )
    columns = await _table_columns(db, "player_actions_log")
    if "cycle_end_time" in columns:
        await db.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_actions_log_player
            ON player_actions_log (player_discord_id, village_id, cycle_end_time DESC, id DESC)
            """
        )


async def _migrate_player_actions_log_if_needed(db):
    if not await _table_exists(db, "player_actions_log"):
        await _create_player_actions_log_table(db)
        return

    columns = await _table_columns(db, "player_actions_log")
    if "action_type" not in columns:
        await _create_player_actions_log_table(db)
        return

    await db.execute("ALTER TABLE player_actions_log RENAME TO player_actions_log_legacy_2026_04_14")
    await _create_player_actions_log_table(db)

    async with db.execute(
        """
        SELECT player_discord_id, village_id, action_type, start_time, end_time
        FROM player_actions_log_legacy_2026_04_14
        ORDER BY player_discord_id, village_id, end_time, id
        """
    ) as cursor:
        legacy_rows = await cursor.fetchall()

    converted_rows = []
    cycle_seconds = _action_cycle_seconds()
    for player_discord_id, village_id, action_type, start_time, end_time in legacy_rows:
        deltas = _action_deltas(action_type)
        if deltas is None:
            continue

        start_dt = _parse_timestamp(start_time)
        end_dt = _parse_timestamp(end_time)
        if start_dt is None or end_dt is None or end_dt <= start_dt:
            continue

        full_cycles = int((end_dt - start_dt).total_seconds() // cycle_seconds)
        for cycle_index in range(full_cycles):
            cycle_end_time = start_dt + timedelta(seconds=cycle_seconds * (cycle_index + 1))
            converted_rows.append(
                (
                    player_discord_id,
                    village_id,
                    deltas[0],
                    deltas[1],
                    deltas[2],
                    deltas[3],
                    deltas[4],
                    cycle_end_time.isoformat(),
                )
            )

    if converted_rows:
        await db.executemany(
            """
            INSERT INTO player_actions_log (
                player_discord_id,
                village_id,
                strength_delta,
                agility_delta,
                perception_delta,
                knowledge_delta,
                endurance_delta,
                cycle_end_time
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            converted_rows,
        )

        await db.execute(
            """
            DELETE FROM player_actions_log
            WHERE id IN (
                SELECT id
                FROM (
                    SELECT
                        id,
                        ROW_NUMBER() OVER (
                            PARTITION BY player_discord_id, village_id
                            ORDER BY cycle_end_time DESC, id DESC
                        ) AS row_num
                    FROM player_actions_log
                )
                WHERE row_num > 150
            )
            """
        )

    await db.execute("DROP TABLE player_actions_log_legacy_2026_04_14")


async def _create_current_tables(db):
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS villages (
            id INTEGER PRIMARY KEY,
            last_tick_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            announcement_channel_id TEXT,
            announcement_message_id TEXT,
            last_announcement_updated TIMESTAMP,
            active_command TEXT,
            protection_expires_at TIMESTAMP
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

    await _create_player_actions_log_table(db)

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
        CREATE TABLE IF NOT EXISTS monsters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            village_id INTEGER NOT NULL UNIQUE,
            name TEXT NOT NULL,
            reward_resource_type TEXT NOT NULL DEFAULT 'food',
            quality INTEGER NOT NULL,
            hp INTEGER NOT NULL,
            max_hp INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (village_id) REFERENCES villages(id)
        )
        """
    )

    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS tokens (
            player_discord_id INTEGER NOT NULL,
            village_id INTEGER NOT NULL,
            token_type TEXT NOT NULL,
            amount INTEGER DEFAULT 0,
            PRIMARY KEY (player_discord_id, village_id, token_type),
            FOREIGN KEY (player_discord_id, village_id) REFERENCES players(discord_id, village_id)
        )
        """
    )

    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS player_buffs (
            player_discord_id INTEGER NOT NULL,
            village_id INTEGER NOT NULL,
            buff_type TEXT,
            expires_at TIMESTAMP,
            PRIMARY KEY (player_discord_id, village_id),
            FOREIGN KEY (player_discord_id, village_id) REFERENCES players(discord_id, village_id)
        )
        """
    )

    await _ensure_column(db, "villages", "active_command", "TEXT")
    await _ensure_column(db, "villages", "protection_expires_at", "TIMESTAMP")
    await _migrate_monsters_table_if_needed(db)
    await _ensure_column(db, "monsters", "reward_resource_type", "TEXT NOT NULL DEFAULT 'food'")
    await _ensure_column(db, "monsters", "created_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP")

    await _migrate_player_actions_log_if_needed(db)

async def init_db():
    """Initializes the SQLite database with the required schemas."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

    async with aiosqlite.connect(DB_PATH) as db:
        await _create_current_tables(db)
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

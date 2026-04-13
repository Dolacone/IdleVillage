import asyncio
import os

import aiosqlite

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
    await _ensure_column(db, "monsters", "reward_resource_type", "TEXT NOT NULL DEFAULT 'food'")
    await _ensure_column(db, "monsters", "created_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP")

    await db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_actions_log_player
        ON player_actions_log (player_discord_id, village_id, end_time DESC, id DESC)
        """
    )

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

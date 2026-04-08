import os
import aiosqlite
import asyncio

DB_PATH = os.getenv("DATABASE_PATH", "data/village.db")


async def _ensure_column(db, table_name: str, column_name: str, definition: str):
    async with db.execute(f"PRAGMA table_info({table_name})") as cursor:
        columns = await cursor.fetchall()

    existing_names = {column[1] for column in columns}
    if column_name not in existing_names:
        await db.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")


async def _migrate_resource_nodes_drop_level(db):
    async with db.execute("PRAGMA table_info(resource_nodes)") as cursor:
        columns = await cursor.fetchall()

    existing_names = {column[1] for column in columns}
    if "level" not in existing_names:
        return

    await db.execute(
        """
        CREATE TABLE resource_nodes_new (
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
        INSERT INTO resource_nodes_new (id, village_id, type, quality, remaining_amount, expiry_time)
        SELECT id, village_id, type, quality, remaining_amount, expiry_time
        FROM resource_nodes
        """
    )
    await db.execute("DROP TABLE resource_nodes")
    await db.execute("ALTER TABLE resource_nodes_new RENAME TO resource_nodes")

async def init_db():
    """Initializes the SQLite database with the required schemas."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS villages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id TEXT UNIQUE NOT NULL,
                food INTEGER DEFAULT 100,
                wood INTEGER DEFAULT 0,
                stone INTEGER DEFAULT 0,
                food_efficiency_xp INTEGER DEFAULT 0,
                storage_capacity_xp INTEGER DEFAULT 0,
                resource_yield_xp INTEGER DEFAULT 0,
                last_tick_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                announcement_channel_id TEXT,
                announcement_message_id TEXT,
                last_announcement_updated TIMESTAMP
            )
        ''')

        await db.execute('''
            CREATE TABLE IF NOT EXISTS players (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                discord_id TEXT NOT NULL,
                village_id INTEGER,
                last_message_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'idle',
                target_id INTEGER,
                last_update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completion_time TIMESTAMP,
                FOREIGN KEY (village_id) REFERENCES villages(id),
                UNIQUE(discord_id, village_id)
            )
        ''')

        await db.execute('''
            CREATE TABLE IF NOT EXISTS player_stats (
                player_id INTEGER PRIMARY KEY,
                strength INTEGER DEFAULT 50,
                agility INTEGER DEFAULT 50,
                perception INTEGER DEFAULT 50,
                knowledge INTEGER DEFAULT 50,
                endurance INTEGER DEFAULT 50,
                last_calc_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (player_id) REFERENCES players(id)
            )
        ''')

        await db.execute('''
            CREATE TABLE IF NOT EXISTS player_actions_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                player_id INTEGER,
                action_type TEXT,
                start_time TIMESTAMP,
                end_time TIMESTAMP,
                FOREIGN KEY (player_id) REFERENCES players(id)
            )
        ''')

        await db.execute('''
            CREATE TABLE IF NOT EXISTS resource_nodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                village_id INTEGER,
                type TEXT,
                quality INTEGER,
                remaining_amount INTEGER,
                expiry_time TIMESTAMP,
                FOREIGN KEY (village_id) REFERENCES villages(id)
            )
        ''')

        await _ensure_column(db, "villages", "announcement_channel_id", "TEXT")
        await _ensure_column(db, "villages", "announcement_message_id", "TEXT")
        await _ensure_column(db, "villages", "last_announcement_updated", "TIMESTAMP")
        await _migrate_resource_nodes_drop_level(db)

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

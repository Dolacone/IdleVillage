import os
import aiosqlite
import asyncio

DB_PATH = os.getenv("DATABASE_PATH", "data/village.db")

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
                last_tick_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        await db.execute('''
            CREATE TABLE IF NOT EXISTS players (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                discord_id TEXT UNIQUE NOT NULL,
                village_id INTEGER,
                satiety_deadline TIMESTAMP,
                last_message_time TIMESTAMP,
                current_weight INTEGER DEFAULT 0,
                status TEXT DEFAULT 'idle',
                location_status TEXT DEFAULT 'at_village',
                current_action_type TEXT,
                target_node_id INTEGER,
                auto_restart INTEGER DEFAULT 0,
                last_update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completion_time TIMESTAMP,
                FOREIGN KEY (village_id) REFERENCES villages(id)
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
                stat_category TEXT,
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
                level INTEGER,
                quality INTEGER,
                distance INTEGER,
                remaining_amount INTEGER,
                max_capacity INTEGER,
                expiry_time TIMESTAMP,
                FOREIGN KEY (village_id) REFERENCES villages(id)
            )
        ''')

        await db.commit()


async def get_connection():
    """Returns a new active aiosqlite connection.
    Must be used with an async context manager:
    async with await get_connection() as db:
    """
    return await aiosqlite.connect(DB_PATH)

if __name__ == "__main__":
    asyncio.run(init_db())
    print("Database schema initialized successfully.")

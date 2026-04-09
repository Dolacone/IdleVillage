import os
import aiosqlite
import asyncio
import math

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
        """
        CREATE TABLE IF NOT EXISTS player_stats (
            player_discord_id INTEGER NOT NULL,
            village_id INTEGER NOT NULL,
            strength INTEGER DEFAULT 50,
            agility INTEGER DEFAULT 50,
            perception INTEGER DEFAULT 50,
            knowledge INTEGER DEFAULT 50,
            endurance INTEGER DEFAULT 50,
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


async def _migrate_identity_schema(db):
    village_columns = await _table_columns(db, "villages")
    player_columns = await _table_columns(db, "players")

    has_legacy_villages = any(column[1] == "guild_id" for column in village_columns)
    has_legacy_players = any(column[1] == "id" for column in player_columns)

    if not has_legacy_villages and not has_legacy_players:
        return

    await db.execute("PRAGMA foreign_keys = OFF")

    table_names = (
        "villages",
        "players",
        "player_stats",
        "player_actions_log",
        "resource_nodes",
    )
    for table_name in table_names:
        if await _table_exists(db, table_name):
            await db.execute(f"ALTER TABLE {table_name} RENAME TO {table_name}_legacy")

    await _create_current_tables(db)

    if await _table_exists(db, "villages_legacy"):
        await db.execute(
            """
            INSERT INTO villages (
                id, food, wood, stone,
                food_efficiency_xp, storage_capacity_xp, resource_yield_xp,
                last_tick_time, announcement_channel_id, announcement_message_id, last_announcement_updated
            )
            SELECT
                CAST(guild_id AS INTEGER),
                food,
                wood,
                stone,
                food_efficiency_xp,
                storage_capacity_xp,
                resource_yield_xp,
                last_tick_time,
                announcement_channel_id,
                announcement_message_id,
                last_announcement_updated
            FROM villages_legacy
            """
        )

    if await _table_exists(db, "players_legacy") and await _table_exists(db, "villages_legacy"):
        await db.execute(
            """
            INSERT INTO players (
                discord_id, village_id, last_message_time, last_command_time,
                status, target_id, last_update_time, completion_time
            )
            SELECT
                CAST(p.discord_id AS INTEGER),
                CAST(v.guild_id AS INTEGER),
                p.last_message_time,
                p.last_message_time,
                p.status,
                p.target_id,
                p.last_update_time,
                p.completion_time
            FROM players_legacy p
            JOIN villages_legacy v ON v.id = p.village_id
            """
        )

    if (
        await _table_exists(db, "player_stats_legacy")
        and await _table_exists(db, "players_legacy")
        and await _table_exists(db, "villages_legacy")
    ):
        await db.execute(
            """
            INSERT INTO player_stats (
                player_discord_id, village_id,
                strength, agility, perception, knowledge, endurance, last_calc_time
            )
            SELECT
                CAST(p.discord_id AS INTEGER),
                CAST(v.guild_id AS INTEGER),
                ps.strength,
                ps.agility,
                ps.perception,
                ps.knowledge,
                ps.endurance,
                ps.last_calc_time
            FROM player_stats_legacy ps
            JOIN players_legacy p ON p.id = ps.player_id
            JOIN villages_legacy v ON v.id = p.village_id
            """
        )

    if (
        await _table_exists(db, "player_actions_log_legacy")
        and await _table_exists(db, "players_legacy")
        and await _table_exists(db, "villages_legacy")
    ):
        await db.execute(
            """
            INSERT INTO player_actions_log (
                id, player_discord_id, village_id, action_type, start_time, end_time
            )
            SELECT
                log.id,
                CAST(p.discord_id AS INTEGER),
                CAST(v.guild_id AS INTEGER),
                log.action_type,
                log.start_time,
                log.end_time
            FROM player_actions_log_legacy log
            JOIN players_legacy p ON p.id = log.player_id
            JOIN villages_legacy v ON v.id = p.village_id
            """
        )

    if await _table_exists(db, "resource_nodes_legacy") and await _table_exists(db, "villages_legacy"):
        await db.execute(
            """
            INSERT INTO resource_nodes (
                id, village_id, type, quality, remaining_amount, expiry_time
            )
            SELECT
                rn.id,
                CAST(v.guild_id AS INTEGER),
                rn.type,
                rn.quality,
                rn.remaining_amount,
                rn.expiry_time
            FROM resource_nodes_legacy rn
            JOIN villages_legacy v ON v.id = rn.village_id
            """
        )

    for table_name in table_names:
        legacy_name = f"{table_name}_legacy"
        if await _table_exists(db, legacy_name):
            await db.execute(f"DROP TABLE {legacy_name}")

    await db.execute("PRAGMA foreign_keys = ON")

async def init_db():
    """Initializes the SQLite database with the required schemas."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

    async with aiosqlite.connect(DB_PATH) as db:
        await _create_current_tables(db)
        await _migrate_identity_schema(db)
        await _ensure_column(db, "players", "last_command_time", "TIMESTAMP DEFAULT ''")
        await db.execute("UPDATE players SET last_command_time = last_message_time WHERE last_command_time IS NULL")
        await _migrate_resource_nodes_drop_level(db)
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

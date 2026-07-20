import os
from datetime import datetime, timezone

import aiosqlite

from core.config import (
    get_announcement_channel_id,
    get_database_path,
    get_discord_guild_id,
    get_stage_base_target,
)

DB_PATH: str | None = None  # Override in tests; production resolves lazily via config.


def _resolve_db_path() -> str:
    return DB_PATH or get_database_path()


async def _create_v2_tables(db):
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS village_state (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            dashboard_channel_id TEXT,
            dashboard_message_id TEXT,
            announcement_channel_id TEXT
        )
        """
    )
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS stage_state (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            stages_cleared INTEGER NOT NULL DEFAULT 0,
            current_stage_index INTEGER NOT NULL DEFAULT 0,
            current_stage_type TEXT NOT NULL,
            current_stage_progress INTEGER NOT NULL DEFAULT 0,
            current_stage_target INTEGER NOT NULL,
            stage_started_at TEXT NOT NULL,
            overtime_notified INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL
        )
        """
    )
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS village_resources (
            resource_type TEXT PRIMARY KEY,
            amount INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL
        )
        """
    )
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS buildings (
            building_type TEXT PRIMARY KEY,
            level INTEGER NOT NULL DEFAULT 0,
            xp_progress INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL
        )
        """
    )
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS players (
            user_id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            action TEXT,
            action_target TEXT,
            completion_time TEXT,
            last_update_time TEXT,
            ap_full_time TEXT NOT NULL,
            materials_gathering INTEGER NOT NULL DEFAULT 0,
            materials_building INTEGER NOT NULL DEFAULT 0,
            materials_combat INTEGER NOT NULL DEFAULT 0,
            materials_research INTEGER NOT NULL DEFAULT 0,
            materials_universal INTEGER NOT NULL DEFAULT 0,
            gear_gathering INTEGER NOT NULL DEFAULT 0,
            gear_building INTEGER NOT NULL DEFAULT 0,
            gear_combat INTEGER NOT NULL DEFAULT 0,
            gear_research INTEGER NOT NULL DEFAULT 0,
            pity_gathering INTEGER NOT NULL DEFAULT 0,
            pity_building INTEGER NOT NULL DEFAULT 0,
            pity_combat INTEGER NOT NULL DEFAULT 0,
            pity_research INTEGER NOT NULL DEFAULT 0,
            risky_failed_levels INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS guild_installations (
            guild_id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1
        )
        """
    )
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS gear_affixes (
            user_id    TEXT NOT NULL,
            gear_type  TEXT NOT NULL,
            slot_index INTEGER NOT NULL,
            affix_type TEXT NOT NULL,
            value      INTEGER NOT NULL,
            PRIMARY KEY (user_id, gear_type, slot_index)
        )
        """
    )
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS trial_state (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            is_active INTEGER NOT NULL DEFAULT 0,
            resource_type TEXT,
            target INTEGER NOT NULL DEFAULT 0,
            progress INTEGER NOT NULL DEFAULT 0,
            started_at TEXT,
            ended_at TEXT,
            updated_at TEXT NOT NULL
        )
        """
    )
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS trial_contributions (
            user_id TEXT PRIMARY KEY,
            contribution INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL
        )
        """
    )
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS player_auto_tools (
            user_id TEXT NOT NULL,
            tool_type TEXT NOT NULL,
            action_target TEXT,
            completion_time TEXT NOT NULL,
            last_update_time TEXT,
            expires_at TEXT NOT NULL,
            started_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (user_id, tool_type)
        )
        """
    )
    await db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_auto_tools_completion
        ON player_auto_tools (completion_time)
        """
    )
    await db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_players_completion_time
        ON players (completion_time)
        """
    )
    await db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_players_action
        ON players (action)
        """
    )


async def _seed_initial_rows(db):
    now = datetime.now(timezone.utc).isoformat()

    await db.execute(
        """
        INSERT OR IGNORE INTO village_state (id, created_at, updated_at, announcement_channel_id)
        VALUES (1, ?, ?, ?)
        """,
        (now, now, get_announcement_channel_id()),
    )

    stage_target = get_stage_base_target()
    await db.execute(
        """
        INSERT OR IGNORE INTO stage_state (
            id, stages_cleared, current_stage_index, current_stage_type,
            current_stage_progress, current_stage_target,
            stage_started_at, overtime_notified, updated_at
        ) VALUES (1, 0, 0, 'gathering', 0, ?, ?, 0, ?)
        """,
        (stage_target, now, now),
    )

    for resource_type in ("food", "wood", "knowledge"):
        await db.execute(
            "INSERT OR IGNORE INTO village_resources (resource_type, amount, updated_at) VALUES (?, 0, ?)",
            (resource_type, now),
        )

    for building_type in ("gathering_field", "workshop", "hunting_ground", "research_lab"):
        await db.execute(
            "INSERT OR IGNORE INTO buildings (building_type, level, xp_progress, updated_at) VALUES (?, 0, 0, ?)",
            (building_type, now),
        )

    await db.execute(
        "INSERT OR IGNORE INTO guild_installations (guild_id, created_at, updated_at, is_active) VALUES (?, ?, ?, 1)",
        (get_discord_guild_id(), now, now),
    )

    await db.execute(
        "INSERT OR IGNORE INTO trial_state (id, is_active, target, progress, updated_at) VALUES (1, 0, 0, 0, ?)",
        (now,),
    )


async def _migrate_v2_columns(db):
    """Apply additive column migrations to existing v2 tables.

    Each migration is idempotent — it checks the current column list first and
    only runs the ALTER when the column is absent, so repeated calls are safe.
    """
    async with db.execute("PRAGMA table_info(players)") as cur:
        columns = {row[1] async for row in cur}

    if "risky_failed_levels" not in columns:
        await db.execute(
            "ALTER TABLE players ADD COLUMN risky_failed_levels INTEGER NOT NULL DEFAULT 0"
        )

    if "materials_universal" not in columns:
        await db.execute(
            "ALTER TABLE players ADD COLUMN materials_universal INTEGER NOT NULL DEFAULT 0"
        )


async def init_db():
    path = _resolve_db_path()
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

    async with aiosqlite.connect(path) as db:
        await _create_v2_tables(db)
        await _migrate_v2_columns(db)
        await _seed_initial_rows(db)
        await db.commit()


def get_connection():
    return aiosqlite.connect(_resolve_db_path())

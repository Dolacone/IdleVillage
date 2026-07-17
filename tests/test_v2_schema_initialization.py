import os
from datetime import datetime, timedelta, timezone

from support import DatabaseTestCase
from database import schema
from core.engine import Engine

V2_TABLE_NAMES = {
    "village_state",
    "stage_state",
    "village_resources",
    "buildings",
    "players",
    "guild_installations",
    "gear_affixes",
    "trial_state",
    "trial_contributions",
    "player_auto_tools",
}


class SchemaCreatesOnlyV2Tables(DatabaseTestCase):
    async def test_only_v2_table_names_exist_after_init(self):
        rows = await self.fetchall(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        actual = {row[0] for row in rows}
        self.assertEqual(actual, V2_TABLE_NAMES)


class SeedRowsExistAfterInit(DatabaseTestCase):
    async def test_village_state_singleton_row_seeded(self):
        row = await self.fetchone("SELECT id, announcement_channel_id FROM village_state WHERE id = 1")
        self.assertIsNotNone(row)
        self.assertEqual(row[0], 1)
        self.assertEqual(row[1], os.environ["ANNOUNCEMENT_CHANNEL_ID"])

    async def test_stage_state_singleton_row_seeded(self):
        row = await self.fetchone(
            """
            SELECT stages_cleared, current_stage_index, current_stage_type,
                   current_stage_progress, current_stage_target, overtime_notified
            FROM stage_state WHERE id = 1
            """
        )
        self.assertIsNotNone(row)
        stages_cleared, stage_index, stage_type, progress, target, overtime = row
        self.assertEqual(stages_cleared, 0)
        self.assertEqual(stage_index, 0)
        self.assertEqual(stage_type, "gathering")
        self.assertEqual(progress, 0)
        self.assertEqual(overtime, 0)

    async def test_stage_state_initial_target_equals_stage_base_target(self):
        row = await self.fetchone("SELECT current_stage_target FROM stage_state WHERE id = 1")
        self.assertIsNotNone(row)
        expected = int(os.environ["STAGE_BASE_TARGET"])
        self.assertEqual(row[0], expected)

    async def test_village_resources_seeded_with_food_wood_knowledge(self):
        rows = await self.fetchall("SELECT resource_type FROM village_resources ORDER BY resource_type")
        types = {row[0] for row in rows}
        self.assertEqual(types, {"food", "knowledge", "wood"})

    async def test_village_resources_initial_amounts_are_zero(self):
        rows = await self.fetchall("SELECT amount FROM village_resources")
        for (amount,) in rows:
            self.assertEqual(amount, 0)

    async def test_buildings_seeded_with_four_types(self):
        rows = await self.fetchall("SELECT building_type FROM buildings ORDER BY building_type")
        types = {row[0] for row in rows}
        self.assertEqual(types, {"gathering_field", "hunting_ground", "research_lab", "workshop"})

    async def test_buildings_initial_level_and_xp_are_zero(self):
        rows = await self.fetchall("SELECT level, xp_progress FROM buildings")
        for level, xp in rows:
            self.assertEqual(level, 0)
            self.assertEqual(xp, 0)

    async def test_guild_installations_seeded_with_discord_guild_id(self):
        row = await self.fetchone("SELECT guild_id, is_active FROM guild_installations")
        self.assertIsNotNone(row)
        self.assertEqual(row[0], os.environ["DISCORD_GUILD_ID"])
        self.assertEqual(row[1], 1)

    async def test_trial_state_singleton_row_seeded(self):
        row = await self.fetchone(
            "SELECT is_active, resource_type, target, progress, started_at, ended_at FROM trial_state WHERE id = 1"
        )
        self.assertIsNotNone(row)
        is_active, resource_type, target, progress, started_at, ended_at = row
        self.assertEqual(is_active, 0)
        self.assertIsNone(resource_type)
        self.assertEqual(target, 0)
        self.assertEqual(progress, 0)
        self.assertIsNone(started_at)
        self.assertIsNone(ended_at)

    async def test_trial_contributions_starts_empty(self):
        row = await self.fetchone("SELECT COUNT(*) FROM trial_contributions")
        self.assertEqual(row[0], 0)


class SchemaInitIsIdempotent(DatabaseTestCase):
    async def test_calling_init_db_twice_does_not_raise(self):
        await schema.init_db()

    async def test_calling_init_db_twice_does_not_duplicate_seed_rows(self):
        await schema.init_db()
        row = await self.fetchone("SELECT COUNT(*) FROM village_state")
        self.assertEqual(row[0], 1)
        row = await self.fetchone("SELECT COUNT(*) FROM stage_state")
        self.assertEqual(row[0], 1)
        row = await self.fetchone("SELECT COUNT(*) FROM guild_installations")
        self.assertEqual(row[0], 1)
        row = await self.fetchone("SELECT COUNT(*) FROM village_resources")
        self.assertEqual(row[0], 3)
        row = await self.fetchone("SELECT COUNT(*) FROM buildings")
        self.assertEqual(row[0], 4)
        row = await self.fetchone("SELECT COUNT(*) FROM trial_state")
        self.assertEqual(row[0], 1)


class MigratesLegacyPlayersMissingUniversalMaterial(DatabaseTestCase):
    """A players table from before materials_universal existed must be migrated in place."""

    async def asyncSetUp(self):
        await super().asyncSetUp()
        from database.schema import get_connection

        now = "2026-01-01T00:00:00+00:00"
        async with get_connection() as db:
            await db.execute("DROP TABLE players")
            await db.execute(
                """
                CREATE TABLE players (
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
                "INSERT INTO players (user_id, created_at, updated_at, ap_full_time, materials_gathering) "
                "VALUES (?, ?, ?, ?, 7)",
                ("legacy_user", now, now, now),
            )
            await db.commit()

    async def test_init_db_adds_materials_universal_with_default_zero(self):
        await schema.init_db()
        row = await self.fetchone(
            "SELECT materials_gathering, materials_universal FROM players WHERE user_id=?",
            ("legacy_user",),
        )
        self.assertEqual(row[0], 7)
        self.assertEqual(row[1], 0)


class PlayerIndexesExist(DatabaseTestCase):
    async def test_completion_time_index_exists(self):
        row = await self.fetchone(
            "SELECT 1 FROM sqlite_master WHERE type='index' AND name='idx_players_completion_time'"
        )
        self.assertIsNotNone(row)

    async def test_action_index_exists(self):
        row = await self.fetchone(
            "SELECT 1 FROM sqlite_master WHERE type='index' AND name='idx_players_action'"
        )
        self.assertIsNotNone(row)


class PlayerAutoToolsTable(DatabaseTestCase):
    async def test_table_exists_with_expected_columns(self):
        rows = await self.fetchall("PRAGMA table_info(player_auto_tools)")
        cols = {row[1] for row in rows}
        self.assertEqual(
            cols,
            {"user_id", "tool_type", "action_target", "completion_time",
             "last_update_time", "expires_at", "started_at", "updated_at"},
        )

    async def test_primary_key_is_user_id_tool_type(self):
        rows = await self.fetchall("PRAGMA table_info(player_auto_tools)")
        pk_cols = {row[1] for row in rows if row[5] > 0}
        self.assertEqual(pk_cols, {"user_id", "tool_type"})

    async def test_completion_index_exists(self):
        row = await self.fetchone(
            "SELECT 1 FROM sqlite_master WHERE type='index' AND name='idx_auto_tools_completion'"
        )
        self.assertIsNotNone(row)

    async def test_new_table_autocreated_on_existing_db(self):
        # Dropping then re-running init_db() (idempotent CREATE IF NOT EXISTS)
        # recreates the table without ALTER migration.
        async with schema.get_connection() as db:
            await db.execute("DROP TABLE player_auto_tools")
            await db.commit()
        await schema.init_db()
        row = await self.fetchone(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='player_auto_tools'"
        )
        self.assertIsNotNone(row)


class WatcherTrialTimeout(DatabaseTestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self._original_bot = Engine.bot

    async def asyncTearDown(self):
        Engine.bot = self._original_bot
        await super().asyncTearDown()

    async def _write_active_trial(self, started_at):
        now_str = datetime.now(timezone.utc).isoformat()
        async with schema.get_connection() as db:
            await db.execute(
                """UPDATE trial_state SET
                   is_active=1, resource_type='food', target=1000, progress=100,
                   started_at=?, updated_at=?
                   WHERE id=1""",
                (started_at.isoformat(), now_str),
            )
            await db.commit()

    async def test_watcher_tick_fails_expired_trial_with_no_due_players(self):
        from unittest.mock import AsyncMock, patch

        now = datetime.now(timezone.utc)
        await self._write_active_trial(now - timedelta(seconds=90000))
        Engine.bot = object()

        with patch("core.notification.dispatch_events", new=AsyncMock()) as dispatch:
            await Engine.process_watcher()

        dispatch.assert_awaited_once()
        _, dispatched_events = dispatch.call_args[0]
        self.assertEqual([e["type"] for e in dispatched_events], ["trial_fail"])

        row = await self.fetchone("SELECT is_active FROM trial_state WHERE id=1")
        self.assertEqual(row[0], 0)

    async def test_watcher_tick_leaves_unexpired_trial_untouched(self):
        now = datetime.now(timezone.utc)
        await self._write_active_trial(now)

        await Engine.process_watcher()

        row = await self.fetchone("SELECT is_active, progress FROM trial_state WHERE id=1")
        self.assertEqual(row[0], 1)
        self.assertEqual(row[1], 100)

    async def test_watcher_tick_no_event_when_no_active_trial(self):
        await Engine.process_watcher()
        row = await self.fetchone("SELECT is_active FROM trial_state WHERE id=1")
        self.assertEqual(row[0], 0)


class WatcherIsV2Safe(DatabaseTestCase):
    async def test_process_watcher_does_not_raise_on_v2_schema(self):
        try:
            await Engine.process_watcher()
        except Exception as e:
            self.fail(f"process_watcher() raised {type(e).__name__} on v2 schema: {e}")

    async def test_process_watcher_settles_due_v2_player(self):
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        cycle_end = now - timedelta(minutes=1)
        last_update = now - timedelta(minutes=11)

        async with schema.get_connection() as db:
            await db.execute(
                """INSERT INTO players
                   (user_id, created_at, updated_at, action, action_target,
                    completion_time, last_update_time, ap_full_time)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (
                    "watcher-player",
                    last_update.isoformat(),
                    last_update.isoformat(),
                    "gathering",
                    None,
                    cycle_end.isoformat(),
                    last_update.isoformat(),
                    now.isoformat(),
                ),
            )
            await db.commit()

        await Engine.process_watcher()

        wood = await self.fetchone(
            "SELECT amount FROM village_resources WHERE resource_type='wood'"
        )
        player = await self.fetchone(
            "SELECT completion_time FROM players WHERE user_id='watcher-player'"
        )

        self.assertEqual(wood[0], 10)
        result_ct = datetime.fromisoformat(player[0])
        if result_ct.tzinfo is None:
            result_ct = result_ct.replace(tzinfo=timezone.utc)
        self.assertGreater(result_ct, cycle_end.replace(tzinfo=timezone.utc))

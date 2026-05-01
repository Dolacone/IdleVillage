import os
import tempfile

import aiosqlite

from support import DatabaseTestCase
from database import schema
from core.config import REQUIRED_KEYS
from core.engine import Engine

V2_TABLE_NAMES = {
    "village_state",
    "stage_state",
    "village_resources",
    "buildings",
    "players",
    "guild_installations",
}


class SchemaCreatesOnlyV2Tables(DatabaseTestCase):
    async def test_only_v2_table_names_exist_after_init(self):
        rows = await self.fetchall(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        actual = {row[0] for row in rows}
        self.assertEqual(actual, V2_TABLE_NAMES)

    async def test_no_v1_tables_exist_after_init(self):
        for v1_table in schema.V1_TABLE_NAMES:
            row = await self.fetchone(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (v1_table,)
            )
            self.assertIsNone(row, f"v1 table '{v1_table}' must not exist after v2 init")


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


class V1DetectionPreventsStartup(DatabaseTestCase):
    async def test_v1_table_causes_init_db_to_raise(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "legacy.db")
            async with aiosqlite.connect(db_path) as db:
                await db.execute("CREATE TABLE villages (id INTEGER PRIMARY KEY)")
                await db.commit()

            original = schema.DB_PATH
            schema.DB_PATH = db_path
            try:
                with self.assertRaises(RuntimeError) as ctx:
                    await schema.init_db()
                self.assertIn("villages", str(ctx.exception))
                self.assertIn("v1", str(ctx.exception))
            finally:
                schema.DB_PATH = original

    async def test_error_message_lists_all_detected_v1_tables(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "legacy.db")
            async with aiosqlite.connect(db_path) as db:
                await db.execute("CREATE TABLE villages (id INTEGER PRIMARY KEY)")
                await db.execute("CREATE TABLE buffs (id INTEGER PRIMARY KEY)")
                await db.commit()

            original = schema.DB_PATH
            schema.DB_PATH = db_path
            try:
                with self.assertRaises(RuntimeError) as ctx:
                    await schema.init_db()
                msg = str(ctx.exception)
                self.assertIn("villages", msg)
                self.assertIn("buffs", msg)
            finally:
                schema.DB_PATH = original


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


class WatcherIsV2Safe(DatabaseTestCase):
    async def test_process_watcher_does_not_raise_on_v2_schema(self):
        # Watcher must skip gracefully on a v2 DB (no villages table).
        # An exception here would mean the background loop crashes every heartbeat.
        try:
            await Engine.process_watcher()
        except Exception as e:
            self.fail(f"process_watcher() raised {type(e).__name__} on v2 schema: {e}")

    async def test_process_watcher_skips_when_villages_table_absent(self):
        # Confirms no settlement queries run against missing v1 tables.
        # After the guard, the v2 players table must remain empty (no writes attempted).
        await Engine.process_watcher()
        row = await self.fetchone("SELECT COUNT(*) FROM players")
        self.assertEqual(row[0], 0)

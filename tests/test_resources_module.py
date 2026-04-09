from datetime import datetime, timedelta
from unittest.mock import patch

from support import DatabaseTestCase
from core.engine import Engine
from database import schema


class ResourcesModuleBehaviorTests(DatabaseTestCase):
    async def test_resources_migration_merges_duplicate_nodes_and_retargets_gatherers(self):
        village_id = await self.create_village()
        keeper_id = await self.create_resource_node(
            village_id,
            node_type="wood",
            quality=100,
            remaining_amount=100,
            expiry_time=datetime.utcnow() + timedelta(hours=4),
        )
        duplicate_id = await self.create_resource_node(
            village_id,
            node_type="wood",
            quality=150,
            remaining_amount=50,
            expiry_time=datetime.utcnow() + timedelta(hours=8),
        )
        player_discord_id = await self.create_player(
            village_id,
            status="gathering",
            target_id=duplicate_id,
            last_update_time=datetime.utcnow(),
            completion_time=datetime.utcnow() + timedelta(hours=1),
        )

        await schema.init_db()

        nodes = await self.fetchall(
            """
            SELECT id, type, quality, remaining_amount, expiry_time
            FROM resource_nodes
            WHERE village_id = ?
            ORDER BY id
            """,
            (village_id,),
        )
        player = await self.fetchone(
            "SELECT status, target_id FROM players WHERE discord_id = ? AND village_id = ?",
            (player_discord_id, village_id),
        )

        self.assertEqual(nodes, [(duplicate_id, "wood", 116, 150, None)])
        self.assertEqual(player, ("gathering", duplicate_id))
        self.assertNotEqual(keeper_id, duplicate_id)

    async def test_resources_migration_is_safe_to_run_multiple_times(self):
        village_id = await self.create_village()
        await self.create_resource_node(
            village_id,
            node_type="stone",
            quality=100,
            remaining_amount=7950,
        )
        await self.create_resource_node(
            village_id,
            node_type="stone",
            quality=400,
            remaining_amount=100,
        )

        await schema.init_db()
        await schema.init_db()

        nodes = await self.fetchall(
            """
            SELECT type, quality, remaining_amount, expiry_time
            FROM resource_nodes
            WHERE village_id = ?
            """,
            (village_id,),
        )
        self.assertEqual(nodes, [("stone", 103, 8000, None)])

    async def test_resources_idle_state_produces_food_without_food_cost(self):
        village_id = await self.create_village(food=0)
        now = datetime.utcnow()
        player_discord_id = await self.create_player(
            village_id,
            status="idle",
            last_update_time=now - timedelta(hours=2),
            completion_time=None,
        )

        async with __import__("database.schema", fromlist=["schema"]).get_connection() as db:
            await Engine.settle_player(player_discord_id, village_id, db)

        village = await self.fetchone("SELECT food FROM villages WHERE id = ?", (village_id,))
        self.assertEqual(village[0], 25)

    async def test_resources_gathering_food_uses_node_quality_and_yield_bonus(self):
        village_id = await self.create_village(resource_yield_xp=1000)
        node_id = await self.create_resource_node(village_id, node_type="food", quality=150, remaining_amount=50)
        now = datetime.utcnow()
        player_discord_id = await self.create_player(
            village_id,
            status="gathering",
            target_id=node_id,
            last_update_time=now - timedelta(hours=1),
            completion_time=now,
        )

        async with __import__("database.schema", fromlist=["schema"]).get_connection() as db:
            await Engine.settle_player(player_discord_id, village_id, db, interrupted=True)

        village = await self.fetchone("SELECT food FROM villages WHERE id = ?", (village_id,))
        node = await self.fetchone("SELECT remaining_amount FROM resource_nodes WHERE id = ?", (node_id,))
        self.assertEqual(village[0], 41)
        self.assertEqual(node[0], 9)

    async def test_buildings_resource_yield_bonus_increases_idle_output(self):
        village_id = await self.create_village(resource_yield_xp=1000)
        now = datetime.utcnow()
        player_discord_id = await self.create_player(
            village_id,
            status="idle",
            last_update_time=now - timedelta(hours=2),
        )

        async with __import__("database.schema", fromlist=["schema"]).get_connection() as db:
            await Engine.settle_player(player_discord_id, village_id, db)

        village = await self.fetchone("SELECT food FROM villages WHERE id = ?", (village_id,))
        self.assertEqual(village[0], 27)

    async def test_resources_exploring_creates_a_node_from_successful_roll(self):
        village_id = await self.create_village()
        now = datetime.utcnow()
        player_discord_id = await self.create_player(
            village_id,
            status="exploring",
            last_update_time=now - timedelta(hours=1),
            completion_time=now,
        )

        with patch("core.engine.random.random", return_value=0.0), patch("core.engine.random.choice", return_value="stone"), patch("core.engine.random.gauss", return_value=140), patch("core.engine.random.randint", return_value=700):
            async with __import__("database.schema", fromlist=["schema"]).get_connection() as db:
                await Engine.settle_player(player_discord_id, village_id, db, interrupted=True)

        nodes = await self.fetchall(
            "SELECT type, quality, remaining_amount FROM resource_nodes WHERE village_id = ?",
            (village_id,),
        )
        self.assertEqual(nodes, [("stone", 140, 700)])

    async def test_resources_exploring_replenishes_existing_singleton_node_with_weighted_quality(self):
        village_id = await self.create_village()
        await self.create_resource_node(village_id, node_type="wood", quality=100, remaining_amount=100)
        now = datetime.utcnow()
        player_discord_id = await self.create_player(
            village_id,
            status="exploring",
            last_update_time=now - timedelta(hours=1),
            completion_time=now,
        )

        with patch("core.engine.random.random", return_value=0.0), patch("core.engine.random.choice", return_value="wood"), patch("core.engine.random.gauss", return_value=150), patch("core.engine.random.randint", return_value=50):
            async with __import__("database.schema", fromlist=["schema"]).get_connection() as db:
                await Engine.settle_player(player_discord_id, village_id, db, interrupted=True)

        nodes = await self.fetchall(
            "SELECT type, quality, remaining_amount FROM resource_nodes WHERE village_id = ? ORDER BY id",
            (village_id,),
        )
        self.assertEqual(nodes, [("wood", 116, 150)])

    async def test_resources_exploring_caps_singleton_stock_but_still_updates_quality(self):
        village_id = await self.create_village()
        await self.create_resource_node(village_id, node_type="wood", quality=100, remaining_amount=7950)
        now = datetime.utcnow()
        player_discord_id = await self.create_player(
            village_id,
            status="exploring",
            last_update_time=now - timedelta(hours=1),
            completion_time=now,
        )

        with patch("core.engine.random.random", return_value=0.0), patch("core.engine.random.choice", return_value="wood"), patch("core.engine.random.gauss", return_value=400), patch("core.engine.random.randint", return_value=100):
            async with __import__("database.schema", fromlist=["schema"]).get_connection() as db:
                await Engine.settle_player(player_discord_id, village_id, db, interrupted=True)

        node = await self.fetchone(
            "SELECT type, quality, remaining_amount FROM resource_nodes WHERE village_id = ?",
            (village_id,),
        )
        self.assertEqual(node, ("wood", 103, 8000))

    async def test_resources_gathering_clamps_quality_to_seventy_five_percent(self):
        village_id = await self.create_village()
        node_id = await self.create_resource_node(village_id, node_type="wood", quality=20, remaining_amount=100)
        now = datetime.utcnow()
        player_discord_id = await self.create_player(
            village_id,
            status="gathering",
            target_id=node_id,
            last_update_time=now - timedelta(hours=1),
            completion_time=now,
        )

        async with __import__("database.schema", fromlist=["schema"]).get_connection() as db:
            await Engine.settle_player(player_discord_id, village_id, db, interrupted=True)

        village = await self.fetchone("SELECT wood FROM villages WHERE id = ?", (village_id,))
        self.assertEqual(village[0], 18)

    async def test_resources_exploring_uses_stats_based_discovery_probability(self):
        village_id = await self.create_village()
        await self.create_resource_node(village_id, node_type="food")
        await self.create_resource_node(village_id, node_type="wood")
        now = datetime.utcnow()
        player_discord_id = await self.create_player(
            village_id,
            status="exploring",
            last_update_time=now - timedelta(hours=1),
            completion_time=now,
        )

        with patch("core.engine.random.random", return_value=0.3):
            async with __import__("database.schema", fromlist=["schema"]).get_connection() as db:
                await Engine.settle_player(player_discord_id, village_id, db, interrupted=True)

        node_count = await self.fetchone("SELECT count(*) FROM resource_nodes WHERE village_id = ?", (village_id,))
        self.assertEqual(node_count[0], 2)

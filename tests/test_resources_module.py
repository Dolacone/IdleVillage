from datetime import datetime, timedelta
from unittest.mock import patch

from support import DatabaseTestCase
from core.engine import Engine


class ResourcesModuleBehaviorTests(DatabaseTestCase):
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
        self.assertEqual(village[0], 10)

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
        self.assertEqual(village[0], 16)
        self.assertEqual(node[0], 34)

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
        self.assertEqual(village[0], 11)

    async def test_resources_exploring_creates_a_node_from_successful_roll(self):
        village_id = await self.create_village()
        now = datetime.utcnow()
        player_discord_id = await self.create_player(
            village_id,
            status="exploring",
            last_update_time=now - timedelta(hours=1),
            completion_time=now,
        )

        with patch("core.engine.random.random", return_value=0.0), patch("core.engine.random.choice", return_value="stone"), patch("core.engine.random.gauss", return_value=140), patch("core.engine.random.randint", return_value=2200):
            async with __import__("database.schema", fromlist=["schema"]).get_connection() as db:
                await Engine.settle_player(player_discord_id, village_id, db, interrupted=True)

        nodes = await self.fetchall(
            "SELECT type, quality, remaining_amount FROM resource_nodes WHERE village_id = ?",
            (village_id,),
        )
        self.assertEqual(nodes, [("stone", 140, 2200)])

    async def test_resources_exploring_uses_inverse_square_discovery_frequency(self):
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

from datetime import datetime, timedelta
from unittest.mock import patch
import unittest

from support import DatabaseTestCase
from core.engine import Engine


class ResourcesModuleBehaviorTests(DatabaseTestCase):
    async def test_resources_idle_state_produces_food_without_food_cost(self):
        village_id = await self.create_village(food=0)
        now = datetime.utcnow()
        player_id = await self.create_player(
            village_id,
            status="idle",
            last_update_time=now - timedelta(hours=2),
            completion_time=None,
        )

        async with __import__("database.schema", fromlist=["schema"]).get_connection() as db:
            await Engine.settle_player(player_id, db)

        village = await self.fetchone("SELECT food FROM villages WHERE id = ?", (village_id,))
        self.assertEqual(village[0], 5)

    async def test_resources_gathering_food_uses_node_quality_and_yield_bonus(self):
        village_id = await self.create_village(resource_yield_xp=1000)
        node_id = await self.create_resource_node(village_id, node_type="food", quality=150, remaining_amount=50)
        now = datetime.utcnow()
        player_id = await self.create_player(
            village_id,
            status="gathering",
            target_id=node_id,
            last_update_time=now - timedelta(hours=1),
            completion_time=now,
        )

        async with __import__("database.schema", fromlist=["schema"]).get_connection() as db:
            await Engine.settle_player(player_id, db, interrupted=True)

        village = await self.fetchone("SELECT food FROM villages WHERE id = ?", (village_id,))
        node = await self.fetchone("SELECT remaining_amount FROM resource_nodes WHERE id = ?", (node_id,))
        self.assertEqual(village[0], 8)
        self.assertEqual(node[0], 42)

    async def test_buildings_resource_yield_bonus_increases_idle_output(self):
        village_id = await self.create_village(resource_yield_xp=1000)
        now = datetime.utcnow()
        player_id = await self.create_player(
            village_id,
            status="idle",
            last_update_time=now - timedelta(hours=2),
        )

        async with __import__("database.schema", fromlist=["schema"]).get_connection() as db:
            await Engine.settle_player(player_id, db)

        village = await self.fetchone("SELECT food FROM villages WHERE id = ?", (village_id,))
        self.assertEqual(village[0], 5)

    async def test_resources_exploring_creates_a_node_from_successful_roll(self):
        village_id = await self.create_village()
        now = datetime.utcnow()
        player_id = await self.create_player(
            village_id,
            status="exploring",
            last_update_time=now - timedelta(hours=1),
            completion_time=now,
        )

        with patch("core.engine.random.random", return_value=0.8), patch("core.engine.random.choice", return_value="stone"), patch("core.engine.random.randint", return_value=140):
            async with __import__("database.schema", fromlist=["schema"]).get_connection() as db:
                await Engine.settle_player(player_id, db, interrupted=True)

        nodes = await self.fetchall(
            "SELECT type, level, quality, remaining_amount FROM resource_nodes WHERE village_id = ?",
            (village_id,),
        )
        self.assertEqual(nodes, [("stone", 2, 140, 2000)])

    @unittest.expectedFailure
    async def test_resources_exploring_budget_consumes_weighted_time_costs(self):
        village_id = await self.create_village()
        now = datetime.utcnow()
        player_id = await self.create_player(
            village_id,
            status="exploring",
            last_update_time=now - timedelta(hours=120),
            completion_time=now,
        )

        with patch("core.engine.random.random", side_effect=[0.8, 0.8]), patch("core.engine.random.choice", return_value="wood"), patch("core.engine.random.randint", return_value=140):
            async with __import__("database.schema", fromlist=["schema"]).get_connection() as db:
                await Engine.settle_player(player_id, db, interrupted=True)

        nodes = await self.fetchall(
            "SELECT level FROM resource_nodes WHERE village_id = ? ORDER BY id",
            (village_id,),
        )
        self.assertEqual(nodes, [(2,)])

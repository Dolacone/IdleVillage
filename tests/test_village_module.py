from datetime import datetime, timedelta
import unittest

from support import DatabaseTestCase
from core.engine import Engine


class VillageModuleBehaviorTests(DatabaseTestCase):

    async def test_village_pre_deduction_applies_at_action_start(self):
        village_id = await self.create_village(food=5, wood=20, stone=10, food_efficiency_xp=1000)
        player_id = await self.create_player(village_id)

        success = await Engine.start_action(player_id, "building", 1)

        self.assertTrue(success)
        village = await self.fetchone(
            "SELECT food, wood, stone FROM villages WHERE id = ?",
            (village_id,),
        )
        self.assertEqual(village, (4, 10, 5))

        player = await self.fetchone(
            "SELECT status, target_id, last_update_time, completion_time FROM players WHERE id = ?",
            (player_id,),
        )
        self.assertEqual(player[0], "building")
        self.assertEqual(player[1], 1)

        last_update = Engine._parse_timestamp(player[2])
        completion = Engine._parse_timestamp(player[3])
        duration_hours = (completion - last_update).total_seconds() / 3600.0
        self.assertAlmostEqual(duration_hours, 1.2, places=2)

    async def test_village_hybrid_decay_uses_base_plus_active_players(self):
        last_tick = datetime.utcnow() - timedelta(hours=2)
        village_id = await self.create_village(
            food_efficiency_xp=100,
            storage_capacity_xp=100,
            resource_yield_xp=100,
            last_tick_time=last_tick,
        )
        await self.create_player(village_id, last_message_time=datetime.utcnow(), status="idle")

        async with __import__("database.schema", fromlist=["schema"]).get_connection() as db:
            await Engine.settle_village(village_id, db)

        village = await self.fetchone(
            """
            SELECT food_efficiency_xp, storage_capacity_xp, resource_yield_xp
            FROM villages WHERE id = ?
            """,
            (village_id,),
        )
        self.assertEqual(village, (78, 78, 78))

    async def test_village_interrupted_action_settles_partial_progress(self):
        village_id = await self.create_village()
        node_id = await self.create_resource_node(village_id, node_type="food", quality=100, remaining_amount=100)
        now = datetime.utcnow()
        player_id = await self.create_player(
            village_id,
            status="gathering",
            target_id=node_id,
            last_message_time=None,
            last_update_time=now - timedelta(minutes=30),
            completion_time=now + timedelta(minutes=30),
        )

        async with __import__("database.schema", fromlist=["schema"]).get_connection() as db:
            await Engine.settle_player(player_id, db, interrupted=True)

        village = await self.fetchone("SELECT food FROM villages WHERE id = ?", (village_id,))
        player = await self.fetchone("SELECT status, target_id, completion_time FROM players WHERE id = ?", (player_id,))
        node = await self.fetchone("SELECT remaining_amount FROM resource_nodes WHERE id = ?", (node_id,))
        log = await self.fetchone(
            "SELECT action_type FROM player_actions_log WHERE player_id = ? ORDER BY id DESC LIMIT 1",
            (player_id,),
        )

        self.assertEqual(village[0], 2)
        self.assertEqual(player, ("idle", None, None))
        self.assertEqual(node[0], 98)
        self.assertEqual(log[0], "gathering_food")

    @unittest.expectedFailure
    async def test_resources_gathering_requires_a_real_node(self):
        village_id = await self.create_village(food=3)
        player_id = await self.create_player(village_id)

        success = await Engine.start_action(player_id, "gathering", None)

        self.assertFalse(success)
        village = await self.fetchone("SELECT food FROM villages WHERE id = ?", (village_id,))
        player = await self.fetchone("SELECT status FROM players WHERE id = ?", (player_id,))
        self.assertEqual(village[0], 3)
        self.assertEqual(player[0], "idle")


if __name__ == "__main__":
    unittest.main()

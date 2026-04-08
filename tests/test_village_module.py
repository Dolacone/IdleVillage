import os
from datetime import datetime, timedelta

from support import DatabaseTestCase
from core.engine import Engine


class VillageModuleBehaviorTests(DatabaseTestCase):
    async def test_village_pre_deduction_uses_food_efficiency_and_cycle_minutes(self):
        os.environ["ACTION_CYCLE_MINUTES"] = "30"
        village_id = await self.create_village(food=15, wood=20, stone=10, food_efficiency_xp=1000)
        player_discord_id = await self.create_player(village_id)

        success = await Engine.start_action(player_discord_id, village_id, "building", 1)

        self.assertTrue(success)
        village = await self.fetchone("SELECT food, wood, stone FROM villages WHERE id = ?", (village_id,))
        self.assertEqual(village, (6, 10, 5))

        player = await self.fetchone(
            """
            SELECT status, target_id, last_update_time, completion_time
            FROM players
            WHERE discord_id = ? AND village_id = ?
            """,
            (player_discord_id, village_id),
        )
        self.assertEqual(player[0], "building")
        self.assertEqual(player[1], 1)

        last_update = Engine._parse_timestamp(player[2])
        completion = Engine._parse_timestamp(player[3])
        duration_minutes = (completion - last_update).total_seconds() / 60.0
        self.assertAlmostEqual(duration_minutes, 30.0, places=2)

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

    async def test_village_decay_uses_cycle_units_for_short_heartbeat(self):
        os.environ["ACTION_CYCLE_MINUTES"] = "1"
        last_tick = datetime.utcnow() - timedelta(seconds=60)
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
        self.assertEqual(village, (89, 89, 89))

    async def test_village_interrupted_action_settles_partial_progress(self):
        village_id = await self.create_village(food=0)
        node_id = await self.create_resource_node(village_id, node_type="food", quality=100, remaining_amount=100)
        now = datetime.utcnow()
        player_discord_id = await self.create_player(
            village_id,
            status="gathering",
            target_id=node_id,
            last_message_time=None,
            last_update_time=now - timedelta(minutes=30),
            completion_time=now + timedelta(minutes=30),
        )

        async with __import__("database.schema", fromlist=["schema"]).get_connection() as db:
            await Engine.settle_player(player_discord_id, village_id, db, interrupted=True)

        village = await self.fetchone("SELECT food FROM villages WHERE id = ?", (village_id,))
        player = await self.fetchone(
            """
            SELECT status, target_id, completion_time
            FROM players
            WHERE discord_id = ? AND village_id = ?
            """,
            (player_discord_id, village_id),
        )
        node = await self.fetchone("SELECT remaining_amount FROM resource_nodes WHERE id = ?", (node_id,))
        log_row = await self.fetchone(
            """
            SELECT action_type
            FROM player_actions_log
            WHERE player_discord_id = ? AND village_id = ?
            ORDER BY id DESC LIMIT 1
            """,
            (player_discord_id, village_id),
        )

        self.assertEqual(village[0], 5)
        self.assertEqual(player, ("idle", None, None))
        self.assertEqual(node[0], 95)
        self.assertEqual(log_row[0], "gathering_food")

    async def test_resources_gathering_requires_a_real_node(self):
        village_id = await self.create_village(food=3)
        player_discord_id = await self.create_player(village_id)

        success = await Engine.start_action(player_discord_id, village_id, "gathering", None)

        self.assertFalse(success)
        village = await self.fetchone("SELECT food FROM villages WHERE id = ?", (village_id,))
        player = await self.fetchone(
            "SELECT status FROM players WHERE discord_id = ? AND village_id = ?",
            (player_discord_id, village_id),
        )
        self.assertEqual(village[0], 3)
        self.assertEqual(player[0], "idle")

    async def test_ui_refresh_keeps_next_cycle_when_action_has_already_completed(self):
        village_id = await self.create_village(food=20, wood=20, stone=10)
        now = datetime.utcnow()
        player_discord_id = await self.create_player(
            village_id,
            status="building",
            target_id=1,
            last_update_time=now - timedelta(hours=2),
            completion_time=now - timedelta(hours=1),
        )

        async with __import__("database.schema", fromlist=["schema"]).get_connection() as db:
            await Engine.settle_player(player_discord_id, village_id, db, is_ui_refresh=True)

        player = await self.fetchone(
            """
            SELECT status, target_id, completion_time
            FROM players
            WHERE discord_id = ? AND village_id = ?
            """,
            (player_discord_id, village_id),
        )
        self.assertEqual(player[0], "building")
        self.assertEqual(player[1], 1)
        self.assertIsNotNone(player[2])

    async def test_settlement_backfills_multiple_completed_cycles(self):
        os.environ["ACTION_CYCLE_MINUTES"] = "1"
        village_id = await self.create_village(food=100, wood=100, stone=100)
        player_discord_id = await self.create_player(village_id)

        async with __import__("database.schema", fromlist=["schema"]).get_connection() as db:
            started = await Engine.start_action(player_discord_id, village_id, "building", 1, db=db)
            self.assertTrue(started)

            now = datetime.utcnow()
            await db.execute(
                """
                UPDATE players
                SET last_update_time = ?, completion_time = ?
                WHERE discord_id = ? AND village_id = ?
                """,
                (
                    (now - timedelta(minutes=5)).isoformat(),
                    (now - timedelta(minutes=4)).isoformat(),
                    player_discord_id,
                    village_id,
                ),
            )
            await db.commit()

            await Engine.settle_player(player_discord_id, village_id, db)

        village = await self.fetchone(
            "SELECT food, wood, stone, food_efficiency_xp FROM villages WHERE id = ?",
            (village_id,),
        )
        player = await self.fetchone(
            """
            SELECT status, target_id, completion_time
            FROM players
            WHERE discord_id = ? AND village_id = ?
            """,
            (player_discord_id, village_id),
        )
        logs = await self.fetchone(
            """
            SELECT count(*)
            FROM player_actions_log
            WHERE player_discord_id = ? AND village_id = ? AND action_type = 'building'
            """,
            (player_discord_id, village_id),
        )

        self.assertEqual(village, (40, 40, 70, 50))
        self.assertEqual(player[0], "building")
        self.assertEqual(player[1], 1)
        self.assertIsNotNone(player[2])
        self.assertEqual(logs[0], 5)

    async def test_settlement_recalculates_stats_during_backfill(self):
        os.environ["ACTION_CYCLE_MINUTES"] = "1"
        village_id = await self.create_village(food=100, wood=100, stone=100)
        player_discord_id = await self.create_player(village_id)
        now = datetime.utcnow()

        async with __import__("database.schema", fromlist=["schema"]).get_connection() as db:
            entries = []
            for index in range(49):
                end_time = now - timedelta(minutes=50 - index)
                start_time = end_time - timedelta(minutes=1)
                entries.append((player_discord_id, village_id, "building", start_time.isoformat(), end_time.isoformat()))
            await db.executemany(
                """
                INSERT INTO player_actions_log (player_discord_id, village_id, action_type, start_time, end_time)
                VALUES (?, ?, ?, ?, ?)
                """,
                entries,
            )
            await db.commit()

            started = await Engine.start_action(player_discord_id, village_id, "building", 1, db=db)
            self.assertTrue(started)

            await db.execute(
                """
                UPDATE players
                SET last_update_time = ?, completion_time = ?
                WHERE discord_id = ? AND village_id = ?
                """,
                (
                    (now - timedelta(minutes=5)).isoformat(),
                    (now - timedelta(minutes=4)).isoformat(),
                    player_discord_id,
                    village_id,
                ),
            )
            await db.commit()

            await Engine.settle_player(player_discord_id, village_id, db)

        village = await self.fetchone(
            "SELECT food_efficiency_xp FROM villages WHERE id = ?",
            (village_id,),
        )
        self.assertEqual(village[0], 99)

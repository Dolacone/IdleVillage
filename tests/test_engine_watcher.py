from datetime import datetime, timedelta

from support import DatabaseTestCase
from database import schema
from core.engine import Engine


class EngineWatcherBehaviorTests(DatabaseTestCase):
    async def test_engine_watcher_leaves_resource_nodes_intact_and_settles_due_players(self):
        village_id = await self.create_village(food=5)
        expired_node_id = await self.create_resource_node(
            village_id,
            expiry_time=datetime.utcnow() - timedelta(minutes=1),
        )
        active_node_id = await self.create_resource_node(
            village_id,
            node_type="wood",
            expiry_time=datetime.utcnow() + timedelta(hours=4),
        )
        now = datetime.utcnow()
        player_discord_id = await self.create_player(
            village_id,
            status="idle",
            last_message_time="",
            last_update_time=now - timedelta(hours=1),
            completion_time=now,
        )

        await Engine.process_watcher()

        expired_node = await self.fetchone("SELECT id FROM resource_nodes WHERE id = ?", (expired_node_id,))
        active_node = await self.fetchone("SELECT id FROM resource_nodes WHERE id = ?", (active_node_id,))
        resources = await self.fetch_resources(village_id)
        logs = await self.fetchall(
            """
            SELECT action_type
            FROM player_actions_log
            WHERE player_discord_id = ? AND village_id = ?
            """,
            (player_discord_id, village_id),
        )

        self.assertEqual(expired_node[0], expired_node_id)
        self.assertEqual(active_node[0], active_node_id)
        self.assertEqual(resources["food"], 17)
        self.assertEqual(logs, [("idle",)])

    async def test_player_system_inactive_players_become_missing_after_7_days(self):
        village_id = await self.create_village()
        now = datetime.utcnow()
        player_discord_id = await self.create_player(
            village_id,
            status="building",
            target_id=1,
            last_message_time=now - timedelta(days=8),
            last_command_time=now - timedelta(days=8),
            last_update_time=now - timedelta(days=8),
            completion_time=now - timedelta(days=7, minutes=1),
        )

        async with schema.get_connection() as db:
            await Engine.settle_player(player_discord_id, village_id, db)

        player = await self.fetchone(
            "SELECT status, target_id FROM players WHERE discord_id = ? AND village_id = ?",
            (player_discord_id, village_id),
        )
        self.assertEqual(player, ("missing", None))

    async def test_watcher_marks_idle_inactive_players_missing_before_decay_count(self):
        village_id = await self.create_village(
            food_efficiency_xp=100,
            storage_capacity_xp=100,
            resource_yield_xp=100,
            last_tick_time=datetime.utcnow() - timedelta(hours=1),
        )
        player_discord_id = await self.create_player(
            village_id,
            status="idle",
            last_message_time=datetime.utcnow() - timedelta(days=8),
            last_command_time=datetime.utcnow() - timedelta(days=8),
            last_update_time=datetime.utcnow(),
            completion_time=None,
        )

        await Engine.process_watcher(req_id="WATCHER")

        player = await self.fetchone(
            "SELECT status, target_id FROM players WHERE discord_id = ? AND village_id = ?",
            (player_discord_id, village_id),
        )
        buffs = await self.fetch_buffs(village_id)

        self.assertEqual(player, ("missing", None))
        self.assertEqual(buffs, {1: 100, 2: 100, 3: 100, 4: 0})

    async def test_in_game_actions_do_not_prevent_missing_when_message_and_command_are_stale(self):
        village_id = await self.create_village()
        now = datetime.utcnow()
        player_discord_id = await self.create_player(
            village_id,
            status="building",
            target_id=1,
            last_message_time=now - timedelta(days=8),
            last_command_time=now - timedelta(days=8),
            last_update_time=now - timedelta(minutes=10),
            completion_time=now + timedelta(minutes=50),
        )

        async with schema.get_connection() as db:
            await Engine.settle_player(player_discord_id, village_id, db, is_ui_refresh=True)

        player = await self.fetchone(
            "SELECT status, target_id FROM players WHERE discord_id = ? AND village_id = ?",
            (player_discord_id, village_id),
        )
        self.assertEqual(player, ("missing", None))

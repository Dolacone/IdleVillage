from datetime import datetime, timedelta

from support import DatabaseTestCase
from core.engine import Engine


class PlayerStatsModuleBehaviorTests(DatabaseTestCase):
    async def test_player_stats_uses_latest_150_action_log_entries(self):
        village_id = await self.create_village()
        player_id = await self.create_player(village_id)
        now = datetime.utcnow()

        entries = []
        for index in range(151):
            end_time = now - timedelta(hours=151 - index)
            start_time = end_time - timedelta(hours=1)
            entries.append((player_id, "building", start_time.isoformat(), end_time.isoformat()))

        async with __import__("database.schema", fromlist=["schema"]).get_connection() as db:
            await db.executemany(
                """
                INSERT INTO player_actions_log (player_id, action_type, start_time, end_time)
                VALUES (?, ?, ?, ?)
                """,
                entries,
            )
            await db.commit()
            stats = await Engine.recalculate_player_stats(player_id, db)

        self.assertEqual(stats, (50, 50, 50, 200, 200))

    async def test_player_stats_cycle_window_scales_partial_cycle_entries(self):
        village_id = await self.create_village()
        player_id = await self.create_player(village_id)
        now = datetime.utcnow()

        async with __import__("database.schema", fromlist=["schema"]).get_connection() as db:
            await db.execute(
                """
                INSERT INTO player_actions_log (player_id, action_type, start_time, end_time)
                VALUES (?, ?, ?, ?)
                """,
                (
                    player_id,
                    "exploring",
                    (now - timedelta(minutes=90)).isoformat(),
                    now.isoformat(),
                ),
            )
            await db.commit()
            stats = await Engine.recalculate_player_stats(player_id, db)

        self.assertEqual(stats, (50, 51, 51, 50, 50))

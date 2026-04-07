from datetime import datetime, timedelta

from support import DatabaseTestCase
from core.engine import Engine


class PlayerStatsModuleBehaviorTests(DatabaseTestCase):
    async def test_player_stats_150h_window_recalculates_from_action_log(self):
        village_id = await self.create_village()
        player_id = await self.create_player(village_id)
        now = datetime.utcnow()

        async with __import__("database.schema", fromlist=["schema"]).get_connection() as db:
            await db.executemany(
                """
                INSERT INTO player_actions_log (player_id, action_type, start_time, end_time)
                VALUES (?, ?, ?, ?)
                """,
                [
                    (
                        player_id,
                        "idle",
                        (now - timedelta(hours=10)).isoformat(),
                        (now - timedelta(hours=8)).isoformat(),
                    ),
                    (
                        player_id,
                        "gathering_wood",
                        (now - timedelta(hours=8)).isoformat(),
                        (now - timedelta(hours=5)).isoformat(),
                    ),
                    (
                        player_id,
                        "exploring",
                        (now - timedelta(hours=5)).isoformat(),
                        (now - timedelta(hours=1)).isoformat(),
                    ),
                ],
            )
            await db.commit()
            stats = await Engine.recalculate_player_stats(player_id, db)
            async with db.execute(
                """
                SELECT strength, agility, perception, knowledge, endurance
                FROM player_stats WHERE player_id = ?
                """,
                (player_id,),
            ) as cursor:
                cached = await cursor.fetchone()

        self.assertEqual(stats, (53, 54, 56, 52, 53))
        self.assertEqual(cached, stats)

    async def test_player_stats_150h_window_trims_older_hours(self):
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
                    "building",
                    (now - timedelta(hours=170)).isoformat(),
                    (now - timedelta(hours=139)).isoformat(),
                ),
            )
            await db.commit()
            stats = await Engine.recalculate_player_stats(player_id, db)

        self.assertEqual(stats, (50, 50, 50, 60, 60))

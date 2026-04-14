import os
from datetime import datetime, timedelta

from support import DatabaseTestCase
from database import schema
from core.engine import Engine


class PlayerStatsModuleBehaviorTests(DatabaseTestCase):
    async def test_player_stats_uses_latest_150_stat_history_rows(self):
        village_id = await self.create_village()
        player_discord_id = await self.create_player(village_id)
        now = datetime.utcnow()

        entries = []
        for index in range(151):
            end_time = now - timedelta(hours=151 - index)
            entries.append((player_discord_id, village_id, 0, 0, 0, 1, 1, end_time.isoformat()))

        async with schema.get_connection() as db:
            await db.executemany(
                """
                INSERT INTO player_actions_log (
                    player_discord_id, village_id,
                    strength_delta, agility_delta, perception_delta, knowledge_delta, endurance_delta,
                    cycle_end_time
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                entries,
            )
            await db.commit()
            stats = await Engine.recalculate_player_stats(player_discord_id, village_id, db)

        self.assertEqual(stats, (50, 50, 50, 200, 200))

    async def test_player_stats_sums_delta_columns_without_time_scaling(self):
        village_id = await self.create_village()
        player_discord_id = await self.create_player(village_id)
        now = datetime.utcnow()

        async with schema.get_connection() as db:
            await db.executemany(
                """
                INSERT INTO player_actions_log (
                    player_discord_id, village_id,
                    strength_delta, agility_delta, perception_delta, knowledge_delta, endurance_delta,
                    cycle_end_time
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    (player_discord_id, village_id, 0, 1, 1, 0, 0, (now - timedelta(minutes=2)).isoformat()),
                    (player_discord_id, village_id, 0, 0, 1, 1, 0, (now - timedelta(minutes=1)).isoformat()),
                ),
            )
            await db.commit()
            stats = await Engine.recalculate_player_stats(player_discord_id, village_id, db)

        self.assertEqual(stats, (50, 51, 52, 51, 50))

    async def test_settle_player_refreshes_cached_stats_after_completed_cycle(self):
        os.environ["ACTION_CYCLE_MINUTES"] = "1"
        village_id = await self.create_village(food=1000, wood=1000, stone=1000)
        now = datetime.utcnow()
        player_discord_id = await self.create_player(
            village_id,
            status="building",
            target_id=1,
            last_update_time=now - timedelta(seconds=61),
            completion_time=now - timedelta(seconds=1),
        )

        entries = []
        for index in range(149):
            end_time = now - timedelta(minutes=151 - index)
            entries.append((player_discord_id, village_id, 0, 0, 0, 1, 1, end_time.isoformat()))

        async with schema.get_connection() as db:
            await db.executemany(
                """
                INSERT INTO player_actions_log (
                    player_discord_id, village_id,
                    strength_delta, agility_delta, perception_delta, knowledge_delta, endurance_delta,
                    cycle_end_time
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                entries,
            )
            await db.commit()

            await Engine.settle_player(player_discord_id, village_id, db)

            async with db.execute(
                """
                SELECT strength, agility, perception, knowledge, endurance
                FROM player_stats
                WHERE player_discord_id = ? AND village_id = ?
                """,
                (player_discord_id, village_id),
            ) as cursor:
                stats = await cursor.fetchone()

        self.assertEqual(stats, (50, 50, 50, 200, 200))

    async def test_init_db_migrates_legacy_action_logs_into_completed_cycle_rows(self):
        os.environ["ACTION_CYCLE_MINUTES"] = "60"
        village_id = await self.create_village()
        player_discord_id = await self.create_player(village_id)
        now = datetime.utcnow()

        async with schema.get_connection() as db:
            await db.execute("DROP INDEX IF EXISTS idx_actions_log_player")
            await db.execute("DROP TABLE player_actions_log")
            await db.execute(
                """
                CREATE TABLE player_actions_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    player_discord_id INTEGER NOT NULL,
                    village_id INTEGER NOT NULL,
                    action_type TEXT,
                    start_time TIMESTAMP,
                    end_time TIMESTAMP
                )
                """
            )
            await db.execute(
                """
                INSERT INTO player_actions_log (player_discord_id, village_id, action_type, start_time, end_time)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    player_discord_id,
                    village_id,
                    "building",
                    (now - timedelta(hours=2, minutes=30)).isoformat(),
                    now.isoformat(),
                ),
            )
            await db.commit()

        await schema.init_db()

        rows = await self.fetchall(
            """
            SELECT knowledge_delta, endurance_delta, cycle_end_time
            FROM player_actions_log
            WHERE player_discord_id = ? AND village_id = ?
            ORDER BY cycle_end_time
            """,
            (player_discord_id, village_id),
        )

        self.assertEqual(
            rows,
            [
                (1, 1, (now - timedelta(hours=1, minutes=30)).isoformat()),
                (1, 1, (now - timedelta(minutes=30)).isoformat()),
            ],
        )

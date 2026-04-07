import os
import sys
import tempfile
import types
import unittest
from datetime import datetime, timedelta


ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC_DIR = os.path.join(ROOT_DIR, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)


try:
    import disnake  # type: ignore # noqa: F401
except ImportError:
    disnake_module = types.ModuleType("disnake")
    ext_module = types.ModuleType("disnake.ext")
    tasks_module = types.ModuleType("disnake.ext.tasks")
    commands_module = types.ModuleType("disnake.ext.commands")

    def loop(*args, **kwargs):
        def decorator(func):
            return func
        return decorator

    def slash_command(*args, **kwargs):
        def decorator(func):
            return func
        return decorator

    class Cog:
        @classmethod
        def listener(cls, *args, **kwargs):
            def decorator(func):
                return func
            return decorator

    class Bot:
        latency = 0

    tasks_module.loop = loop
    commands_module.Cog = Cog
    commands_module.Bot = Bot
    commands_module.slash_command = slash_command
    ext_module.tasks = tasks_module
    ext_module.commands = commands_module
    disnake_module.ext = ext_module
    sys.modules["disnake"] = disnake_module
    sys.modules["disnake.ext"] = ext_module
    sys.modules["disnake.ext.tasks"] = tasks_module
    sys.modules["disnake.ext.commands"] = commands_module


from database import schema


class DatabaseTestCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_db_path = schema.DB_PATH
        schema.DB_PATH = os.path.join(self.temp_dir.name, "test.db")
        await schema.init_db()

    async def asyncTearDown(self):
        schema.DB_PATH = self.original_db_path
        self.temp_dir.cleanup()

    async def create_village(
        self,
        *,
        guild_id="guild-1",
        food=0,
        wood=0,
        stone=0,
        food_efficiency_xp=0,
        storage_capacity_xp=0,
        resource_yield_xp=0,
        last_tick_time=None,
    ):
        async with schema.get_connection() as db:
            await db.execute(
                """
                INSERT INTO villages (
                    guild_id, food, wood, stone,
                    food_efficiency_xp, storage_capacity_xp, resource_yield_xp, last_tick_time
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    guild_id,
                    food,
                    wood,
                    stone,
                    food_efficiency_xp,
                    storage_capacity_xp,
                    resource_yield_xp,
                    (last_tick_time or datetime.utcnow()).isoformat(),
                ),
            )
            await db.commit()
            async with db.execute("SELECT id FROM villages WHERE guild_id = ?", (guild_id,)) as cursor:
                row = await cursor.fetchone()
        return row[0]

    async def create_player(
        self,
        village_id,
        *,
        discord_id="player-1",
        status="idle",
        target_id=None,
        last_message_time=None,
        last_update_time=None,
        completion_time=None,
    ):
        if last_message_time is None:
            last_message_time = ""
        async with schema.get_connection() as db:
            await db.execute(
                """
                INSERT INTO players (
                    discord_id, village_id, last_message_time,
                    status, target_id, last_update_time, completion_time
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    discord_id,
                    village_id,
                    last_message_time.isoformat() if isinstance(last_message_time, datetime) else last_message_time,
                    status,
                    target_id,
                    (last_update_time or datetime.utcnow()).isoformat(),
                    completion_time.isoformat() if isinstance(completion_time, datetime) else completion_time,
                ),
            )
            await db.commit()
            async with db.execute(
                "SELECT id FROM players WHERE discord_id = ? AND village_id = ?",
                (discord_id, village_id),
            ) as cursor:
                row = await cursor.fetchone()
        return row[0]

    async def create_resource_node(
        self,
        village_id,
        *,
        node_type="food",
        level=1,
        quality=100,
        remaining_amount=100,
        expiry_time=None,
    ):
        async with schema.get_connection() as db:
            await db.execute(
                """
                INSERT INTO resource_nodes (
                    village_id, type, level, quality, remaining_amount, expiry_time
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    village_id,
                    node_type,
                    level,
                    quality,
                    remaining_amount,
                    (expiry_time or (datetime.utcnow() + timedelta(hours=4))).isoformat(),
                ),
            )
            await db.commit()
            async with db.execute(
                """
                SELECT id FROM resource_nodes
                WHERE village_id = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (village_id,),
            ) as cursor:
                row = await cursor.fetchone()
        return row[0]

    async def fetchone(self, query, params=()):
        async with schema.get_connection() as db:
            async with db.execute(query, params) as cursor:
                return await cursor.fetchone()

    async def fetchall(self, query, params=()):
        async with schema.get_connection() as db:
            async with db.execute(query, params) as cursor:
                return await cursor.fetchall()

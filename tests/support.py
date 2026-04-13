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
from core.engine import Engine


class DatabaseTestCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_db_path = schema.DB_PATH
        self.original_action_cycle_minutes = os.environ.get("ACTION_CYCLE_MINUTES")
        self.original_admin_ids = os.environ.get("ADMIN_IDS")
        self.next_guild_id = 100
        self.next_player_discord_id = 1000
        schema.DB_PATH = os.path.join(self.temp_dir.name, "test.db")
        Engine.bot = None
        os.environ.pop("ACTION_CYCLE_MINUTES", None)
        os.environ.pop("ADMIN_IDS", None)
        await schema.init_db()

    async def asyncTearDown(self):
        schema.DB_PATH = self.original_db_path
        if self.original_action_cycle_minutes is None:
            os.environ.pop("ACTION_CYCLE_MINUTES", None)
        else:
            os.environ["ACTION_CYCLE_MINUTES"] = self.original_action_cycle_minutes
        if self.original_admin_ids is None:
            os.environ.pop("ADMIN_IDS", None)
        else:
            os.environ["ADMIN_IDS"] = self.original_admin_ids
        Engine.bot = None
        self.temp_dir.cleanup()

    async def create_village(
        self,
        *,
        guild_id=None,
        food=1000,
        wood=1000,
        stone=1000,
        gold=0,
        food_efficiency_xp=0,
        storage_capacity_xp=0,
        resource_yield_xp=0,
        hunting_xp=0,
        last_tick_time=None,
    ):
        if guild_id is None:
            guild_id = self.next_guild_id
            self.next_guild_id += 1
        guild_id = int(guild_id)

        async with schema.get_connection() as db:
            await db.execute(
                """
                INSERT INTO villages (
                    id, last_tick_time
                )
                VALUES (?, ?)
                """,
                (
                    guild_id,
                    (last_tick_time or datetime.utcnow()).isoformat(),
                ),
            )
            await db.executemany(
                """
                INSERT INTO village_resources (village_id, resource_type, amount)
                VALUES (?, ?, ?)
                """,
                (
                    (guild_id, "food", food),
                    (guild_id, "wood", wood),
                    (guild_id, "stone", stone),
                    (guild_id, "gold", gold),
                ),
            )
            await db.executemany(
                """
                INSERT INTO buffs (village_id, buff_id, xp)
                VALUES (?, ?, ?)
                """,
                (
                    (guild_id, 1, food_efficiency_xp),
                    (guild_id, 2, storage_capacity_xp),
                    (guild_id, 3, resource_yield_xp),
                    (guild_id, 4, hunting_xp),
                ),
            )
            await db.commit()
            async with db.execute("SELECT id FROM villages WHERE id = ?", (guild_id,)) as cursor:
                row = await cursor.fetchone()
        return row[0]

    async def create_player(
        self,
        village_id,
        *,
        discord_id=None,
        status="idle",
        target_id=None,
        last_message_time=None,
        last_command_time=None,
        last_update_time=None,
        completion_time=None,
    ):
        if discord_id is None:
            discord_id = self.next_player_discord_id
            self.next_player_discord_id += 1
        discord_id = int(discord_id)

        if last_message_time is None:
            last_message_time = ""
        if last_command_time is None:
            last_command_time = ""
        async with schema.get_connection() as db:
            await db.execute(
                """
                INSERT INTO players (
                    discord_id, village_id, last_message_time, last_command_time,
                    status, target_id, last_update_time, completion_time
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    discord_id,
                    int(village_id),
                    last_message_time.isoformat() if isinstance(last_message_time, datetime) else last_message_time,
                    last_command_time.isoformat() if isinstance(last_command_time, datetime) else last_command_time,
                    status,
                    target_id,
                    (last_update_time or datetime.utcnow()).isoformat(),
                    completion_time.isoformat() if isinstance(completion_time, datetime) else completion_time,
                ),
            )
            await db.commit()
            async with db.execute(
                "SELECT discord_id FROM players WHERE discord_id = ? AND village_id = ?",
                (discord_id, int(village_id)),
            ) as cursor:
                row = await cursor.fetchone()
        return row[0]

    async def create_resource_node(
        self,
        village_id,
        *,
        node_type="food",
        quality=100,
        remaining_amount=100,
        expiry_time=None,
    ):
        async with schema.get_connection() as db:
            await db.execute(
                """
                INSERT INTO resource_nodes (
                    village_id, type, quality, remaining_amount, expiry_time
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    village_id,
                    node_type,
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

    async def create_monster(
        self,
        village_id,
        *,
        name="Monsters",
        reward_resource_type="food",
        quality=100,
        hp=1000,
        max_hp=1000,
        expires_at=None,
    ):
        del expires_at

        async with schema.get_connection() as db:
            await db.execute(
                """
                INSERT INTO monsters (
                    village_id, name, reward_resource_type, quality, hp, max_hp
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(village_id) DO UPDATE SET
                    name = excluded.name,
                    reward_resource_type = excluded.reward_resource_type,
                    quality = excluded.quality,
                    hp = excluded.hp,
                    max_hp = excluded.max_hp
                """,
                (
                    village_id,
                    name,
                    reward_resource_type,
                    quality,
                    hp,
                    max_hp,
                ),
            )
            await db.commit()
            async with db.execute(
                """
                SELECT id FROM monsters
                WHERE village_id = ?
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

    async def fetch_resources(self, village_id):
        rows = await self.fetchall(
            """
            SELECT resource_type, amount
            FROM village_resources
            WHERE village_id = ?
            ORDER BY resource_type
            """,
            (village_id,),
        )
        return {resource_type: amount for resource_type, amount in rows}

    async def fetch_buffs(self, village_id):
        rows = await self.fetchall(
            """
            SELECT buff_id, xp
            FROM buffs
            WHERE village_id = ?
            ORDER BY buff_id
            """,
            (village_id,),
        )
        return {buff_id: xp for buff_id, xp in rows}

    async def fetch_tokens(self, player_discord_id, village_id):
        rows = await self.fetchall(
            """
            SELECT token_type, amount
            FROM tokens
            WHERE player_discord_id = ?
              AND village_id = ?
            ORDER BY token_type
            """,
            (player_discord_id, village_id),
        )
        return {token_type: amount for token_type, amount in rows}

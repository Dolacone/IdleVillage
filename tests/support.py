import os
import sys
import tempfile
import types
import unittest


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


ALL_TEST_ENV = {
    "DISCORD_TOKEN": "test-token",
    "DISCORD_GUILD_ID": "111111111111111111",
    "DATABASE_PATH": "data/test.db",  # non-blank placeholder; schema tests override schema.DB_PATH directly
    "ANNOUNCEMENT_CHANNEL_ID": "222222222222222222",
    "ADMIN_IDS": "151517260622594048",
    "ACTION_CYCLE_MINUTES": "10",
    "WATCHER_HEARTBEAT_SECONDS": "60",
    "MAX_CYCLES_PER_SETTLEMENT": "100",
    "REFRESH_COOLDOWN_SECONDS": "5",
    "BASE_OUTPUT": "20",
    "FOOD_COST": "10",
    "WOOD_COST": "10",
    "KNOWLEDGE_COST": "10",
    "MATERIAL_DROP_RATE": "0.05",
    "ADMIN_RESOURCE_DELTA_SMALL": "100",
    "ADMIN_RESOURCE_DELTA_LARGE": "1000",
    "STAGE_BONUS_PER_CLEAR": "0.01",
    "GEAR_BONUS_PER_LEVEL": "0.05",
    "FACILITY_BONUS_PER_LEVEL": "0.01",
    "AP_CAP": "24",
    "AP_RECOVERY_MINUTES": "60",
    "STAGE_BASE_TARGET": "1000",
    "STAGE_TARGET_GROWTH_PER_ROUND": "0.2",
    "UPGRADE_STAGE_TARGET_MULTIPLIER": "10",
    "STAGE_OVERTIME_SECONDS": "86400",
    "STAGE_OVERTIME_PROGRESS_MULTIPLIER": "0.5",
    "BUILDING_XP_PER_LEVEL": "1000",
    "GEAR_PITY_BONUS": "0.05",
    "GEAR_MIN_SUCCESS_RATE": "0.10",
    "GEAR_RATE_LOSS_PER_LEVEL": "0.10",
}


class DatabaseTestCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self._original_db_path = schema.DB_PATH
        self._original_env = {key: os.environ.get(key) for key in ALL_TEST_ENV}

        schema.DB_PATH = os.path.join(self.temp_dir.name, "test.db")
        for key, value in ALL_TEST_ENV.items():
            os.environ[key] = value
        # DATABASE_PATH in env is not used (schema.DB_PATH takes priority), but must be non-blank.
        os.environ["DATABASE_PATH"] = schema.DB_PATH

        await schema.init_db()

    async def asyncTearDown(self):
        schema.DB_PATH = self._original_db_path
        for key, original in self._original_env.items():
            if original is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = original
        self.temp_dir.cleanup()

    async def fetchone(self, query, params=()):
        async with schema.get_connection() as db:
            async with db.execute(query, params) as cursor:
                return await cursor.fetchone()

    async def fetchall(self, query, params=()):
        async with schema.get_connection() as db:
            async with db.execute(query, params) as cursor:
                return await cursor.fetchall()

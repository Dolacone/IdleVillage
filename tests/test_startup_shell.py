import asyncio
import os
import unittest
from unittest.mock import Mock, PropertyMock, patch

from support import ALL_TEST_ENV

import main


class StartupShellBehavior(unittest.TestCase):
    def setUp(self):
        self._original_env = {key: os.environ.get(key) for key in ALL_TEST_ENV}
        for key, value in ALL_TEST_ENV.items():
            os.environ[key] = value

    def tearDown(self):
        for key, original in self._original_env.items():
            if original is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = original

    def test_main_loads_discord_extensions_before_run(self):
        loaded_extensions = []

        async def fake_init_db():
            return None

        class FakeBot:
            def load_extension(self, extension):
                loaded_extensions.append(extension)

            def run(self, token):
                self.token = token

        fake_bot = FakeBot()

        with patch.object(main, "init_db", fake_init_db), \
             patch.object(main, "IdleVillageBot", return_value=fake_bot), \
             patch.object(main.os, "makedirs"):
            main.main()

        self.assertEqual(
            loaded_extensions,
            ["cogs.general", "cogs.events", "cogs.actions"],
        )
        self.assertEqual(fake_bot.token, ALL_TEST_ENV["DISCORD_TOKEN"])

    def test_on_ready_attaches_engine_and_starts_watcher(self):
        start_watcher_loop = Mock()
        start_watcher_loop.is_running.return_value = False
        fake_engine = Mock(start_watcher_loop=start_watcher_loop)

        bot = object.__new__(main.IdleVillageBot)
        fake_user = type("User", (), {"id": 123, "__str__": lambda self: "TestBot"})()

        with patch.object(main, "Engine", fake_engine, create=True), \
             patch.object(main.IdleVillageBot, "user", new_callable=PropertyMock) as user:
            user.return_value = fake_user
            asyncio.run(bot.on_ready())

        fake_engine.set_bot.assert_called_once_with(bot)
        start_watcher_loop.start.assert_called_once_with()

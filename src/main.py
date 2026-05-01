import asyncio
import os

from dotenv import load_dotenv

load_dotenv()

import disnake
from disnake.ext import commands
from core.config import validate_env, get_discord_token, get_discord_guild_id, get_env_int
from core.engine import Engine
from database.schema import init_db


class IdleVillageBot(commands.InteractionBot):
    def __init__(self):
        intents = disnake.Intents.default()
        intents.message_content = True
        super().__init__(
            intents=intents,
            test_guilds=[int(get_discord_guild_id())],
            sync_commands_debug=True,
        )

    async def on_connect(self):
        print("Connected to Discord gateway.")

    async def on_ready(self):
        Engine.set_bot(self)
        heartbeat_secs = max(1, get_env_int("WATCHER_HEARTBEAT_SECONDS"))
        if not Engine.start_watcher_loop.is_running():
            Engine.start_watcher_loop.change_interval(seconds=heartbeat_secs)
            Engine.start_watcher_loop.start()
            print(f"Watcher loop started (interval: {heartbeat_secs}s).")

        print(f"Logged in as {self.user} (ID: {self.user.id})")
        print("------")


def main():
    if not validate_env():
        return

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        try:
            loop.run_until_complete(init_db())
            print("Database schema initialized.")
        except RuntimeError as e:
            print(f"Error: {e}")
            return

        bot = IdleVillageBot()

        os.makedirs("data", exist_ok=True)

        initial_extensions = [
            "cogs.general",
            "cogs.events",
            "cogs.actions",
        ]

        for extension in initial_extensions:
            try:
                bot.load_extension(extension)
                print(f"Loaded extension: {extension}")
            except Exception as e:
                print(f"Failed to load extension {extension}. Error: {e}")

        print("Starting Discord bot connection.")
        bot.run(get_discord_token())
    finally:
        if not loop.is_closed():
            loop.close()
        asyncio.set_event_loop(None)

if __name__ == "__main__":
    main()

import asyncio
import os

from dotenv import load_dotenv

load_dotenv()

import disnake
from disnake.ext import commands
from core.config import validate_env, get_discord_token
from database.schema import init_db


class IdleVillageBot(commands.InteractionBot):
    def __init__(self):
        intents = disnake.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)

    async def on_ready(self):
        print(f"Logged in as {self.user} (ID: {self.user.id})")
        print("------")


def main():
    if not validate_env():
        return

    try:
        asyncio.run(init_db())
        print("Database schema initialized.")
    except RuntimeError as e:
        print(f"Error: {e}")
        return

    bot = IdleVillageBot()

    os.makedirs("data", exist_ok=True)

    bot.run(get_discord_token())

if __name__ == "__main__":
    main()

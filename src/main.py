import os
import disnake
from disnake.ext import commands
from dotenv import load_dotenv
from database.schema import init_db

load_dotenv()

class IdleVillageBot(commands.InteractionBot):
    def __init__(self):
        intents = disnake.Intents.default()
        intents.message_content = True # Enable message content for tracking user activity
        super().__init__(intents=intents)

    async def on_ready(self):
        print("Initializing database schemas...")
        await init_db()

        from core.engine import Engine
        if not Engine.start_watcher_loop.is_running():
            Engine.start_watcher_loop.start()
            print("Watcher loop started.")

        print(f"Logged in as {self.user} (ID: {self.user.id})")
        print("------")

def main():
    bot = IdleVillageBot()

    # Runtime state lives outside the package tree.
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

    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("Error: DISCORD_TOKEN not found in environment variables.")
        return

    bot.run(token)

if __name__ == "__main__":
    main()

import os
import disnake
from disnake.ext import commands
from dotenv import load_dotenv
from src.database.schema import init_db

load_dotenv()

class IdleVillageBot(commands.InteractionBot):
    def __init__(self):
        intents = disnake.Intents.default()
        intents.message_content = True # Enable message content for tracking user activity
        super().__init__(intents=intents)

    async def on_ready(self):
        print("Initializing database schemas...")
        await init_db()
        print(f"Logged in as {self.user} (ID: {self.user.id})")
        print("------")

def main():
    bot = IdleVillageBot()

    # 建立目錄確保路徑存在
    os.makedirs("src/cogs", exist_ok=True)
    os.makedirs("src/database", exist_ok=True)
    os.makedirs("src/core", exist_ok=True)
    os.makedirs("data", exist_ok=True)

    # 載入 Cogs
    # 注意：這裡假設 src.cogs.general 已經存在
    initial_extensions = [
        "src.cogs.general",
        "src.cogs.events",
        "src.cogs.actions",
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
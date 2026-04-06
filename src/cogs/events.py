import disnake
from disnake.ext import commands
import datetime
from src.database.schema import get_connection

ALLOWED_OWNER_ID = 151517260622594048

class EventsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: disnake.Message):
        """Track user message activity to keep 'last_message_time' updated."""
        if message.author.bot:
            return

        async with await get_connection() as db:
            # Update last_message_time if player exists in the database
            now = datetime.datetime.now(datetime.timezone.utc).isoformat()
            await db.execute('''
                UPDATE players
                SET last_message_time = ?
                WHERE discord_id = ?
            ''', (now, str(message.author.id)))
            await db.commit()

    @disnake.slash_command(name="idlevillage-initial", description="Initialize the village for this server (Owner only)")
    async def idlevillage_initial(self, inter: disnake.ApplicationCommandInteraction):
        """Initializes the village for the guild. Restricted to specific user ID."""
        if inter.author.id != ALLOWED_OWNER_ID:
            await inter.response.send_message("You do not have permission to run this command.", ephemeral=True)
            return

        if not inter.guild:
            await inter.response.send_message("This command must be run in a server.", ephemeral=True)
            return

        guild_id_str = str(inter.guild.id)

        async with await get_connection() as db:
            # Check if village already exists
            async with db.execute('SELECT id FROM villages WHERE guild_id = ?', (guild_id_str,)) as cursor:
                existing = await cursor.fetchone()
                if existing:
                    await inter.response.send_message("Village is already initialized for this server.", ephemeral=True)
                    return

            # Insert new village
            await db.execute('''
                INSERT INTO villages (guild_id, food, wood, stone, food_efficiency_xp, storage_capacity_xp, resource_yield_xp)
                VALUES (?, 100, 0, 0, 0, 0, 0)
            ''', (guild_id_str,))
            await db.commit()

        await inter.response.send_message("Village successfully initialized for this server!")

def setup(bot: commands.Bot):
    bot.add_cog(EventsCog(bot))

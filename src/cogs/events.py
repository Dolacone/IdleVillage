import disnake
from disnake.ext import commands
import datetime
from database.schema import get_connection

class EventsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: disnake.Message):
        """Track user message activity to keep 'last_message_time' updated."""
        if message.author.bot or not message.guild:
            return

        guild_id_str = str(message.guild.id)

        async with get_connection() as db:
            # Find village first
            async with db.execute('SELECT id FROM villages WHERE guild_id = ?', (guild_id_str,)) as cursor:
                village = await cursor.fetchone()

            if village:
                village_id = village[0]
                now = datetime.datetime.now(datetime.timezone.utc).isoformat()
                await db.execute('''
                    UPDATE players
                    SET last_message_time = ?
                    WHERE discord_id = ? AND village_id = ?
                ''', (now, str(message.author.id), village_id))
                await db.commit()

def setup(bot: commands.Bot):
    bot.add_cog(EventsCog(bot))

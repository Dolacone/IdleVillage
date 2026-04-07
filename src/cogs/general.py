import disnake
from disnake.ext import commands
from database.schema import get_connection

ALLOWED_OWNER_ID = 151517260622594048

class General(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.slash_command(description="Ping the bot")
    async def ping(self, inter: disnake.ApplicationCommandInteraction):
        await inter.response.send_message(
            f"Pong! Latency: {round(self.bot.latency * 1000)}ms",
            ephemeral=True,
        )

    @commands.slash_command(name="idlevillage-initial", description="[Owner Only] Initialize a new village for this server")
    async def idlevillage_initial(self, inter: disnake.ApplicationCommandInteraction):
        if inter.author.id != ALLOWED_OWNER_ID:
            await inter.response.send_message("You do not have permission to use this command.", ephemeral=True)
            return

        if not inter.guild:
            await inter.response.send_message("This command must be run in a server.", ephemeral=True)
            return

        guild_id_str = str(inter.guild.id)

        async with get_connection() as db:
            async with db.execute('SELECT id FROM villages WHERE guild_id = ?', (guild_id_str,)) as cursor:
                village_min = await cursor.fetchone()

            if village_min:
                await inter.response.send_message("A village already exists for this server. Resetting existing villages is not allowed via this command.", ephemeral=True)
                return

            await db.execute('''
                INSERT INTO villages (guild_id, food, wood, stone, food_efficiency_xp, storage_capacity_xp, resource_yield_xp)
                VALUES (?, 100, 0, 0, 0, 0, 0)
            ''', (guild_id_str,))
            await db.commit()

        await inter.response.send_message("Village successfully initialized for this server with 100 food, 0 wood, 0 stone, and Lv 0 buildings.", ephemeral=True)


def setup(bot: commands.Bot):
    bot.add_cog(General(bot))

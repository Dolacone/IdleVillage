import disnake
from disnake.ext import commands

class General(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.slash_command(description="Ping the bot")
    async def ping(self, inter: disnake.ApplicationCommandInteraction):
        await inter.response.send_message(
            f"Pong! Latency: {round(self.bot.latency * 1000)}ms",
            ephemeral=True,
        )

def setup(bot: commands.Bot):
    bot.add_cog(General(bot))

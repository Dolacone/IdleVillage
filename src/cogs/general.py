import disnake
from disnake.ext import commands
from core.config import get_primary_admin_id, is_admin
from core.engine import Engine
from core.observability import log_event, new_request_id
from database.schema import get_connection

ALLOWED_OWNER_ID = get_primary_admin_id()

class General(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        Engine.set_bot(bot)

    @commands.slash_command(description="Ping the bot")
    async def ping(self, inter: disnake.ApplicationCommandInteraction):
        await inter.response.send_message(
            f"Pong! Latency: {round(self.bot.latency * 1000)}ms",
            ephemeral=True,
        )

    @commands.slash_command(name="idlevillage-initial", description="[Owner Only] Initialize a new village for this server")
    async def idlevillage_initial(self, inter: disnake.ApplicationCommandInteraction):
        req_id = new_request_id()
        log_event(req_id, inter.author.id, "CMD", "/idlevillage-initial")

        if not is_admin(inter.author.id):
            log_event(req_id, inter.author.id, "ERROR", "Unauthorized idlevillage-initial attempt")
            await inter.response.send_message("You do not have permission to use this command.", ephemeral=True)
            return

        if not inter.guild:
            log_event(req_id, inter.author.id, "ERROR", "idlevillage-initial used outside a guild")
            await inter.response.send_message("This command must be run in a server.", ephemeral=True)
            return

        village_id = int(inter.guild.id)

        async with get_connection() as db:
            async with db.execute('SELECT id FROM villages WHERE id = ?', (village_id,)) as cursor:
                village_min = await cursor.fetchone()

            if village_min:
                log_event(req_id, inter.author.id, "RESP", f"Village already exists for guild {village_id}")
                await inter.response.send_message("A village already exists for this server. Resetting existing villages is not allowed via this command.", ephemeral=True)
                return

            await db.execute('''
                INSERT INTO villages (id, food, wood, stone, food_efficiency_xp, storage_capacity_xp, resource_yield_xp)
                VALUES (?, 100, 0, 0, 0, 0, 0)
            ''', (village_id,))
            await db.commit()

        log_event(req_id, inter.author.id, "RESP", f"Village initialized for guild {village_id}")
        await inter.response.send_message("Village successfully initialized for this server with 100 food, 0 wood, 0 stone, and Lv 0 buildings.", ephemeral=True)

    @commands.slash_command(name="idlevillage-announcement", description="[Owner Only] Publish or refresh the public village dashboard")
    async def idlevillage_announcement(self, inter: disnake.ApplicationCommandInteraction):
        req_id = new_request_id()
        log_event(req_id, inter.author.id, "CMD", "/idlevillage-announcement")

        if not is_admin(inter.author.id):
            log_event(req_id, inter.author.id, "ERROR", "Unauthorized idlevillage-announcement attempt")
            await inter.response.send_message("You do not have permission to use this command.", ephemeral=True)
            return

        if not inter.guild or not inter.channel:
            log_event(req_id, inter.author.id, "ERROR", "idlevillage-announcement used outside a guild")
            await inter.response.send_message("This command must be run in a server channel.", ephemeral=True)
            return

        village_id = int(inter.guild.id)
        channel_id_str = str(inter.channel.id)

        async with get_connection() as db:
            async with db.execute("SELECT id FROM villages WHERE id = ?", (village_id,)) as cursor:
                village_row = await cursor.fetchone()

            if not village_row:
                log_event(req_id, inter.author.id, "ERROR", f"No village found for guild {village_id}")
                await inter.response.send_message("Village not initialized for this server. Run `/idlevillage-initial` first.", ephemeral=True)
                return

            await db.execute(
                """
                UPDATE villages
                SET announcement_channel_id = ?
                WHERE id = ?
                """,
                (channel_id_str, village_id),
            )
            await db.commit()

            message = await Engine.sync_announcement(
                village_id,
                db=db,
                bot=self.bot,
                force=True,
                req_id=req_id,
                user_id=inter.author.id,
            )

        if message is None:
            log_event(req_id, inter.author.id, "ERROR", f"Failed to publish announcement for village {village_id}")
            await inter.response.send_message("Failed to publish the village announcement. Check bot channel permissions and try again.", ephemeral=True)
            return

        log_event(req_id, inter.author.id, "RESP", f"Announcement synced to channel {channel_id_str}")
        await inter.response.send_message(
            f"Village announcement is now tracked in {inter.channel.mention}.",
            ephemeral=True,
        )


def setup(bot: commands.Bot):
    bot.add_cog(General(bot))

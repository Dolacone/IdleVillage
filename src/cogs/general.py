import disnake
from disnake.ext import commands
from core.config import get_primary_admin_id, is_admin
from core.engine import Engine
from core.observability import log_event, new_request_id
from database.schema import get_connection

ALLOWED_OWNER_ID = get_primary_admin_id()


def _normalize_admin_mode(mode: str):
    return (mode or "").strip().lower().replace("-", " ")


def _normalize_resource_type(resource_type: str):
    value = (resource_type or "").strip().lower()
    if value in ("food", "wood", "stone"):
        return value
    return None

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
                VALUES (?, 1000, 1000, 1000, 0, 0, 0)
            ''', (village_id,))
            await db.commit()

        log_event(req_id, inter.author.id, "RESP", f"Village initialized for guild {village_id}")
        await inter.response.send_message("Village successfully initialized for this server with 1,000 food, 1,000 wood, 1,000 stone, and Lv 0 buildings.", ephemeral=True)

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

    @commands.slash_command(name="idlevillage-admin", description="[Owner Only] Manage village resources and nodes")
    async def idlevillage_admin(
        self,
        inter: disnake.ApplicationCommandInteraction,
        mode: str,
        target: str,
        amount: int = None,
    ):
        req_id = new_request_id()
        log_event(req_id, inter.author.id, "CMD", f"/idlevillage-admin {mode} {target} {amount}")

        if not is_admin(inter.author.id):
            log_event(req_id, inter.author.id, "ERROR", "Unauthorized idlevillage-admin attempt")
            await inter.response.send_message("You do not have permission to use this command.", ephemeral=True)
            return

        if not inter.guild:
            log_event(req_id, inter.author.id, "ERROR", "idlevillage-admin used outside a guild")
            await inter.response.send_message("This command must be run in a server.", ephemeral=True)
            return

        village_id = int(inter.guild.id)
        normalized_mode = _normalize_admin_mode(mode)

        async with get_connection() as db:
            async with db.execute("SELECT id FROM villages WHERE id = ?", (village_id,)) as cursor:
                village_row = await cursor.fetchone()

            if not village_row:
                await inter.response.send_message("Village not initialized for this server. Run `/idlevillage-initial` first.", ephemeral=True)
                return

            if normalized_mode == "resource set":
                resource_type = _normalize_resource_type(target)
                if resource_type is None or amount is None or amount < 0:
                    await inter.response.send_message(
                        "Use `mode=resource set`, `target=food|wood|stone`, and a non-negative `amount`.",
                        ephemeral=True,
                    )
                    return

                await db.execute(
                    f"UPDATE villages SET {resource_type} = ? WHERE id = ?",
                    (amount, village_id),
                )
                await db.commit()
                log_event(req_id, inter.author.id, "RESP", f"Village {village_id} {resource_type} set to {amount}")
                await inter.response.send_message(f"Set village {resource_type} to {amount:,}.", ephemeral=True)
                return

            if normalized_mode == "node remove":
                try:
                    node_id = int(target)
                except (TypeError, ValueError):
                    await inter.response.send_message(
                        "Use `mode=node remove` and set `target` to a numeric node ID.",
                        ephemeral=True,
                    )
                    return

                async with db.execute(
                    "SELECT type FROM resource_nodes WHERE id = ? AND village_id = ?",
                    (node_id, village_id),
                ) as cursor:
                    node_row = await cursor.fetchone()

                if not node_row:
                    await inter.response.send_message(
                        f"Resource node #{node_id} was not found in this village.",
                        ephemeral=True,
                    )
                    return

                await db.execute(
                    "DELETE FROM resource_nodes WHERE id = ? AND village_id = ?",
                    (node_id, village_id),
                )
                await db.commit()
                log_event(req_id, inter.author.id, "RESP", f"Village {village_id} node {node_id} removed")
                await inter.response.send_message(
                    f"Removed {node_row[0].title()} node #{node_id}.",
                    ephemeral=True,
                )
                return

        await inter.response.send_message(
            "Supported admin modes are `resource set` and `node remove`.",
            ephemeral=True,
        )


def setup(bot: commands.Bot):
    bot.add_cog(General(bot))

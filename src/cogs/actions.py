import disnake
from disnake.ext import commands
import datetime
from src.database.schema import get_connection
from src.core.engine import Engine

class ActionDropdown(disnake.ui.Select):
    def __init__(self):
        options = [
            disnake.SelectOption(label="Gather", description="Gather resources in the wild", value="gather"),
            disnake.SelectOption(label="Build", description="Contribute to village buildings", value="build"),
            disnake.SelectOption(label="Explore", description="Search for new resource nodes", value="explore"),
            disnake.SelectOption(label="Cancel", description="Cancel current action and return to village", value="cancel")
        ]
        super().__init__(placeholder="Choose an action category...", min_values=1, max_values=1, options=options)

    async def callback(self, inter: disnake.MessageInteraction):
        # Update original message to acknowledge interaction and show next step
        action = self.values[0]
        await inter.response.edit_message(content=f"You selected: {action}. (Sub-menus coming soon!)", embed=None, view=None)


class VillageView(disnake.ui.View):
    def __init__(self):
        super().__init__(timeout=300.0) # UI expires in 5 minutes
        self.add_item(ActionDropdown())


class ActionsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @disnake.slash_command(name="idlevillage", description="Open the Idle Village interface")
    async def idlevillage(self, inter: disnake.ApplicationCommandInteraction):
        if not inter.guild:
            await inter.response.send_message("This command must be run in a server.", ephemeral=True)
            return

        guild_id_str = str(inter.guild.id)
        discord_id_str = str(inter.author.id)

        async with await get_connection() as db:
            # Fetch minimal village id first to run settlements
            async with db.execute('SELECT id FROM villages WHERE guild_id = ?', (guild_id_str,)) as cursor:
                village_min = await cursor.fetchone()

            if not village_min:
                await inter.response.send_message("Village not initialized for this server. Ask an admin to run `/idlevillage-initial`.", ephemeral=True)
                return

            village_id = village_min[0]

            # Run village hybrid decay
            await Engine.settle_village(village_id, db)

            # 2. Fetch Player (create if not exists)
            async with db.execute('SELECT id, current_weight, status FROM players WHERE discord_id = ? AND village_id = ?', (discord_id_str, village_id)) as cursor:
                player = await cursor.fetchone()

            if not player:
                # Initialize new player
                deadline = datetime.datetime.utcnow() + datetime.timedelta(hours=100)
                await db.execute('''
                    INSERT INTO players (discord_id, village_id, satiety_deadline)
                    VALUES (?, ?, ?)
                ''', (discord_id_str, village_id, deadline.isoformat()))
                await db.commit()
                # Fetch again
                async with db.execute('SELECT id, current_weight, status FROM players WHERE discord_id = ? AND village_id = ?', (discord_id_str, village_id)) as cursor:
                    player = await cursor.fetchone()

            p_id = player[0]

            # Run settlement logic to make sure states are up-to-date
            await Engine.settle_player(p_id, db)

            # Re-fetch states after settlement to prevent stale data
            async with db.execute('SELECT id, current_weight, status FROM players WHERE id = ?', (p_id,)) as cursor:
                player = await cursor.fetchone()

            p_id, p_weight, p_status = player

            async with db.execute('SELECT food, wood, stone, food_efficiency_xp, storage_capacity_xp, resource_yield_xp FROM villages WHERE id = ?', (village_id,)) as cursor:
                village_full = await cursor.fetchone()

            v_food, v_wood, v_stone, v_food_xp, v_storage_xp, v_yield_xp = village_full

            # 3. Fetch Player Stats (create if not exists)
            async with db.execute('SELECT strength, agility, perception, knowledge, endurance FROM player_stats WHERE player_id = ?', (p_id,)) as cursor:
                stats = await cursor.fetchone()

            if not stats:
                await db.execute('INSERT INTO player_stats (player_id) VALUES (?)', (p_id,))
                await db.commit()
                stats = (50, 50, 50, 50, 50)

            p_str, p_agi, p_per, p_kno, p_end = stats

            # 4. Construct Embed
            embed = disnake.Embed(title="Idle Village", color=disnake.Color.green())

            # Player Stats
            max_weight = max(100, p_str + p_end)
            embed.add_field(name="Player Status", value=f"**Status:** {p_status.title()}\n**Weight:** {p_weight}/{max_weight}\n**Stats:** STR {p_str} | AGI {p_agi} | PER {p_per} | KNO {p_kno} | END {p_end}", inline=False)

            # Village Stats
            embed.add_field(name="Village Status", value=f"**Food:** {v_food} | **Wood:** {v_wood} | **Stone:** {v_stone}\n**Buildings XP:** Food {v_food_xp} | Storage {v_storage_xp} | Yield {v_yield_xp}", inline=False)

            # Current Progress
            embed.add_field(name="Current Progress", value="Idle (Sub-menus will display progress)", inline=False)

            view = VillageView()
            await inter.response.send_message(embed=embed, view=view)


def setup(bot: commands.Bot):
    bot.add_cog(ActionsCog(bot))

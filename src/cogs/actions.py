import disnake
from disnake.ext import commands
import datetime
from database.schema import get_connection
from core.engine import Engine

class ActionSubmitButton(disnake.ui.Button):
    def __init__(self, action: str, target: str):
        super().__init__(label="Start Action", style=disnake.ButtonStyle.green)
        self.action = action
        self.target = target

    async def callback(self, inter: disnake.MessageInteraction):
        # We need to process the action
        guild_id_str = str(inter.guild.id)
        discord_id_str = str(inter.author.id)

        async with get_connection() as db:
            async with db.execute('SELECT id FROM villages WHERE guild_id = ?', (guild_id_str,)) as cursor:
                village_min = await cursor.fetchone()

            if not village_min:
                await inter.response.edit_message(content="Village not initialized.", view=None, embed=None)
                return

            village_id = village_min[0]

            async with db.execute('SELECT id, status FROM players WHERE discord_id = ? AND village_id = ?', (discord_id_str, village_id)) as cursor:
                player = await cursor.fetchone()

            if not player:
                await inter.response.edit_message(content="Player not found.", view=None, embed=None)
                return

            p_id, status = player

            # If player was doing something else, interrupt it
            if status != 'idle':
                await Engine.settle_player(p_id, db, interrupted=True)
            else:
                # Still settle idle to capture output up to this point
                await Engine.settle_player(p_id, db, interrupted=False)

            target_id = None
            if self.target and self.target.isdigit():
                target_id = int(self.target)

            # Try to start action
            success = True
            if self.action != 'idle':
                # Double-check we haven't already started it in the last few seconds to avoid race conditions/double-charging
                success = await Engine.start_action(p_id, self.action, target_id, db)

            if not success:
                # Revert to idle
                now = datetime.datetime.utcnow().isoformat()
                await db.execute("UPDATE players SET status = 'idle', target_id = NULL, last_update_time = ? WHERE id = ?", (now, p_id))
                await db.commit()
                await inter.response.edit_message(content=f"Failed to start {self.action}. Insufficient resources or invalid target. You are now idle.", view=None, embed=None)
                return
            else:
                # Need to refresh UI to reflect successful start
                await Engine.settle_player(p_id, db, interrupted=False, is_ui_refresh=True)

            # Fetch updated data
            async with db.execute('SELECT status, target_id, completion_time FROM players WHERE id = ?', (p_id,)) as cursor:
                player = await cursor.fetchone()

            p_status, p_target, p_comp_str = player

            async with db.execute('SELECT food, wood, stone, food_efficiency_xp, storage_capacity_xp, resource_yield_xp FROM villages WHERE id = ?', (village_id,)) as cursor:
                village_full = await cursor.fetchone()

            v_food, v_wood, v_stone, v_food_xp, v_storage_xp, v_yield_xp = village_full

            # 3. Fetch Player Stats
            async with db.execute('SELECT strength, agility, perception, knowledge, endurance FROM player_stats WHERE player_id = ?', (p_id,)) as cursor:
                stats = await cursor.fetchone()
            p_str, p_agi, p_per, p_kno, p_end = stats if stats else (50, 50, 50, 50, 50)

            # 4. Construct Embed
            embed = disnake.Embed(title="Idle Village", color=disnake.Color.green())

            # Player Stats
            embed.add_field(name="Player Status", value=f"**Status:** {p_status.title()}\n**Stats:** STR {p_str} | AGI {p_agi} | PER {p_per} | KNO {p_kno} | END {p_end}", inline=False)

            # Village Stats
            embed.add_field(name="Village Status", value=f"**Food:** {v_food} | **Wood:** {v_wood} | **Stone:** {v_stone}\n**Buildings XP:** Food {v_food_xp} | Storage {v_storage_xp} | Yield {v_yield_xp}", inline=False)

            comp_text = "Idle (Gathering food in village)"
            if p_comp_str:
                comp_dt = Engine._parse_timestamp(p_comp_str)
                if comp_dt:
                    comp_text = f"Expected completion: <t:{int(comp_dt.timestamp())}:R>"

            embed.add_field(name="Current Progress", value=comp_text, inline=False)

            await inter.response.edit_message(content="Action started!", embed=embed, view=None)

class SubMenuDropdown(disnake.ui.Select):
    def __init__(self, action: str, options: list):
        self.action = action
        super().__init__(placeholder=f"Select target for {action}...", min_values=1, max_values=1, options=options)

    async def callback(self, inter: disnake.MessageInteraction):
        target = self.values[0]
        # Keep original dropdowns, and add or update the submit button
        view = self.view
        view.clear_items()
        view.add_item(ActionDropdown(default_value=self.action))
        view.add_item(SubMenuDropdown(action=self.action, options=self.options)) # Add self back
        view.add_item(ActionSubmitButton(action=self.action, target=target))
        await inter.response.edit_message(view=view)

class ActionDropdown(disnake.ui.Select):
    def __init__(self, default_value: str = None):
        options = [
            disnake.SelectOption(label="Gather", description="Gather resources from a node", value="gathering", default=(default_value=="gathering")),
            disnake.SelectOption(label="Build", description="Contribute to village buildings", value="building", default=(default_value=="building")),
            disnake.SelectOption(label="Explore", description="Search for new resource nodes", value="exploring", default=(default_value=="exploring")),
            disnake.SelectOption(label="Idle", description="Return to village and assist", value="idle", default=(default_value=="idle"))
        ]
        super().__init__(placeholder="Choose an action category...", min_values=1, max_values=1, options=options)

    async def callback(self, inter: disnake.MessageInteraction):
        action = self.values[0]
        view = self.view
        view.clear_items()
        view.add_item(ActionDropdown(default_value=action))

        # Determine submenu options dynamically
        guild_id_str = str(inter.guild.id)

        if action == 'idle' or action == 'exploring':
            view.add_item(ActionSubmitButton(action=action, target="none"))
            await inter.response.edit_message(view=view)
            return

        options = []
        async with get_connection() as db:
            async with db.execute('SELECT id FROM villages WHERE guild_id = ?', (guild_id_str,)) as cursor:
                village_min = await cursor.fetchone()

            if village_min:
                village_id = village_min[0]
                if action == 'gathering':
                    async with db.execute('SELECT id, type, level, remaining_amount, quality FROM resource_nodes WHERE village_id = ? AND remaining_amount > 0 AND expiry_time > ?', (village_id, datetime.datetime.utcnow().isoformat())) as cursor:
                        nodes = await cursor.fetchall()
                    for n in nodes:
                        n_id, n_type, n_lvl, n_rem, n_qual = n
                        options.append(disnake.SelectOption(label=f"Lv{n_lvl} {n_type.title()} Node", description=f"Stock: {n_rem} | Qual: {n_qual}", value=str(n_id)))
                    if not options:
                        options.append(disnake.SelectOption(label="No nodes available", value="none"))

                elif action == 'building':
                    options = [
                        disnake.SelectOption(label="Food Efficiency", description="Cost: 10 Wood, 5 Stone", value="1"),
                        disnake.SelectOption(label="Storage Capacity", description="Cost: 10 Wood, 5 Stone", value="2"),
                        disnake.SelectOption(label="Resource Yield", description="Cost: 10 Wood, 5 Stone", value="3"),
                    ]

        if options:
            if len(options) == 1 and options[0].value == "none":
                view.add_item(SubMenuDropdown(action=action, options=options))
            else:
                view.add_item(SubMenuDropdown(action=action, options=options))

        await inter.response.edit_message(view=view)


class VillageView(disnake.ui.View):
    def __init__(self):
        super().__init__(timeout=300.0) # UI expires in 5 minutes
        self.add_item(ActionDropdown())


class ActionsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.slash_command(name="idlevillage", description="Open the Idle Village interface")
    async def idlevillage(self, inter: disnake.ApplicationCommandInteraction):
        if not inter.guild:
            await inter.response.send_message("This command must be run in a server.", ephemeral=True)
            return

        guild_id_str = str(inter.guild.id)
        discord_id_str = str(inter.author.id)

        async with get_connection() as db:
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
            now = datetime.datetime.utcnow().isoformat()
            async with db.execute('SELECT id, status FROM players WHERE discord_id = ? AND village_id = ?', (discord_id_str, village_id)) as cursor:
                player = await cursor.fetchone()

            if not player:
                # Initialize new player
                await db.execute('''
                    INSERT INTO players (discord_id, village_id, last_message_time)
                    VALUES (?, ?, ?)
                ''', (discord_id_str, village_id, now))
                await db.commit()

                async with db.execute('SELECT id, status FROM players WHERE discord_id = ? AND village_id = ?', (discord_id_str, village_id)) as cursor:
                    player = await cursor.fetchone()

            p_id = player[0]

            # Update last_message_time
            await db.execute("UPDATE players SET last_message_time = ? WHERE id = ?", (now, p_id))
            await db.commit()

            # Run settlement logic to make sure states are up-to-date, but without restarting or interrupting, just capturing current progress
            await Engine.settle_player(p_id, db, interrupted=False, is_ui_refresh=True)

            # Re-fetch states after settlement
            async with db.execute('SELECT status, completion_time FROM players WHERE id = ?', (p_id,)) as cursor:
                player = await cursor.fetchone()

            p_status, p_comp_str = player

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
            embed.add_field(name="Player Status", value=f"**Status:** {p_status.title()}\n**Stats:** STR {p_str} | AGI {p_agi} | PER {p_per} | KNO {p_kno} | END {p_end}", inline=False)

            # Village Stats
            embed.add_field(name="Village Status", value=f"**Food:** {v_food} | **Wood:** {v_wood} | **Stone:** {v_stone}\n**Buildings XP:** Food {v_food_xp} | Storage {v_storage_xp} | Yield {v_yield_xp}", inline=False)

            # Current Progress
            comp_text = "Idle (Gathering food in village)"
            if p_comp_str:
                comp_dt = Engine._parse_timestamp(p_comp_str)
                if comp_dt:
                    comp_text = f"Expected completion: <t:{int(comp_dt.timestamp())}:R>"

            embed.add_field(name="Current Progress", value=comp_text, inline=False)

            view = VillageView()
            await inter.response.send_message(embed=embed, view=view, ephemeral=True)


def setup(bot: commands.Bot):
    bot.add_cog(ActionsCog(bot))

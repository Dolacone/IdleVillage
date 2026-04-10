from datetime import datetime, timezone

import disnake
from disnake.ext import commands

from core.config import is_admin
from core.engine import Engine
from core.observability import log_event, new_request_id
from database.schema import get_connection

RESOURCE_EMOJIS = {
    "food": "🍎",
    "wood": "🪵",
    "stone": "🪨",
}

RESOURCE_LABELS = {
    "food": "Food",
    "wood": "Wood",
    "stone": "Stone",
}

MANAGE_MODE_LABELS = {
    "resources": "Manage Resources",
    "nodes": "Manage Nodes",
}


async def _fetch_village_row(village_id: int):
    async with get_connection() as db:
        async with db.execute("SELECT id FROM villages WHERE id = ?", (village_id,)) as cursor:
            village = await cursor.fetchone()
        if not village:
            return None
        resources = await Engine._fetch_village_resources(db, village_id)
        return (village[0], resources["food"], resources["wood"], resources["stone"])


async def _fetch_active_nodes(village_id: int):
    async with get_connection() as db:
        async with db.execute(
            """
            SELECT id, type, remaining_amount, quality
            FROM resource_nodes
            WHERE village_id = ?
              AND remaining_amount > 0
            ORDER BY type, quality DESC, id DESC
            """,
            (village_id,),
        ) as cursor:
            return await cursor.fetchall()


async def _set_village_resource(village_id: int, resource_type: str, amount: int):
    normalized_amount = max(0, int(amount))
    async with get_connection() as db:
        resources = await Engine._fetch_village_resources(db, village_id)
        resources[resource_type] = normalized_amount
        await Engine._write_village_resources(db, village_id, resources)
        await db.commit()
    return normalized_amount


async def _adjust_village_resource(village_id: int, resource_type: str, delta: int):
    async with get_connection() as db:
        resources = await Engine._fetch_village_resources(db, village_id)
        new_amount = max(0, resources[resource_type] + delta)
        resources[resource_type] = new_amount
        await Engine._write_village_resources(db, village_id, resources)
        await db.commit()
    return new_amount


async def _remove_village_node(village_id: int, node_id: int):
    async with get_connection() as db:
        async with db.execute(
            """
            SELECT type
            FROM resource_nodes
            WHERE id = ?
              AND village_id = ?
            """,
            (node_id, village_id),
        ) as cursor:
            node_row = await cursor.fetchone()

        if not node_row:
            return None

        await db.execute(
            """
            DELETE FROM resource_nodes
            WHERE id = ?
              AND village_id = ?
            """,
            (node_id, village_id),
        )
        await db.commit()
        return node_row[0]


class ManageModeSelect(disnake.ui.StringSelect):
    def __init__(self, mode: str):
        options = [
            disnake.SelectOption(
                label="Manage Resources",
                description="Adjust village food, wood, and stone totals",
                value="resources",
                default=(mode == "resources"),
            ),
            disnake.SelectOption(
                label="Manage Nodes",
                description="Remove active resource nodes from the village",
                value="nodes",
                default=(mode == "nodes"),
            ),
        ]
        super().__init__(placeholder="Choose admin mode...", options=options, min_values=1, max_values=1, row=0)

    async def callback(self, inter: disnake.MessageInteraction):
        self.view.mode = self.values[0]
        await self.view.refresh_state()
        await self.view.render(inter, content=f"{MANAGE_MODE_LABELS[self.view.mode]} loaded.")


class ResourceTypeSelect(disnake.ui.StringSelect):
    def __init__(self, selected_resource: str):
        options = [
            disnake.SelectOption(
                label=RESOURCE_LABELS[resource_type],
                description=f"Adjust village {resource_type}",
                value=resource_type,
                default=(selected_resource == resource_type),
            )
            for resource_type in ("food", "wood", "stone")
        ]
        super().__init__(placeholder="Choose a resource...", options=options, min_values=1, max_values=1, row=1)

    async def callback(self, inter: disnake.MessageInteraction):
        self.view.selected_resource = self.values[0]
        await self.view.refresh_state()
        await self.view.render(inter, content=f"{RESOURCE_LABELS[self.view.selected_resource]} selected.")


class NodeSelect(disnake.ui.StringSelect):
    def __init__(self, nodes, selected_node_id: int = None):
        if nodes:
            options = [
                disnake.SelectOption(
                    label=f"#{node_id} {node_type.title()}",
                    description=f"Stock {remaining_amount} | Quality {quality}%",
                    value=str(node_id),
                    default=(selected_node_id == node_id),
                )
                for node_id, node_type, remaining_amount, quality in nodes
            ]
            disabled = False
            placeholder = "Choose a node to remove..."
        else:
            options = [
                disnake.SelectOption(
                    label="No active nodes",
                    description="There are no active nodes to manage",
                    value="none",
                    default=True,
                )
            ]
            disabled = True
            placeholder = "No active nodes available"

        super().__init__(
            placeholder=placeholder,
            options=options,
            min_values=1,
            max_values=1,
            disabled=disabled,
            row=1,
        )

    async def callback(self, inter: disnake.MessageInteraction):
        value = self.values[0]
        self.view.selected_node_id = None if value == "none" else int(value)
        await self.view.refresh_state()
        await self.view.render(inter, content="Node selection updated.")


class ResourceDeltaButton(disnake.ui.Button):
    def __init__(self, delta: int):
        label = f"{delta:+,}"
        style = disnake.ButtonStyle.green if delta > 0 else disnake.ButtonStyle.red
        super().__init__(label=label, style=style, row=2)
        self.delta = delta

    async def callback(self, inter: disnake.MessageInteraction):
        new_amount = await _adjust_village_resource(self.view.village_id, self.view.selected_resource, self.delta)
        await Engine.sync_announcement(self.view.village_id, bot=self.view.bot, force=True, req_id=self.view.req_id, user_id=inter.author.id)
        await self.view.refresh_state()
        await self.view.render(
            inter,
            content=f"{RESOURCE_LABELS[self.view.selected_resource]} updated to {new_amount:,}.",
        )


class SetCustomButton(disnake.ui.Button):
    def __init__(self):
        super().__init__(label="Set Custom", style=disnake.ButtonStyle.blurple, row=2)

    async def callback(self, inter: disnake.MessageInteraction):
        await inter.response.send_modal(ResourceAmountModal(self.view))


class RemoveNodeButton(disnake.ui.Button):
    def __init__(self, disabled: bool):
        super().__init__(label="Remove Node", style=disnake.ButtonStyle.red, disabled=disabled, row=2)

    async def callback(self, inter: disnake.MessageInteraction):
        if self.view.selected_node_id is None:
            await self.view.render(inter, content="Choose a node before removing it.")
            return

        removed_type = await _remove_village_node(self.view.village_id, self.view.selected_node_id)
        if removed_type is None:
            await self.view.refresh_state()
            await self.view.render(inter, content="That node is no longer available.")
            return

        removed_node_id = self.view.selected_node_id
        await Engine.sync_announcement(self.view.village_id, bot=self.view.bot, force=True, req_id=self.view.req_id, user_id=inter.author.id)
        await self.view.refresh_state()
        await self.view.render(inter, content=f"Removed {removed_type.title()} node #{removed_node_id}.")


class ResourceAmountModal(disnake.ui.Modal):
    def __init__(self, manage_view):
        self.manage_view = manage_view
        current_amount = manage_view.resource_amounts.get(manage_view.selected_resource, 0)
        super().__init__(
            title=f"Set {RESOURCE_LABELS[manage_view.selected_resource]} Amount",
            custom_id=f"idlevillage-manage:{manage_view.village_id}:{manage_view.selected_resource}",
            components=[
                disnake.ui.TextInput(
                    label="Absolute Amount",
                    custom_id="amount",
                    placeholder="Enter a non-negative integer",
                    value=str(current_amount),
                    style=disnake.TextInputStyle.short,
                    max_length=12,
                )
            ],
        )

    async def callback(self, inter: disnake.ModalInteraction):
        raw_amount = inter.text_values.get("amount", "").strip()
        if not raw_amount.isdigit():
            await inter.response.send_message("Enter a non-negative integer amount.", ephemeral=True)
            return

        amount = await _set_village_resource(self.manage_view.village_id, self.manage_view.selected_resource, int(raw_amount))
        await Engine.sync_announcement(
            self.manage_view.village_id,
            bot=self.manage_view.bot,
            force=True,
            req_id=self.manage_view.req_id,
            user_id=inter.author.id,
        )
        await self.manage_view.refresh_state()
        await self.manage_view.render(
            inter,
            content=f"{RESOURCE_LABELS[self.manage_view.selected_resource]} set to {amount:,}.",
        )


class ManageView(disnake.ui.View):
    def __init__(self, village_id: int, bot, req_id: str):
        super().__init__(timeout=300.0)
        self.village_id = village_id
        self.bot = bot
        self.req_id = req_id
        self.mode = "resources"
        self.selected_resource = "food"
        self.selected_node_id = None
        self.resource_amounts = {"food": 0, "wood": 0, "stone": 0}
        self.nodes = []

    async def refresh_state(self):
        village = await _fetch_village_row(self.village_id)
        if village:
            _, food, wood, stone = village
            self.resource_amounts = {
                "food": food,
                "wood": wood,
                "stone": stone,
            }

        self.nodes = await _fetch_active_nodes(self.village_id)
        valid_node_ids = {node_id for node_id, *_ in self.nodes}
        if self.selected_node_id not in valid_node_ids:
            self.selected_node_id = self.nodes[0][0] if self.nodes else None
        self._rebuild_items()
        return self

    def _rebuild_items(self):
        self.clear_items()
        self.add_item(ManageModeSelect(self.mode))

        if self.mode == "resources":
            self.add_item(ResourceTypeSelect(self.selected_resource))
            self.add_item(ResourceDeltaButton(100))
            self.add_item(ResourceDeltaButton(1000))
            self.add_item(ResourceDeltaButton(-100))
            self.add_item(ResourceDeltaButton(-1000))
            self.add_item(SetCustomButton())
            return

        self.add_item(NodeSelect(self.nodes, self.selected_node_id))
        self.add_item(RemoveNodeButton(disabled=(self.selected_node_id is None)))

    async def build_embed(self):
        village_name = await Engine._resolve_village_name(self.bot, self.village_id)
        embed = disnake.Embed(title=f"Idle Village Admin - {village_name}", color=disnake.Color.orange())

        if self.mode == "resources":
            amount = self.resource_amounts[self.selected_resource]
            emoji = RESOURCE_EMOJIS[self.selected_resource]
            embed.description = "Adjust village stockpiles with quick buttons or set an exact amount."
            embed.add_field(
                name=f"{RESOURCE_LABELS[self.selected_resource]}",
                value=f"{emoji} Current amount: {amount:,}",
                inline=False,
            )
            embed.add_field(
                name="Available Resources",
                value=(
                    f"🍎 Food: {self.resource_amounts['food']:,}\n"
                    f"🪵 Wood: {self.resource_amounts['wood']:,}\n"
                    f"🪨 Stone: {self.resource_amounts['stone']:,}"
                ),
                inline=False,
            )
            return embed

        embed.description = "Select a node and remove it from the village board."
        if self.selected_node_id is None:
            embed.add_field(name="Selected Node", value="No active nodes are available.", inline=False)
            return embed

        selected_node = next((node for node in self.nodes if node[0] == self.selected_node_id), None)
        if not selected_node:
            embed.add_field(name="Selected Node", value="No active nodes are available.", inline=False)
            return embed

        node_id, node_type, remaining_amount, quality = selected_node
        embed.add_field(
            name=f"Node #{node_id}",
            value=(
                f"Type: {node_type.title()}\n"
                f"Stock: {remaining_amount:,}\n"
                f"Quality: {quality}%"
            ),
            inline=False,
        )
        embed.add_field(name="Active Node Count", value=str(len(self.nodes)), inline=False)
        return embed

    async def render(self, inter, *, content: str):
        embed = await self.build_embed()
        if hasattr(inter.response, "edit_message"):
            await inter.response.edit_message(content=content, embed=embed, view=self)
            return
        await inter.response.send_message(content=content, embed=embed, view=self, ephemeral=True)


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
            async with db.execute("SELECT id FROM villages WHERE id = ?", (village_id,)) as cursor:
                village_min = await cursor.fetchone()

            if village_min:
                log_event(req_id, inter.author.id, "RESP", f"Village already exists for guild {village_id}")
                await inter.response.send_message(
                    "A village already exists for this server. Resetting existing villages is not allowed via this command.",
                    ephemeral=True,
                )
                return

            await db.execute(
                """
                INSERT INTO villages (id)
                VALUES (?)
                """,
                (village_id,),
            )
            await Engine._write_village_resources(
                db,
                village_id,
                {"food": 1000, "wood": 1000, "stone": 1000},
            )
            await Engine._write_village_buffs(db, village_id, {1: 0, 2: 0, 3: 0})
            await db.commit()

        log_event(req_id, inter.author.id, "RESP", f"Village initialized for guild {village_id}")
        await inter.response.send_message(
            "Village successfully initialized for this server with 1,000 food, 1,000 wood, 1,000 stone, and Lv 0 buildings.",
            ephemeral=True,
        )

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
            await inter.response.send_message(
                "Failed to publish the village announcement. Check bot channel permissions and try again.",
                ephemeral=True,
            )
            return

        log_event(req_id, inter.author.id, "RESP", f"Announcement synced to channel {channel_id_str}")
        await inter.response.send_message(
            f"Village announcement is now tracked in {inter.channel.mention}.",
            ephemeral=True,
        )

    @commands.slash_command(name="idlevillage-manage", description="[Owner Only] Open the interactive village admin panel")
    async def idlevillage_manage(self, inter: disnake.ApplicationCommandInteraction):
        req_id = new_request_id()
        log_event(req_id, inter.author.id, "CMD", "/idlevillage-manage")

        if not is_admin(inter.author.id):
            log_event(req_id, inter.author.id, "ERROR", "Unauthorized idlevillage-manage attempt")
            await inter.response.send_message("You do not have permission to use this command.", ephemeral=True)
            return

        if not inter.guild:
            log_event(req_id, inter.author.id, "ERROR", "idlevillage-manage used outside a guild")
            await inter.response.send_message("This command must be run in a server.", ephemeral=True)
            return

        village_id = int(inter.guild.id)
        village = await _fetch_village_row(village_id)
        if not village:
            await inter.response.send_message("Village not initialized for this server. Run `/idlevillage-initial` first.", ephemeral=True)
            return

        view = await ManageView(village_id, self.bot, req_id).refresh_state()
        embed = await view.build_embed()
        await inter.response.send_message(
            "Manage village resources and nodes.",
            embed=embed,
            view=view,
            ephemeral=True,
        )


def setup(bot: commands.Bot):
    bot.add_cog(General(bot))

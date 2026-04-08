import datetime
import time

import disnake
from disnake.ext import commands

from core.engine import Engine
from core.observability import log_event, new_request_id
from database.schema import get_connection


async def _get_village_id(db, guild_id: str):
    async with db.execute("SELECT id FROM villages WHERE guild_id = ?", (guild_id,)) as cursor:
        village_row = await cursor.fetchone()
    return village_row[0] if village_row else None


async def _get_or_create_player(db, village_id: int, discord_id: str):
    async with db.execute(
        "SELECT id FROM players WHERE discord_id = ? AND village_id = ?",
        (discord_id, village_id),
    ) as cursor:
        player_row = await cursor.fetchone()

    if player_row:
        return player_row[0]

    now = datetime.datetime.utcnow().isoformat()
    await db.execute(
        """
        INSERT INTO players (discord_id, village_id, last_message_time)
        VALUES (?, ?, ?)
        """,
        (discord_id, village_id, now),
    )
    await db.commit()

    async with db.execute(
        "SELECT id FROM players WHERE discord_id = ? AND village_id = ?",
        (discord_id, village_id),
    ) as cursor:
        player_row = await cursor.fetchone()
    return player_row[0]


async def _update_player_activity(db, player_id: int):
    now = datetime.datetime.utcnow().isoformat()
    await db.execute("UPDATE players SET last_message_time = ? WHERE id = ?", (now, player_id))
    await db.commit()


async def _load_submenu_options(db, village_id: int, action: str):
    if action == "gathering":
        async with db.execute(
            """
            SELECT id, type, remaining_amount, quality
            FROM resource_nodes
            WHERE village_id = ?
              AND remaining_amount > 0
              AND expiry_time > ?
            ORDER BY type, quality DESC, id DESC
            """,
            (village_id, datetime.datetime.utcnow().isoformat()),
        ) as cursor:
            nodes = await cursor.fetchall()

        options = []
        for node_id, node_type, remaining_amount, quality in nodes:
            options.append(
                disnake.SelectOption(
                    label=f"{node_type.title()} Node",
                    description=f"Stock {remaining_amount} | Quality {quality}%",
                    value=str(node_id),
                )
            )
        return options

    if action == "building":
        return [
            disnake.SelectOption(label="廚房", description="Food cost reduction", value="1"),
            disnake.SelectOption(label="倉庫", description="Storage capacity", value="2"),
            disnake.SelectOption(label="加工", description="Resource yield", value="3"),
        ]

    return []


async def _build_embed(inter, db, village_id: int, player_id: int):
    async with db.execute(
        """
        SELECT food, wood, stone, food_efficiency_xp, storage_capacity_xp, resource_yield_xp
        FROM villages
        WHERE id = ?
        """,
        (village_id,),
    ) as cursor:
        village = await cursor.fetchone()

    async with db.execute(
        """
        SELECT status, target_id, last_update_time, completion_time
        FROM players
        WHERE id = ?
        """,
        (player_id,),
    ) as cursor:
        player = await cursor.fetchone()

    async with db.execute(
        """
        SELECT strength, agility, perception, knowledge, endurance
        FROM player_stats
        WHERE player_id = ?
        """,
        (player_id,),
    ) as cursor:
        stats = await cursor.fetchone()

    if not village or not player:
        return None

    food, wood, stone, food_xp, storage_xp, yield_xp = village
    status, target_id, last_update_str, completion_time_str = player
    p_str, p_agi, p_per, p_kno, p_end = stats if stats else (50, 50, 50, 50, 50)

    storage_capacity = Engine._storage_capacity(storage_xp)
    building_rows = []
    for building_id, xp in ((1, food_xp), (2, storage_xp), (3, yield_xp)):
        level = Engine._building_level_from_xp(xp)
        next_threshold = Engine._next_building_threshold(level)
        building_rows.append(f"{Engine.BUILDING_NAMES[building_id]} Lv.{level} [XP: {xp:,} / {next_threshold:,}]")

    last_update = Engine._parse_timestamp(last_update_str)
    completion_time = Engine._parse_timestamp(completion_time_str)
    status_text = await Engine._get_target_description(db, status, target_id)
    if last_update:
        last_activity_text = f"<t:{Engine._to_discord_unix(last_update)}:t>"
    else:
        last_activity_text = "Unknown"

    if completion_time:
        next_check_text = f"<t:{Engine._to_discord_unix(completion_time)}:R>"
    else:
        next_check_text = "Manual refresh"

    guild_name = inter.guild.name if inter.guild else f"Village {village_id}"
    embed = disnake.Embed(title=f"Idle Village - {guild_name}", color=disnake.Color.green())
    embed.add_field(
        name="Village Resources",
        value=f"🍎 {food:,} | 🪵 {wood:,} | 🪨 {stone:,} (Cap: {storage_capacity:,})",
        inline=False,
    )
    embed.add_field(
        name="Village Buildings",
        value="```text\n" + "\n".join(building_rows) + "\n```",
        inline=False,
    )
    embed.add_field(
        name="Player Status",
        value=(
            f"Stats: 💪 STR {p_str} | 🏃 AGI {p_agi} | 👁️ PER {p_per} | 🧠 KNO {p_kno} | 🔋 END {p_end}\n"
            f"Status: {status_text} (Last activity: {last_activity_text}, Next check: {next_check_text})"
        ),
        inline=False,
    )
    return embed


async def _render_interface(
    inter,
    *,
    content: str = None,
    create_response: bool = False,
    view=None,
    req_id: str = None,
    user_id=None,
):
    if not inter.guild:
        if create_response:
            await inter.response.send_message("This command must be run in a server.", ephemeral=True)
        else:
            await inter.response.edit_message(content="This command must be run in a server.", embed=None, view=None)
        return

    guild_id_str = str(inter.guild.id)
    discord_id_str = str(inter.author.id)

    async with get_connection() as db:
        village_id = await _get_village_id(db, guild_id_str)
        if village_id is None:
            message = "Village not initialized for this server. Ask an admin to run `/idlevillage-initial`."
            if create_response:
                await inter.response.send_message(message, ephemeral=True)
            else:
                await inter.response.edit_message(content=message, embed=None, view=None)
            return

        await Engine.settle_village(village_id, db, req_id=req_id, user_id=user_id)
        player_id = await _get_or_create_player(db, village_id, discord_id_str)
        await _update_player_activity(db, player_id)
        await Engine.settle_player(player_id, db, is_ui_refresh=True, req_id=req_id, user_id=user_id)
        embed = await _build_embed(inter, db, village_id, player_id)
        await Engine.sync_announcement(village_id, db=db, bot=getattr(inter, "bot", None), req_id=req_id, user_id=user_id)

    active_view = view or VillageView()
    if create_response:
        await inter.response.send_message(content=content, embed=embed, view=active_view, ephemeral=True)
    else:
        await inter.response.edit_message(content=content, embed=embed, view=active_view)


class RefreshButton(disnake.ui.Button):
    def __init__(self):
        super().__init__(label="Refresh Status", style=disnake.ButtonStyle.gray)

    async def callback(self, inter: disnake.MessageInteraction):
        now_monotonic = time.monotonic()
        if now_monotonic < self.view.refresh_available_at:
            remaining_seconds = max(1, int(self.view.refresh_available_at - now_monotonic))
            await inter.response.edit_message(content=f"Refresh available in {remaining_seconds}s.", view=self.view)
            return

        self.view.refresh_available_at = now_monotonic + 5
        await _render_interface(
            inter,
            content="Status refreshed.",
            view=VillageView(refresh_available_at=self.view.refresh_available_at),
            req_id=new_request_id(),
            user_id=inter.author.id,
        )


class ActionSubmitButton(disnake.ui.Button):
    def __init__(self, action: str, target: str = None):
        super().__init__(label="Start Action", style=disnake.ButtonStyle.green)
        self.action = action
        self.target = target

    async def callback(self, inter: disnake.MessageInteraction):
        req_id = new_request_id()
        log_event(req_id, inter.author.id, "CMD", f"action-submit:{self.action}")

        guild_id_str = str(inter.guild.id)
        discord_id_str = str(inter.author.id)

        async with get_connection() as db:
            village_id = await _get_village_id(db, guild_id_str)
            if village_id is None:
                await inter.response.edit_message(content="Village not initialized.", embed=None, view=None)
                return

            player_id = await _get_or_create_player(db, village_id, discord_id_str)
            await _update_player_activity(db, player_id)
            await Engine.settle_village(village_id, db, req_id=req_id, user_id=inter.author.id)

            async with db.execute("SELECT status FROM players WHERE id = ?", (player_id,)) as cursor:
                player_row = await cursor.fetchone()

            current_status = player_row[0] if player_row else "idle"
            if current_status != "idle":
                await Engine.settle_player(player_id, db, interrupted=True, req_id=req_id, user_id=inter.author.id)
            else:
                await Engine.settle_player(player_id, db, req_id=req_id, user_id=inter.author.id)

            target_id = int(self.target) if self.target and self.target.isdigit() else None
            success = True
            if self.action != "idle":
                success = await Engine.start_action(
                    player_id,
                    self.action,
                    target_id,
                    db,
                    req_id=req_id,
                    user_id=inter.author.id,
                )

            if not success:
                log_event(req_id, inter.author.id, "RESP", f"Failed to start {self.action}")
                await _render_interface(
                    inter,
                    content=f"Failed to start {self.action}. Check resources or target availability.",
                    view=VillageView(refresh_available_at=self.view.refresh_available_at),
                    req_id=req_id,
                    user_id=inter.author.id,
                )
                return

            await Engine.sync_announcement(village_id, db=db, bot=inter.bot, req_id=req_id, user_id=inter.author.id)

        log_event(req_id, inter.author.id, "RESP", f"Started action {self.action}")
        await _render_interface(
            inter,
            content="Action updated.",
            view=VillageView(refresh_available_at=self.view.refresh_available_at),
            req_id=req_id,
            user_id=inter.author.id,
        )


class SubMenuDropdown(disnake.ui.Select):
    def __init__(self, action: str, options: list, selected_value: str = None):
        self.action = action
        cloned_options = []
        for option in options:
            cloned_options.append(
                disnake.SelectOption(
                    label=option.label,
                    description=option.description,
                    value=option.value,
                    default=(option.value == selected_value),
                )
            )
        super().__init__(
            placeholder=f"Select target for {action}...",
            min_values=1,
            max_values=1,
            options=cloned_options,
        )

    async def callback(self, inter: disnake.MessageInteraction):
        target = self.values[0]
        self.view.reset(action=self.action, options=self.options, target=target, selected_value=target)
        await inter.response.edit_message(view=self.view)


class ActionDropdown(disnake.ui.Select):
    def __init__(self, default_value: str = None):
        options = [
            disnake.SelectOption(label="Gather", description="Collect from a discovered node", value="gathering", default=(default_value == "gathering")),
            disnake.SelectOption(label="Build", description="Work on a village structure", value="building", default=(default_value == "building")),
            disnake.SelectOption(label="Explore", description="Search for fresh resource nodes", value="exploring", default=(default_value == "exploring")),
            disnake.SelectOption(label="Return", description="Return to idle village support", value="idle", default=(default_value == "idle")),
        ]
        super().__init__(placeholder="Choose an action...", min_values=1, max_values=1, options=options)

    async def callback(self, inter: disnake.MessageInteraction):
        action = self.values[0]
        if action in ("idle", "exploring"):
            self.view.reset(action=action, options=None, target="none")
            await inter.response.edit_message(view=self.view)
            return

        async with get_connection() as db:
            village_id = await _get_village_id(db, str(inter.guild.id))
            options = await _load_submenu_options(db, village_id, action) if village_id else []

        self.view.reset(action=action, options=options, target=None)
        await inter.response.edit_message(view=self.view)


class VillageView(disnake.ui.View):
    def __init__(self, refresh_available_at: float = 0.0):
        super().__init__(timeout=300.0)
        self.refresh_available_at = refresh_available_at
        self.reset()

    def reset(self, action: str = None, options=None, target: str = None, selected_value: str = None):
        self.clear_items()
        self.add_item(ActionDropdown(default_value=action))

        if options:
            self.add_item(SubMenuDropdown(action=action, options=options, selected_value=selected_value))

        if action in ("idle", "exploring"):
            self.add_item(ActionSubmitButton(action=action, target=target))
        elif target and target != "none":
            self.add_item(ActionSubmitButton(action=action, target=target))

        self.add_item(RefreshButton())


class ActionsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        Engine.set_bot(bot)

    @commands.slash_command(name="idlevillage", description="Open the Idle Village interface")
    async def idlevillage(self, inter: disnake.ApplicationCommandInteraction):
        req_id = new_request_id()
        log_event(req_id, inter.author.id, "CMD", "/idlevillage")
        await _render_interface(
            inter,
            content="Village status loaded.",
            create_response=True,
            view=VillageView(),
            req_id=req_id,
            user_id=inter.author.id,
        )
        log_event(req_id, inter.author.id, "RESP", "/idlevillage rendered")


def setup(bot: commands.Bot):
    bot.add_cog(ActionsCog(bot))

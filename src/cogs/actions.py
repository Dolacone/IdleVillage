import time
from datetime import datetime, timezone

import disnake
from disnake.ext import commands

from core.engine import Engine
from core.observability import log_event, new_request_id
from database.schema import get_connection


async def _village_exists(db, village_id: int):
    async with db.execute(
        "SELECT 1 FROM villages WHERE id = ?",
        (village_id,),
    ) as cursor:
        return await cursor.fetchone() is not None


async def _get_or_create_player(db, village_id: int, discord_id: int):
    async with db.execute(
        "SELECT discord_id FROM players WHERE discord_id = ? AND village_id = ?",
        (discord_id, village_id),
    ) as cursor:
        player_row = await cursor.fetchone()

    if player_row:
        return discord_id

    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    await db.execute(
        """
        INSERT INTO players (discord_id, village_id, last_message_time, last_command_time)
        VALUES (?, ?, ?, ?)
        """,
        (discord_id, village_id, "", now),
    )
    await db.commit()
    return discord_id


async def _update_player_command_time(db, player_discord_id: int, village_id: int):
    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    await db.execute(
        """
        UPDATE players
        SET last_command_time = ?
        WHERE discord_id = ?
          AND village_id = ?
        """,
        (now, player_discord_id, village_id),
    )
    await db.commit()


async def _load_submenu_options(db, village_id: int, action: str):
    if action == "interact":
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
            nodes = await cursor.fetchall()

        options = []
        for node_id, node_type, remaining_amount, quality in nodes:
            options.append(
                disnake.SelectOption(
                    label=f"{node_type.title()} Node",
                    description=f"Stock {remaining_amount} | Quality {quality}%",
                    value=f"node:{node_id}",
                )
            )

        async with db.execute(
            """
            SELECT id, name, hp, max_hp, quality
            FROM monsters
            WHERE village_id = ?
            """,
            (village_id,),
        ) as cursor:
            monster = await cursor.fetchone()
        if monster:
            monster_id, name, hp, max_hp, quality = monster
            options.append(
                disnake.SelectOption(
                    label=name,
                    description=f"HP {hp}/{max_hp} | Quality {quality}%",
                    value=f"monster:{monster_id}",
                )
            )
        return options

    if action == "building":
        return [
            disnake.SelectOption(label="廚房", description="Food cost reduction (materials: food & wood)", value="1"),
            disnake.SelectOption(label="倉庫", description="Storage capacity (materials: wood & stone)", value="2"),
            disnake.SelectOption(label="加工", description="Resource yield (materials: wood & stone)", value="3"),
            disnake.SelectOption(label="狩獵", description="Attack damage bonus (materials: stone & gold)", value="4"),
        ]

    return []


async def _build_embed(inter, db, village_id: int, player_discord_id: int):
    async with db.execute(
        """
        SELECT 1
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
        WHERE discord_id = ?
          AND village_id = ?
        """,
        (player_discord_id, village_id),
    ) as cursor:
        player = await cursor.fetchone()

    async with db.execute(
        """
        SELECT strength, agility, perception, knowledge, endurance
        FROM player_stats
        WHERE player_discord_id = ?
          AND village_id = ?
        """,
        (player_discord_id, village_id),
    ) as cursor:
        stats = await cursor.fetchone()

    if not village or not player:
        return None

    status, target_id, last_update_str, completion_time_str = player
    p_str, p_agi, p_per, p_kno, p_end = stats if stats else (50, 50, 50, 50, 50)

    last_update = Engine._parse_timestamp(last_update_str)
    completion_time = Engine._parse_timestamp(completion_time_str)
    status_text = await Engine._get_target_description(db, status, target_id)
    if last_update:
        last_activity_text = f"<t:{Engine._to_discord_unix(last_update)}:t>"
    else:
        last_activity_text = "Unknown"

    next_check_time = completion_time
    if status == "idle":
        next_check_time = Engine._next_idle_completion(last_update)

    if next_check_time:
        next_check_text = f"<t:{Engine._to_discord_unix(next_check_time)}:R>"
    else:
        next_check_text = "Manual refresh"

    guild_name = inter.guild.name if inter.guild else f"Village {village_id}"
    embed = disnake.Embed(title=f"Idle Village - {guild_name}", color=disnake.Color.green())
    
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    unified_description = await Engine.render_announcement(
        village_id, 
        db=db, 
        bot=getattr(inter, "bot", None), 
        rendered_at=now
    )
    if unified_description:
        embed.description = unified_description

    embed.add_field(
        name="Player Status",
        value=(
            f"Stats: 💪 STR {p_str} | 🏃 AGI {p_agi} | 👁️ PER {p_per} | 🧠 KNO {p_kno} | 🔋 END {p_end}\n"
            f"Status: {status_text} (Last activity: {last_activity_text}, Next check: {next_check_text})"
        ),
        inline=False,
    )
    return embed


async def _ensure_player_ready(db, village_id: int, player_discord_id: int):
    if not await _village_exists(db, village_id):
        return False, "Village not initialized for this server. Ask an admin to run `/idlevillage-initial`."
    await Engine.settle_village(village_id, db)
    player_discord_id = await _get_or_create_player(db, village_id, player_discord_id)
    await _update_player_command_time(db, player_discord_id, village_id)
    await Engine.settle_player(player_discord_id, village_id, db, is_ui_refresh=True)
    return True, player_discord_id


def _format_token_status(tokens: dict):
    return (
        f"Gathering: {tokens['gathering']}\n"
        f"Exploring: {tokens['exploring']}\n"
        f"Building: {tokens['building']}\n"
        f"Attacking: {tokens['attacking']}"
    )


async def _render_interface(
    inter,
    *,
    content: str = None,
    create_response: bool = False,
    view=None,
    req_id: str = None,
    user_id=None,
    update_command_activity: bool = False,
):
    if not inter.guild:
        if create_response:
            await inter.response.send_message("This command must be run in a server.", ephemeral=True)
        else:
            await inter.response.edit_message(content="This command must be run in a server.", embed=None, view=None)
        return

    village_id = int(inter.guild.id)
    player_discord_id = int(inter.author.id)

    async with get_connection() as db:
        if not await _village_exists(db, village_id):
            message = "Village not initialized for this server. Ask an admin to run `/idlevillage-initial`."
            if create_response:
                await inter.response.send_message(message, ephemeral=True)
            else:
                await inter.response.edit_message(content=message, embed=None, view=None)
            return

        await Engine.settle_village(village_id, db, req_id=req_id, user_id=user_id)
        player_discord_id = await _get_or_create_player(db, village_id, player_discord_id)
        if update_command_activity:
            await _update_player_command_time(db, player_discord_id, village_id)
        await Engine.settle_player(player_discord_id, village_id, db, is_ui_refresh=True, req_id=req_id, user_id=user_id)
        embed = await _build_embed(inter, db, village_id, player_discord_id)
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

        village_id = int(inter.guild.id)
        player_discord_id = int(inter.author.id)

        async with get_connection() as db:
            if not await _village_exists(db, village_id):
                await inter.response.edit_message(content="Village not initialized.", embed=None, view=None)
                return

            player_discord_id = await _get_or_create_player(db, village_id, player_discord_id)
            await Engine.settle_village(village_id, db, req_id=req_id, user_id=inter.author.id)

            async with db.execute(
                """
                SELECT status
                FROM players
                WHERE discord_id = ?
                  AND village_id = ?
                """,
                (player_discord_id, village_id),
            ) as cursor:
                player_row = await cursor.fetchone()

            current_status = player_row[0] if player_row else "idle"
            if current_status != "idle":
                await Engine.settle_player(
                    player_discord_id,
                    village_id,
                    db,
                    interrupted=True,
                    req_id=req_id,
                    user_id=inter.author.id,
                )
            else:
                await Engine.settle_player(
                    player_discord_id,
                    village_id,
                    db,
                    req_id=req_id,
                    user_id=inter.author.id,
                )

            action_to_start = self.action
            target_id = int(self.target) if self.target and self.target.isdigit() else None
            if self.action == "interact":
                if not self.target:
                    await _render_interface(
                        inter,
                        content="Choose an interaction target first.",
                        view=VillageView(refresh_available_at=self.view.refresh_available_at),
                        req_id=req_id,
                        user_id=inter.author.id,
                    )
                    return
                if self.target.startswith("node:"):
                    action_to_start = "gathering"
                    target_id = int(self.target.split(":", 1)[1])
                elif self.target.startswith("monster:"):
                    action_to_start = "attack"
                    target_id = int(self.target.split(":", 1)[1])
                else:
                    await _render_interface(
                        inter,
                        content="Invalid interaction target.",
                        view=VillageView(refresh_available_at=self.view.refresh_available_at),
                        req_id=req_id,
                        user_id=inter.author.id,
                    )
                    return

            success = True
            if action_to_start != "idle":
                success = await Engine.start_action(
                    player_discord_id,
                    village_id,
                    action_to_start,
                    target_id,
                    db,
                    req_id=req_id,
                    user_id=inter.author.id,
                )

            if not success:
                log_event(req_id, inter.author.id, "RESP", f"Failed to start {action_to_start}")
                await _render_interface(
                    inter,
                    content=f"Failed to start {action_to_start}. Check resources or target availability.",
                    view=VillageView(refresh_available_at=self.view.refresh_available_at),
                    req_id=req_id,
                    user_id=inter.author.id,
                )
                return

            await Engine.sync_announcement(village_id, db=db, bot=inter.bot, req_id=req_id, user_id=inter.author.id)

        log_event(req_id, inter.author.id, "RESP", f"Started action {action_to_start}")
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
            disnake.SelectOption(label="Interact", description="Gather nodes or attack monsters", value="interact", default=(default_value == "interact")),
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
            village_id = int(inter.guild.id)
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
            update_command_activity=True,
        )
        log_event(req_id, inter.author.id, "RESP", "/idlevillage rendered")

    @commands.slash_command(name="idlevillage-tokens", description="Check and spend personal village tokens")
    async def idlevillage_tokens(
        self,
        inter: disnake.ApplicationCommandInteraction,
        action: str = "status",
        token_type: str = None,
    ):
        req_id = new_request_id()
        log_event(req_id, inter.author.id, "CMD", f"/idlevillage-tokens action={action}")

        if not inter.guild:
            await inter.response.send_message("This command must be run in a server.", ephemeral=True)
            return

        village_id = int(inter.guild.id)
        player_discord_id = int(inter.author.id)
        action = str(action or "status").lower()
        token_type = str(token_type).lower() if token_type else None

        async with get_connection() as db:
            ready, result = await _ensure_player_ready(db, village_id, player_discord_id)
            if not ready:
                await inter.response.send_message(result, ephemeral=True)
                return

            player_discord_id = result
            response_lines = []
            if action == "buff":
                if not token_type:
                    await inter.response.send_message(
                        "Choose a token type for buff use: gathering, exploring, building, or attacking.",
                        ephemeral=True,
                    )
                    return
                success, buff_result = await Engine.use_player_buff_token(db, player_discord_id, village_id, token_type)
                if not success:
                    await inter.response.send_message(str(buff_result), ephemeral=True)
                    return
                response_lines.append(
                    f"Used 1 {token_type} token. Matching actions now gain +100 total stats until <t:{Engine._to_discord_unix(buff_result)}:R>."
                )
            elif action == "protect":
                success, protect_result = await Engine.use_village_protection_token(db, player_discord_id, village_id)
                if not success:
                    await inter.response.send_message(str(protect_result), ephemeral=True)
                    return
                response_lines.append(
                    f"Village protection extended until <t:{Engine._to_discord_unix(protect_result)}:R>. Future decay is reduced by 50% while active."
                )

            tokens = await Engine._fetch_player_tokens(db, player_discord_id, village_id)
            active_buff = await Engine._fetch_player_buff(db, player_discord_id, village_id)
            protection_expires_at = await Engine._fetch_protection_expires_at(db, village_id)
            await db.commit()

        response_lines.append("Current tokens:")
        response_lines.append(_format_token_status(tokens))
        if active_buff:
            response_lines.append(
                f"Active buff: {active_buff['buff_type']} until <t:{Engine._to_discord_unix(active_buff['expires_at'])}:R>"
            )
        if protection_expires_at:
            response_lines.append(
                f"Village protection: <t:{Engine._to_discord_unix(protection_expires_at)}:R>"
            )

        await inter.response.send_message("\n".join(response_lines), ephemeral=True)

    @commands.slash_command(name="idlevillage-village-command", description="View or set the village command")
    async def idlevillage_village_command(
        self,
        inter: disnake.ApplicationCommandInteraction,
        command: str = None,
    ):
        req_id = new_request_id()
        log_event(req_id, inter.author.id, "CMD", f"/idlevillage-village-command command={command}")

        if not inter.guild:
            await inter.response.send_message("This command must be run in a server.", ephemeral=True)
            return

        village_id = int(inter.guild.id)
        player_discord_id = int(inter.author.id)
        normalized_command = str(command).lower() if command else None

        async with get_connection() as db:
            ready, result = await _ensure_player_ready(db, village_id, player_discord_id)
            if not ready:
                await inter.response.send_message(result, ephemeral=True)
                return

            player_discord_id = result
            tokens = await Engine._fetch_player_tokens(db, player_discord_id, village_id)
            total_tokens = sum(tokens.values())
            current_command = await Engine._fetch_village_command(db, village_id)

            if normalized_command:
                success, command_result = await Engine.set_village_command_with_tokens(
                    db,
                    player_discord_id,
                    village_id,
                    normalized_command,
                )
                if not success:
                    await inter.response.send_message(str(command_result), ephemeral=True)
                    return
                current_command = command_result
                tokens = await Engine._fetch_player_tokens(db, player_discord_id, village_id)
                total_tokens = sum(tokens.values())
                await db.commit()
                await inter.response.send_message(
                    (
                        f"Village command set to `{current_command}`. "
                        "This setting consumed 10 tokens.\n"
                        f"Remaining total tokens: {total_tokens}"
                    ),
                    ephemeral=True,
                )
                return

        valid_commands = ", ".join(Engine.VILLAGE_COMMANDS)
        await inter.response.send_message(
            (
                f"Current village command: `{current_command or 'none'}`\n"
                f"Your total tokens: {total_tokens}\n"
                "Setting a village command will consume 10 tokens.\n"
                f"Available commands: {valid_commands}"
            ),
            ephemeral=True,
        )


def setup(bot: commands.Bot):
    bot.add_cog(ActionsCog(bot))

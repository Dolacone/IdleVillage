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
        next_check_text = _format_discord_relative_time(next_check_time)
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


def _token_type_label(token_type: str) -> str:
    return {
        "gathering": "Gathering",
        "exploring": "Exploring",
        "building": "Building",
        "attacking": "Attacking",
    }.get(str(token_type or ""), str(token_type or "Unknown").replace("_", " ").title())


def _village_command_label(command: str | None) -> str:
    return {
        "gathering_food": "Gather Food",
        "gathering_wood": "Gather Wood",
        "gathering_stone": "Gather Stone",
        "exploring": "Explore",
        "attack": "Attack Monsters",
    }.get(str(command or ""), "None")


def _format_discord_relative_time(dt: datetime) -> str:
    """Format datetime as Discord relative timestamp."""
    return f"<t:{Engine._to_discord_unix(dt)}:R>"


async def _build_token_embed(inter, db, village_id: int, player_discord_id: int):
    tokens = await Engine._fetch_player_tokens(db, player_discord_id, village_id)
    active_buff = await Engine._fetch_player_buff(db, player_discord_id, village_id)
    protection_expires_at = await Engine._fetch_protection_expires_at(db, village_id)
    active_command = await Engine._fetch_village_command(db, village_id)
    guild_name = inter.guild.name if inter.guild else f"Village {village_id}"
    total_tokens = sum(tokens.values())

    embed = disnake.Embed(title=f"Idle Village Tokens - {guild_name}", color=disnake.Color.blurple())
    embed.description = (
        "Use the menus below to spend tokens on a personal buff, village protection, "
        "or the village command. Village command changes consume 10 tokens from the selected token type."
    )
    embed.add_field(
        name="Token Inventory",
        value=f"Total: {total_tokens}\n{_format_token_status(tokens)}",
        inline=False,
    )

    buff_line = "Inactive"
    if active_buff:
        buff_line = f"{_token_type_label(active_buff['buff_type'])} until {_format_discord_relative_time(active_buff['expires_at'])}"

    protection_line = "Inactive"
    if protection_expires_at:
        protection_line = _format_discord_relative_time(protection_expires_at)

    embed.add_field(
        name="Active Effects",
        value=(
            f"Personal Buff: {buff_line}\n"
            f"Village Protection: {protection_line}\n"
            f"Village Command: {_village_command_label(active_command)}"
        ),
        inline=False,
    )
    embed.add_field(
        name="Costs",
        value=(
            "Personal Buff: 1 matching token\n"
            "Village Protection: 1 selected token\n"
            f"Village Command: {Engine.VILLAGE_COMMAND_TOKEN_COST} tokens from the selected token type"
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


async def _render_token_interface(
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

    village_id = int(inter.guild.id)
    player_discord_id = int(inter.author.id)

    async with get_connection() as db:
        ready, result = await _ensure_player_ready(db, village_id, player_discord_id)
        if not ready:
            if create_response:
                await inter.response.send_message(str(result), ephemeral=True)
            else:
                await inter.response.edit_message(content=str(result), embed=None, view=None)
            return
        player_discord_id = result
        embed = await _build_token_embed(inter, db, village_id, player_discord_id)

    active_view = view or TokenView()
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


class TokenRefreshButton(disnake.ui.Button):
    def __init__(self):
        super().__init__(label="Refresh Tokens", style=disnake.ButtonStyle.gray)

    async def callback(self, inter: disnake.MessageInteraction):
        now_monotonic = time.monotonic()
        if now_monotonic < self.view.refresh_available_at:
            remaining_seconds = max(1, int(self.view.refresh_available_at - now_monotonic))
            await inter.response.edit_message(content=f"Refresh available in {remaining_seconds}s.", view=self.view)
            return

        self.view.refresh_available_at = now_monotonic + 5
        await _render_token_interface(
            inter,
            content="Token status refreshed.",
            view=TokenView(
                mode=self.view.mode,
                token_type=self.view.token_type,
                command=self.view.command,
                refresh_available_at=self.view.refresh_available_at,
            ),
            req_id=new_request_id(),
            user_id=inter.author.id,
        )


class TokenModeDropdown(disnake.ui.Select):
    def __init__(self, default_value: str | None = None):
        options = [
            disnake.SelectOption(
                label="Personal Buff",
                description="Spend 1 token for a 3-cycle self-buff.",
                value="buff",
                default=(default_value == "buff"),
            ),
            disnake.SelectOption(
                label="Village Protection",
                description="Spend 1 selected token to reduce decay by 50% for 1 cycle.",
                value="protect",
                default=(default_value == "protect"),
            ),
            disnake.SelectOption(
                label="Village Command",
                description="Spend 10 tokens from the selected type to guide idle villagers.",
                value="command",
                default=(default_value == "command"),
            ),
        ]
        super().__init__(placeholder="Choose a token action...", min_values=1, max_values=1, options=options)

    async def callback(self, inter: disnake.MessageInteraction):
        self.view.reset(mode=self.values[0])
        await inter.response.edit_message(view=self.view)


class TokenTypeDropdown(disnake.ui.Select):
    def __init__(self, mode: str, selected_value: str | None = None):
        descriptions = {
            "buff": "Use 1 token to boost matching actions.",
            "protect": "Use 1 token to extend village protection.",
            "command": f"Spend {Engine.VILLAGE_COMMAND_TOKEN_COST} of this type for the village command.",
        }
        options = [
            disnake.SelectOption(label="Gathering", description=descriptions[mode], value="gathering", default=(selected_value == "gathering")),
            disnake.SelectOption(label="Exploring", description=descriptions[mode], value="exploring", default=(selected_value == "exploring")),
            disnake.SelectOption(label="Building", description=descriptions[mode], value="building", default=(selected_value == "building")),
            disnake.SelectOption(label="Attacking", description=descriptions[mode], value="attacking", default=(selected_value == "attacking")),
        ]
        placeholder = "Choose which token type to spend..."
        super().__init__(placeholder=placeholder, min_values=1, max_values=1, options=options)
        self.mode = mode

    async def callback(self, inter: disnake.MessageInteraction):
        self.view.reset(mode=self.view.mode, token_type=self.values[0], command=self.view.command)
        await inter.response.edit_message(view=self.view)


class VillageCommandDropdown(disnake.ui.Select):
    def __init__(self, selected_value: str | None = None):
        options = [
            disnake.SelectOption(label="Gather Food", description="Idle villagers gather food when possible.", value="gathering_food", default=(selected_value == "gathering_food")),
            disnake.SelectOption(label="Gather Wood", description="Idle villagers gather wood when possible.", value="gathering_wood", default=(selected_value == "gathering_wood")),
            disnake.SelectOption(label="Gather Stone", description="Idle villagers gather stone when possible.", value="gathering_stone", default=(selected_value == "gathering_stone")),
            disnake.SelectOption(label="Explore", description="Idle villagers explore when resources allow.", value="exploring", default=(selected_value == "exploring")),
            disnake.SelectOption(label="Attack Monsters", description="Idle villagers attack the current monster when one exists.", value="attack", default=(selected_value == "attack")),
        ]
        super().__init__(placeholder="Choose the village command...", min_values=1, max_values=1, options=options)

    async def callback(self, inter: disnake.MessageInteraction):
        self.view.reset(mode=self.view.mode, token_type=self.view.token_type, command=self.values[0])
        await inter.response.edit_message(view=self.view)


class TokenApplyButton(disnake.ui.Button):
    def __init__(self, mode: str, disabled: bool = False):
        labels = {
            "buff": "Use Personal Buff",
            "protect": "Apply Village Protection",
            "command": "Set Village Command",
        }
        super().__init__(label=labels.get(mode, "Apply"), style=disnake.ButtonStyle.green, disabled=disabled)

    async def callback(self, inter: disnake.MessageInteraction):
        req_id = new_request_id()
        log_event(req_id, inter.author.id, "CMD", f"token-apply:{self.view.mode}")

        if not self.view.mode:
            await _render_token_interface(inter, content="Choose a token action first.", view=self.view, req_id=req_id, user_id=inter.author.id)
            return

        if not self.view.token_type:
            await _render_token_interface(inter, content="Choose which token type to spend first.", view=self.view, req_id=req_id, user_id=inter.author.id)
            return

        if self.view.mode == "command" and not self.view.command:
            await _render_token_interface(inter, content="Choose a village command first.", view=self.view, req_id=req_id, user_id=inter.author.id)
            return

        village_id = int(inter.guild.id)
        player_discord_id = int(inter.author.id)

        async with get_connection() as db:
            ready, result = await _ensure_player_ready(db, village_id, player_discord_id)
            if not ready:
                await inter.response.edit_message(content=str(result), embed=None, view=None)
                return

            player_discord_id = result
            if self.view.mode == "buff":
                success, action_result = await Engine.use_player_buff_token(
                    db,
                    player_discord_id,
                    village_id,
                    self.view.token_type,
                )
                if success:
                    message = (
                        f"Used 1 {_token_type_label(self.view.token_type)} token. "
                        f"Matching actions now gain +100 total stats until {_format_discord_relative_time(action_result)}."
                    )
            elif self.view.mode == "protect":
                success, action_result = await Engine.use_village_protection_token(
                    db,
                    player_discord_id,
                    village_id,
                    self.view.token_type,
                )
                if success:
                    message = (
                        f"Used 1 {_token_type_label(self.view.token_type)} token. "
                        f"Village protection is active until {_format_discord_relative_time(action_result)}."
                    )
            else:
                success, action_result = await Engine.set_village_command_with_tokens(
                    db,
                    player_discord_id,
                    village_id,
                    self.view.command,
                    token_type=self.view.token_type,
                )
                if success:
                    message = (
                        f"Village command set to `{action_result}`. "
                        f"This consumed {Engine.VILLAGE_COMMAND_TOKEN_COST} {_token_type_label(self.view.token_type).lower()} tokens."
                    )

            if not success:
                await _render_token_interface(inter, content=str(action_result), view=self.view, req_id=req_id, user_id=inter.author.id)
                return

            await db.commit()

        await _render_token_interface(
            inter,
            content=message,
            view=TokenView(
                mode=self.view.mode,
                token_type=self.view.token_type,
                command=self.view.command,
                refresh_available_at=self.view.refresh_available_at,
            ),
            req_id=req_id,
            user_id=inter.author.id,
        )


class TokenView(disnake.ui.View):
    def __init__(
        self,
        mode: str | None = None,
        token_type: str | None = None,
        command: str | None = None,
        refresh_available_at: float = 0.0,
    ):
        super().__init__(timeout=300.0)
        self.refresh_available_at = refresh_available_at
        self.mode = mode
        self.token_type = token_type
        self.command = command
        self.reset(mode=mode, token_type=token_type, command=command)

    def reset(self, mode: str | None = None, token_type: str | None = None, command: str | None = None):
        self.mode = mode
        self.token_type = token_type
        self.command = command if mode == "command" else None

        self.clear_items()
        self.add_item(TokenModeDropdown(default_value=self.mode))

        if self.mode in ("buff", "protect", "command"):
            self.add_item(TokenTypeDropdown(self.mode, selected_value=self.token_type))

        if self.mode == "command":
            self.add_item(VillageCommandDropdown(selected_value=self.command))

        is_ready = bool(self.mode and self.token_type and (self.mode != "command" or self.command))
        if self.mode:
            self.add_item(TokenApplyButton(self.mode, disabled=not is_ready))

        self.add_item(TokenRefreshButton())


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

    @commands.slash_command(name="idlevillage-tokens", description="Open the token and village command interface")
    async def idlevillage_tokens(self, inter: disnake.ApplicationCommandInteraction):
        req_id = new_request_id()
        log_event(req_id, inter.author.id, "CMD", "/idlevillage-tokens")
        await _render_token_interface(
            inter,
            content="Token interface loaded.",
            create_response=True,
            view=TokenView(),
            req_id=req_id,
            user_id=inter.author.id,
        )
        log_event(req_id, inter.author.id, "RESP", "/idlevillage-tokens rendered")


def setup(bot: commands.Bot):
    bot.add_cog(ActionsCog(bot))

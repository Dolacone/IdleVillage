import secrets
from datetime import datetime, timedelta, timezone

import disnake
from disnake.ext import commands

from cogs.ui_renderer import (
    ACTION_EMOJIS,
    ACTION_LABELS,
    UI_BUILDING_TARGETS,
    build_affix_components,
    build_affix_embed,
    build_auto_affix_components,
    build_auto_affix_embed,
    build_auto_tool_components,
    build_auto_tool_embed,
    build_gear_components,
    build_gear_embed,
    build_main_components,
    build_main_embed,
    build_ranking_text,
    build_trial_target_components,
    build_trial_target_embed,
)
from core import notification
from core.config import get_discord_guild_id, get_env_int
from core.formula import ACTION_MATERIAL_COL
from core.settlement import change_action, settle_auto_tool_cycles, settle_burst, settle_complete_cycles
from core.utils import dt_str
from database.schema import get_connection
from managers import affix_manager, auto_tool_manager, building_manager, gear_manager, player_manager, trial_manager

_OWN_BUTTONS = frozenset({"burst_execute", "open_gear_upgrade", "open_trial_start", "open_auto_tool", "back_to_main"})
_OWN_BUTTON_PREFIXES = ("confirm_action:", "attempt_upgrade:", "clear_affix:", "sacrifice_material:", "open_affix_mgmt:", "affix_extract:", "affix_clear:", "back_to_gear:", "auto_tool_confirm:", "trial_target_page:", "open_auto_affix:", "back_to_affix:", "auto_affix_run:")
_OWN_DROPDOWNS = frozenset({"action_select", "building_target_select", "gear_type_select", "affix_gear_select", "auto_tool_type_select", "trial_target_select"})
_OWN_DROPDOWN_PREFIXES = ("upgrade_mode_select:", "upgrade_count_select:", "affix_slot_select:", "auto_tool_target_select:", "auto_tool_add_select:", "auto_tool_sub_select:", "auto_affix_target:", "auto_affix_value:", "auto_affix_material:", "auto_affix_scope:")
_OWN_MODAL_PREFIXES = ("modal_sacrifice:",)
_VALID_GEAR_TYPES = frozenset({"gathering", "building", "combat", "research"})
_VALID_ACTIONS = frozenset({"gathering", "building", "combat", "research"})
_VALID_UPGRADE_MODES = frozenset(gear_manager.UPGRADE_MODES)
_VALID_UPGRADE_COUNTS = frozenset({"1", "5", "10", "20", "inf"})
_VALID_AFFIX_TYPES = frozenset(affix_manager.AFFIX_TYPES)
_VALID_AUTO_AFFIX_VALUES = frozenset({"1", "2", "3", "4", "5"})
_VALID_AUTO_AFFIX_SOURCES = frozenset({"none", "tool", "universal"})
_VALID_AUTO_AFFIX_SCOPES = frozenset({"none", "one", "all"})


def _parse_auto_affix_state(parts: list[str]) -> tuple[str, str, str, str, str] | None:
    if len(parts) != 6:
        return None
    gear, target, value, source, scope = parts[1:]
    if gear not in (*_VALID_GEAR_TYPES, "none") or scope not in _VALID_AUTO_AFFIX_SCOPES:
        return None
    if target not in ("none", "any") and target not in _VALID_AFFIX_TYPES:
        return None
    if value != "none" and value not in _VALID_AUTO_AFFIX_VALUES:
        return None
    if source not in _VALID_AUTO_AFFIX_SOURCES:
        return None
    return gear, target, value, source, scope


def _is_own_button(cid: str) -> bool:
    return cid in _OWN_BUTTONS or any(cid.startswith(p) for p in _OWN_BUTTON_PREFIXES)


def _is_own_dropdown(cid: str) -> bool:
    return cid in _OWN_DROPDOWNS or any(cid.startswith(p) for p in _OWN_DROPDOWN_PREFIXES)


def _is_own_modal(cid: str) -> bool:
    return any(cid.startswith(p) for p in _OWN_MODAL_PREFIXES)

def _make_player_gear(row):
    if row:
        return {"gathering": row[0], "building": row[1], "combat": row[2], "research": row[3]}
    return {"gathering": 0, "building": 0, "combat": 0, "research": 0}


class ActionsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._auto_affix_confirmations: dict[str, str] = {}

    def _check_guild(self, inter) -> bool:
        return str(inter.guild_id) == get_discord_guild_id()

    async def _get_or_create_player(self, db, user_id: str, now: datetime) -> None:
        ap_cap = get_env_int("AP_CAP")
        recovery_mins = get_env_int("AP_RECOVERY_MINUTES")
        ap_full_time = now + timedelta(minutes=ap_cap * recovery_mins)
        now_str = dt_str(now)
        ap_full_time_str = dt_str(ap_full_time)
        await db.execute(
            """INSERT OR IGNORE INTO players
               (user_id, created_at, updated_at, ap_full_time)
               VALUES (?, ?, ?, ?)""",
            (user_id, now_str, now_str, ap_full_time_str),
        )
        await db.commit()

    async def _fetch_all_data(
        self, db, user_id: str
    ) -> tuple[dict, dict, dict, list, dict, dict, int]:
        async with db.execute("SELECT * FROM stage_state WHERE id=1") as cur:
            row = await cur.fetchone()
            cols = [d[0] for d in cur.description]
            stage_data = dict(zip(cols, row)) if row else {}

        resources: dict = {}
        async with db.execute(
            "SELECT resource_type, amount FROM village_resources"
        ) as cur:
            async for r in cur:
                resources[r[0]] = r[1]

        buildings: dict = {}
        async with db.execute(
            "SELECT building_type, level, xp_progress FROM buildings"
        ) as cur:
            async for r in cur:
                buildings[r[0]] = {"level": r[1], "xp_progress": r[2]}

        action_counts: list = []
        async with db.execute(
            "SELECT action, action_target, COUNT(*) FROM players"
            " WHERE action IS NOT NULL GROUP BY action, action_target"
        ) as cur:
            async for r in cur:
                action_counts.append((r[0], r[1], r[2]))

        async with db.execute(
            "SELECT * FROM players WHERE user_id=?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
            cols = [d[0] for d in cur.description]
            player_row = dict(zip(cols, row)) if row else {}

        async with db.execute("SELECT * FROM trial_state WHERE id=1") as cur:
            row = await cur.fetchone()
            cols = [d[0] for d in cur.description]
            trial_data = dict(zip(cols, row)) if row else {}

        async with db.execute(
            "SELECT contribution FROM trial_contributions WHERE user_id=?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
        trial_contribution = row[0] if row else 0

        return stage_data, resources, buildings, action_counts, player_row, trial_data, trial_contribution

    async def _render_main(
        self,
        inter,
        *,
        pending_action: str | None = None,
        pending_target: str | None = None,
        trial_message: str | None = None,
        respond=None,
    ) -> None:
        user_id = str(inter.user.id)
        now = datetime.now(timezone.utc)
        events = await settle_complete_cycles(user_id, now)
        # Catch up any due auto-tools for this player before rendering.
        async with get_connection() as db:
            due_auto = await auto_tool_manager.list_active(db, user_id)
        for row in due_auto:
            events.extend(await settle_auto_tool_cycles(user_id, row["tool_type"], now))
        await notification.dispatch_events(self.bot, events)

        async with get_connection() as db:
            await self._get_or_create_player(db, user_id, now)
            stage_data, resources, buildings, action_counts, player_row, trial_data, trial_contribution = (
                await self._fetch_all_data(db, user_id)
            )
            ap = await player_manager.get_ap(db, user_id, now)
            active_auto_tools = await auto_tool_manager.get_active_tool_types(db, user_id)

        player_row["_ap"] = ap
        embed = build_main_embed(
            stage_data, resources, buildings, action_counts, player_row,
            trial_data, trial_contribution, trial_message,
        )
        components = build_main_components(
            player_row, buildings, pending_action=pending_action, pending_target=pending_target,
            trial_data=trial_data, resources=resources, active_auto_tools=active_auto_tools,
        )
        if respond is not None:
            await respond(embed=embed, components=components)
        else:
            await inter.edit_original_response(embed=embed, components=components)

    async def _render_gear(
        self, inter, gear_type: str | None, *, mode: str | None = None, count: str | None = None,
        result: dict | None = None, respond=None
    ) -> None:
        user_id = str(inter.user.id)
        now = datetime.now(timezone.utc)
        async with get_connection() as db:
            async with db.execute(
                """SELECT gear_gathering, gear_building, gear_combat, gear_research
                   FROM players WHERE user_id=?""",
                (user_id,),
            ) as cur:
                row = await cur.fetchone()

            if gear_type is None:
                gear_cap = await building_manager.get_level(db, "research_lab")
                player_gear = _make_player_gear(row)
                embed = build_gear_embed({}, None, result)
                components = build_gear_components(None, None, False, player_gear, gear_cap, materials=0)
                if respond is not None:
                    await respond(embed=embed, components=components)
                else:
                    await inter.edit_original_response(embed=embed, components=components)
                return

            effective_mode = mode or "normal"
            upgrade_info = await gear_manager.get_upgrade_info(db, user_id, gear_type, now, mode=effective_mode)
            gear_level = upgrade_info["gear_level"]
            max_slots = affix_manager.slot_count(gear_level)
            affixes = await affix_manager.get_affixes(db, user_id, gear_type)

        player_gear = _make_player_gear(row)

        embed = build_gear_embed(upgrade_info, gear_type, result, affixes=affixes, max_slots=max_slots)
        components = build_gear_components(
            gear_type, mode, upgrade_info["can_attempt"], player_gear, upgrade_info["gear_cap"],
            affixes=affixes, max_slots=max_slots, materials=upgrade_info["materials"], count=count,
        )
        if respond is not None:
            await respond(embed=embed, components=components)
        else:
            await inter.edit_original_response(embed=embed, components=components)

    async def _render_affix(self, inter, gear_type: str | None, *, selected_group: tuple[str, int] | None = None) -> None:
        user_id = str(inter.user.id)
        now = datetime.now(timezone.utc)
        async with get_connection() as db:
            async with db.execute(
                """SELECT gear_gathering, gear_building, gear_combat, gear_research
                   FROM players WHERE user_id=?""",
                (user_id,),
            ) as cur:
                row = await cur.fetchone()

            if gear_type is None:
                gear_cap = await building_manager.get_level(db, "research_lab")
                player_gear = _make_player_gear(row)
                embed = build_affix_embed(None, player_gear, [], 0)
                components = build_affix_components(None, player_gear, gear_cap, [], 0)
                await inter.edit_original_response(embed=embed, components=components)
                return

            upgrade_info = await gear_manager.get_upgrade_info(db, user_id, gear_type, now)
            gear_level = upgrade_info["gear_level"]
            max_slots = affix_manager.slot_count(gear_level)
            affixes = await affix_manager.get_affixes(db, user_id, gear_type)

        player_gear = _make_player_gear(row)
        embed = build_affix_embed(
            gear_type,
            player_gear,
            affixes,
            max_slots,
            selected_group=selected_group,
            materials=upgrade_info.get("materials", 0),
            universal_materials=upgrade_info.get("universal_materials", 0),
        )
        components = build_affix_components(
            gear_type, player_gear, upgrade_info["gear_cap"], affixes, max_slots, selected_group=selected_group
        )
        await inter.edit_original_response(embed=embed, components=components)

    async def _render_auto_affix(
        self, inter, gear_type: str | None, *, target_affix_type: str | None = None,
        min_value: int | None = None, material_source: str | None = None,
        scope: str | None = None, error: str | None = None,
    ) -> None:
        user_id = str(inter.user.id)
        materials = universal_materials = max_slots = 0
        affixes = []
        if gear_type in _VALID_GEAR_TYPES:
            async with get_connection() as db:
                gear_level = await player_manager.get_gear_level(db, user_id, gear_type)
                max_slots = affix_manager.slot_count(gear_level)
                affixes = await affix_manager.get_affixes(db, user_id, gear_type)
                materials = await player_manager.get_material(db, user_id, gear_type)
                universal_materials = await player_manager.get_universal_material(db, user_id)
        embed = build_auto_affix_embed(
            gear_type, materials, universal_materials, max_slots, affixes,
            target_affix_type, min_value, material_source, error, scope,
        )
        confirmation_token = secrets.token_urlsafe(6)
        components = build_auto_affix_components(
            gear_type, materials, universal_materials, max_slots, affixes,
            target_affix_type, min_value, material_source, error,
            confirmation_token=confirmation_token, scope=scope,
        )
        user_id = str(inter.user.id)
        self._auto_affix_confirmations[user_id] = next(
            component.custom_id
            for row in components for component in row.children
            if component.custom_id.startswith("auto_affix_run:")
        )
        await inter.edit_original_response(embed=embed, components=components)

    async def _execute_clear_affix(self, inter, gear_type: str, slot_index: int) -> None:
        user_id = str(inter.user.id)
        now = datetime.now(timezone.utc)
        affix_event = None
        async with get_connection() as db:
            gear_level = await player_manager.get_gear_level(db, user_id, gear_type)
            try:
                result = await affix_manager.clear_affix(db, user_id, gear_type, slot_index, gear_level, now)
                await db.commit()
                affix_event = {
                    "type": "affix_cleared",
                    "user_display_name": inter.user.display_name,
                    "gear_type": gear_type,
                    "affix_type": result["affix_type"],
                    "value": result["value"],
                }
            except ValueError:
                pass
        if affix_event:
            await notification.dispatch_events(self.bot, [affix_event])

    async def _render_auto_tool(
        self, inter, *,
        selected_tool: str | None = None,
        selected_target: str | None = None,
        selected_delta: int | None = None,
        error: str | None = None,
    ) -> None:
        user_id = str(inter.user.id)
        now = datetime.now(timezone.utc)
        async with get_connection() as db:
            active_rows = await auto_tool_manager.list_active(db, user_id)
            idle_tools = await auto_tool_manager.get_idle_tools(db, user_id)
            materials = {
                r["tool_type"]: await player_manager.get_material(db, user_id, r["tool_type"])
                for r in active_rows
            }
            max_add = 0
            max_subtract = 0
            if selected_tool is not None:
                row = await auto_tool_manager.get(db, user_id, selected_tool)
                expires = row["expires_at"] if row else None
                max_add = auto_tool_manager.max_add_hours(expires, now)
                max_subtract = auto_tool_manager.max_subtract_hours(expires, now)
        max_hours = get_env_int("AUTO_TOOL_MAX_HOURS")
        embed = build_auto_tool_embed(active_rows, max_hours, materials=materials, error=error)
        components = build_auto_tool_components(
            idle_tools, active_rows,
            selected_tool=selected_tool, selected_target=selected_target,
            selected_delta=selected_delta, max_add=max_add, max_subtract=max_subtract,
        )
        await inter.edit_original_response(embed=embed, components=components)

    async def _read_trial_context(self, db) -> tuple[dict, dict]:
        trial_data = await trial_manager.get_trial_info(db)
        resources = {}
        async with db.execute("SELECT resource_type, amount FROM village_resources") as cur:
            async for row in cur:
                resources[row[0]] = row[1]
        return trial_data, resources

    async def _render_trial_targets(self, inter, page: int) -> None:
        now = datetime.now(timezone.utc)
        async with get_connection() as db:
            trial_data, resources = await self._read_trial_context(db)

        if trial_data.get("is_active"):
            await self._render_main(inter, trial_message="⚠️ 試煉已由其他玩家開啟。")
            return
        if trial_manager.is_cooldown_active(trial_data.get("ended_at"), now):
            await self._render_main(inter, trial_message="⚠️ 試煉仍在冷卻中。")
            return
        if trial_manager.get_max_trial_target(resources) == 0:
            await self._render_main(inter, trial_message="⚠️ 村莊資源不足，尚無法開啟試煉。")
            return

        embed = build_trial_target_embed(resources, page)
        components = build_trial_target_components(resources, page)
        await inter.edit_original_response(embed=embed, components=components)

    @commands.slash_command(name="idlevillage-ranking", description="查看各工具等級排行榜")
    async def idlevillage_ranking(self, inter: disnake.ApplicationCommandInteraction) -> None:
        if not self._check_guild(inter):
            return await inter.response.send_message(
                "此指令僅限指定伺服器使用。", ephemeral=True
            )
        self._auto_affix_confirmations.pop(str(inter.user.id), None)
        await inter.response.defer(ephemeral=True)
        async with get_connection() as db:
            rankings = await player_manager.get_gear_rankings(db)
        sliced = {
            gear_type: player_manager.slice_top_levels(entries)
            for gear_type, entries in rankings.items()
        }
        all_user_ids = {uid for entries in sliced.values() for uid, _ in entries}
        name_map = {}
        for uid in all_user_ids:
            try:
                member = await inter.guild.fetch_member(int(uid))
                name_map[uid] = member.display_name
            except Exception:
                name_map[uid] = uid
        text = build_ranking_text(sliced, name_map)
        if len(text) > 1900:
            text = text[:1900] + "\n（排行過長，部分內容已省略）"
        await inter.edit_original_response(content=text)

    @commands.slash_command(name="idlevillage", description="開啟 Idle Village 個人介面")
    async def idlevillage(self, inter: disnake.ApplicationCommandInteraction) -> None:
        if not self._check_guild(inter):
            return await inter.response.send_message(
                "此指令僅限指定伺服器使用。", ephemeral=True
            )
        self._auto_affix_confirmations.pop(str(inter.user.id), None)
        await inter.response.defer(ephemeral=True)
        await self._render_main(inter)

    @commands.Cog.listener("on_button_click")
    async def on_button_click(self, inter: disnake.MessageInteraction) -> None:
        if not self._check_guild(inter):
            return
        cid = inter.component.custom_id
        if not _is_own_button(cid):
            return

        user_id = str(inter.user.id)
        if not cid.startswith("auto_affix_run:"):
            self._auto_affix_confirmations.pop(user_id, None)

        if cid == "burst_execute":
            await inter.response.defer()
            now = datetime.now(timezone.utc)
            success, events = await settle_burst(user_id, now)
            if success:
                await notification.dispatch_events(self.bot, events)
            await self._render_main(inter)

        elif cid == "open_gear_upgrade":
            await inter.response.defer()
            await self._render_gear(inter, None)

        elif cid == "open_auto_tool":
            await inter.response.defer()
            await self._render_auto_tool(inter)

        elif cid.startswith("auto_tool_confirm:"):
            parts = cid.split(":")
            # auto_tool_confirm:{tool}:{delta}:{target|none} — delta is signed hours:
            # start (idle tool) / add_time (delta>0) / subtract_time (delta<0).
            if len(parts) < 4 or parts[1] not in _VALID_GEAR_TYPES:
                return
            tool_type = parts[1]
            try:
                delta = int(parts[2])
            except ValueError:
                return
            target = None if parts[3] == "none" else parts[3]
            await inter.response.defer()
            now = datetime.now(timezone.utc)
            error: str | None = None
            async with get_connection() as db:
                try:
                    if await auto_tool_manager.is_active(db, user_id, tool_type):
                        if delta > 0:
                            await auto_tool_manager.add_time(db, user_id, tool_type, delta, now)
                        else:
                            await auto_tool_manager.subtract_time(db, user_id, tool_type, -delta, now)
                    else:
                        await auto_tool_manager.start(db, user_id, tool_type, delta, target, now)
                    await db.commit()
                except ValueError:
                    error = "⚠️ 操作失敗（素材不足、工具使用中或已達上限），請重新確認。"
            await self._render_auto_tool(inter, error=error)

        elif cid == "open_trial_start":
            await inter.response.defer()
            await self._render_trial_targets(inter, 0)

        elif cid.startswith("trial_target_page:"):
            await inter.response.defer()
            try:
                page = int(cid.split(":", 1)[1])
            except ValueError:
                page = 0
            await self._render_trial_targets(inter, page)

        elif cid == "back_to_main":
            await inter.response.defer()
            await self._render_main(inter)

        elif cid.startswith("confirm_action:"):
            parts = cid.split(":")
            if len(parts) < 2:
                return
            action = parts[1]
            target = parts[2] if len(parts) >= 3 else None

            if action not in _VALID_ACTIONS:
                return
            if action == "building" and target not in UI_BUILDING_TARGETS:
                return

            await inter.response.defer()
            now = datetime.now(timezone.utc)
            try:
                events = await change_action(user_id, action, target, now)
                await notification.dispatch_events(self.bot, events)
            except ValueError:
                pass
            await self._render_main(inter)

        elif cid.startswith("attempt_upgrade:"):
            parts = cid.split(":")
            if len(parts) != 4:
                return
            gear_type, mode, count = parts[1], parts[2], parts[3]
            if (
                gear_type not in _VALID_GEAR_TYPES
                or mode not in _VALID_UPGRADE_MODES
                or count not in _VALID_UPGRADE_COUNTS
            ):
                return
            await inter.response.defer()
            max_attempts = None if count == "inf" else int(count)
            committed: list[dict] = []
            first_error: dict | None = None
            while max_attempts is None or len(committed) < max_attempts:
                try:
                    async with get_connection() as db:
                        attempt = await gear_manager.attempt_upgrade(
                            db, user_id, gear_type, datetime.now(timezone.utc), mode=mode
                        )
                        await db.commit()
                except Exception as exc:
                    if not committed:
                        first_error = {"success": False, "new_level": 0, "rate": 0.0, "error": str(exc)}
                    break
                committed.append(attempt)

            if first_error is not None:
                result = first_error
            else:
                result = committed[-1] if committed else None
            if committed:
                if count == "1":
                    last = committed[0]
                    if last.get("success"):
                        gear_event = {
                            "type": "gear_success",
                            "user_display_name": inter.user.display_name,
                            "gear_type": gear_type,
                            "current_level": last.get("current_level", 0),
                            "target_level": last.get("new_level", last.get("current_level", 0) + 1),
                            "failure_count": last.get("pity_before", 0),
                            "mode": last.get("mode", "normal"),
                        }
                    else:
                        gear_event = {
                            "type": "gear_fail",
                            "user_display_name": inter.user.display_name,
                            "gear_type": gear_type,
                            "current_level": last.get("current_level", 0),
                            "target_level": last.get("target_level", last.get("current_level", 0) + 1),
                            "failure_count": last.get("pity_after", 0),
                            "mode": last.get("mode", "normal"),
                        }
                else:
                    gear_event = {
                        "type": "gear_batch",
                        "user_display_name": inter.user.display_name,
                        "gear_type": gear_type,
                        "mode": mode,
                        "results": [
                            {
                                "success": bool(r.get("success")),
                                "current_level": r.get("current_level", 0),
                                "target_level": (
                                    r.get("new_level", r.get("current_level", 0) + 1)
                                    if r.get("success")
                                    else r.get("target_level", r.get("current_level", 0) + 1)
                                ),
                                "failure_count": (
                                    r.get("pity_before", 0) if r.get("success") else r.get("pity_after", 0)
                                ),
                            }
                            for r in committed
                        ],
                    }
                await notification.dispatch_events(self.bot, [gear_event])
            await self._render_gear(inter, gear_type, mode=mode, count=count, result=result)

        elif cid.startswith("extract_affix:"):
            parts = cid.split(":")
            gear_type = parts[1] if len(parts) > 1 else ""
            if gear_type not in _VALID_GEAR_TYPES:
                return
            await inter.response.defer()
            now = datetime.now(timezone.utc)
            affix_event = None
            async with get_connection() as db:
                gear_level = await player_manager.get_gear_level(db, user_id, gear_type)
                try:
                    result = await affix_manager.extract_affix(db, user_id, gear_type, gear_level, now)
                    await db.commit()
                    affix_event = {
                        "type": "affix_extracted",
                        "user_display_name": inter.user.display_name,
                        "gear_type": gear_type,
                        "affix_type": result["affix_type"],
                        "value": result["value"],
                    }
                except ValueError:
                    pass
            if affix_event:
                await notification.dispatch_events(self.bot, [affix_event])
            await self._render_gear(inter, gear_type)

        elif cid.startswith("clear_affix:"):
            parts = cid.split(":")
            if len(parts) < 3:
                return
            gear_type = parts[1]
            if gear_type not in _VALID_GEAR_TYPES:
                return
            try:
                slot_index = int(parts[2])
            except ValueError:
                return
            await inter.response.defer()
            await self._execute_clear_affix(inter, gear_type, slot_index)
            await self._render_gear(inter, gear_type)

        elif cid.startswith("open_affix_mgmt:"):
            gear_type = cid.split(":", 1)[1]
            if gear_type not in _VALID_GEAR_TYPES:
                return
            await inter.response.defer()
            await self._render_affix(inter, None)

        elif cid.startswith("open_auto_affix:"):
            parts = cid.split(":")
            if len(parts) != 2 or parts[1] not in (*_VALID_GEAR_TYPES, "none"):
                return
            await inter.response.defer()
            await self._render_auto_affix(inter, None if parts[1] == "none" else parts[1])

        elif cid.startswith("back_to_affix:"):
            parts = cid.split(":")
            if len(parts) != 2 or parts[1] not in (*_VALID_GEAR_TYPES, "none"):
                return
            await inter.response.defer()
            await self._render_affix(inter, None if parts[1] == "none" else parts[1])

        elif cid.startswith("auto_affix_run:"):
            registered_id = self._auto_affix_confirmations.get(user_id)
            if cid != registered_id:
                await inter.response.defer()
                return
            self._auto_affix_confirmations.pop(user_id, None)
            parts = cid.split(":")
            state = _parse_auto_affix_state(parts[:6]) if len(parts) == 8 else None
            expected_slot_text = parts[6] if len(parts) == 8 else ""
            token = parts[7] if len(parts) == 8 else ""
            valid_token = len(token) == 8 and all(
                character.isascii() and (character.isalnum() or character in "-_") for character in token
            )
            if state is None or not expected_slot_text.isdecimal() or not valid_token:
                await inter.response.defer()
                gear = parts[1] if len(parts) > 1 else "none"
                gear = gear if gear in _VALID_GEAR_TYPES else None
                await self._render_auto_affix(inter, gear, error="⚠️ 設定無效，請重新選擇。")
                return
            expected_slot = int(expected_slot_text)
            gear, target, value, source, scope = state
            complete = (
                gear in _VALID_GEAR_TYPES and (target == "any" or target in _VALID_AFFIX_TYPES)
                and value in _VALID_AUTO_AFFIX_VALUES and source in {"tool", "universal"}
                and scope in {"one", "all"}
            )
            if not complete:
                await inter.response.defer()
                await self._render_auto_affix(
                    inter, gear if gear in _VALID_GEAR_TYPES else None,
                    target_affix_type=target if target != "none" else None,
                    min_value=int(value) if value != "none" else None,
                    material_source=source if source != "none" else None,
                    scope=scope if scope != "none" else None,
                    error="⚠️ 設定未完成，請重新選擇。",
                )
                return
            await inter.response.defer()
            committed: list[dict] = []
            error = None
            next_slot: int | None = expected_slot
            while True:
                try:
                    async with get_connection() as db:
                        try:
                            gear_level = await player_manager.get_gear_level(db, user_id, gear)
                            if next_slot is None:
                                slots = affix_manager.slot_count(gear_level)
                                filled = {a["slot_index"] for a in await affix_manager.get_affixes(db, user_id, gear)}
                                next_slot = next((i for i in range(slots) if i not in filled), None)
                                if next_slot is None:
                                    break
                            result = await affix_manager.auto_extract_affix(
                                db, user_id, gear, gear_level, datetime.now(timezone.utc),
                                target_affix_type=target if target != "any" else None,
                                min_value=int(value), material_source=source, expected_slot=next_slot,
                            )
                            await db.commit()
                        except Exception:
                            await db.rollback()
                            raise
                except Exception:
                    if not committed:
                        error = "⚠️ 抽取失敗，素材與詞條未變更。"
                    break
                committed.append(result)
                if scope == "one" or not result.get("affix"):
                    break
                next_slot = None
            if error:
                await self._render_auto_affix(
                    inter, gear, target_affix_type=target, min_value=int(value),
                    material_source=source, scope=scope, error=error,
                )
                return
            if committed:
                if scope == "one":
                    event = {
                        "type": "affix_auto_extracted",
                        "user_display_name": inter.user.display_name,
                        "gear_type": gear,
                        **committed[0],
                    }
                else:
                    event = {
                        "type": "affix_auto_batch",
                        "user_display_name": inter.user.display_name,
                        "gear_type": gear,
                        "material_source": source,
                        "results": [
                            {"affix": r.get("affix"), "attempts": r.get("attempts", 0),
                             "material_spent": r.get("material_spent", 0)}
                            for r in committed
                        ],
                    }
                await notification.dispatch_events(self.bot, [event])
            await self._render_affix(inter, gear)

        elif cid.startswith("affix_extract:"):
            gear_type = cid.split(":", 1)[1]
            if gear_type not in _VALID_GEAR_TYPES:
                return
            await inter.response.defer()
            now = datetime.now(timezone.utc)
            affix_event = None
            async with get_connection() as db:
                gear_level = await player_manager.get_gear_level(db, user_id, gear_type)
                try:
                    result = await affix_manager.extract_affix(db, user_id, gear_type, gear_level, now)
                    await db.commit()
                    affix_event = {
                        "type": "affix_extracted",
                        "user_display_name": inter.user.display_name,
                        "gear_type": gear_type,
                        "affix_type": result["affix_type"],
                        "value": result["value"],
                    }
                except ValueError:
                    pass
            if affix_event:
                await notification.dispatch_events(self.bot, [affix_event])
            await self._render_affix(inter, gear_type)

        elif cid.startswith("affix_clear:"):
            parts = cid.split(":")
            if len(parts) != 4:
                return
            gear_type, affix_type = parts[1], parts[2]
            if gear_type not in _VALID_GEAR_TYPES or affix_type not in _VALID_AFFIX_TYPES:
                return
            if parts[3] not in _VALID_AUTO_AFFIX_VALUES:
                return
            value = int(parts[3])
            await inter.response.defer()
            async with get_connection() as db:
                affixes = await affix_manager.get_affixes(db, str(inter.user.id), gear_type)
            slots = [a["slot_index"] for a in affixes if a["affix_type"] == affix_type and a["value"] == value]
            if slots:
                await self._execute_clear_affix(inter, gear_type, max(slots))
            await self._render_affix(inter, gear_type)

        elif cid.startswith("back_to_gear:"):
            gear_type = cid.split(":", 1)[1]
            await inter.response.defer()
            if gear_type not in _VALID_GEAR_TYPES:
                await self._render_gear(inter, None)
                return
            await self._render_gear(inter, gear_type)

        elif cid.startswith("sacrifice_material:"):
            parts = cid.split(":")
            gear_type = parts[1] if len(parts) > 1 else ""
            if gear_type not in _VALID_GEAR_TYPES:
                return
            mat_col = ACTION_MATERIAL_COL[gear_type]
            async with get_connection() as db:
                async with db.execute(
                    f"SELECT {mat_col} FROM players WHERE user_id=?", (user_id,)
                ) as cur:
                    row = await cur.fetchone()
            holdings = row[0] if row else 0
            mat_label = f"{ACTION_EMOJIS[gear_type]} {ACTION_LABELS[gear_type]} 素材"
            await inter.response.send_modal(
                disnake.ui.Modal(
                    title="🩸 獻祭素材",
                    custom_id=f"modal_sacrifice:{gear_type}",
                    components=[
                        disnake.ui.TextInput(
                            label=f"投入 {mat_label}（持有：{holdings}）",
                            custom_id="sacrifice_amount",
                            style=disnake.TextInputStyle.short,
                            placeholder=f"1 ~ {holdings}",
                            required=True,
                        ),
                    ],
                )
            )

    @commands.Cog.listener("on_modal_submit")
    async def on_modal_submit(self, inter: disnake.ModalInteraction) -> None:
        if not self._check_guild(inter):
            return
        cid = inter.custom_id
        if not _is_own_modal(cid):
            return

        self._auto_affix_confirmations.pop(str(inter.user.id), None)

        if cid.startswith("modal_sacrifice:"):
            gear_type = cid.split(":", 1)[1]
            if gear_type not in _VALID_GEAR_TYPES:
                return
            raw = inter.text_values.get("sacrifice_amount", "").strip()
            now = datetime.now(timezone.utc)
            result: dict | None = None
            try:
                amount = int(raw)
                async with get_connection() as db:
                    result = await gear_manager.sacrifice_material(db, str(inter.user.id), gear_type, amount, now)
                    await db.commit()
            except (ValueError, KeyError) as exc:
                result = {"error": str(exc) or "無效輸入"}
            await self._render_gear(
                inter, gear_type, result=result,
                respond=lambda **kw: inter.response.edit_message(**kw),
            )

    @commands.Cog.listener("on_dropdown")
    async def on_dropdown(self, inter: disnake.MessageInteraction) -> None:
        if not self._check_guild(inter):
            return
        cid = inter.component.custom_id
        if not _is_own_dropdown(cid):
            return

        value = inter.values[0] if inter.values else None
        user_id = str(inter.user.id)
        self._auto_affix_confirmations.pop(user_id, None)
        await inter.response.defer()

        if cid == "action_select":
            await self._render_main(inter, pending_action=value)
        elif cid == "building_target_select":
            await self._render_main(inter, pending_action="building", pending_target=value)
        elif cid == "gear_type_select":
            if value in _VALID_GEAR_TYPES:
                await self._render_gear(inter, value)
        elif cid.startswith("upgrade_mode_select:"):
            parts = cid.split(":")
            if len(parts) != 3:
                return
            gear_type, count = parts[1], parts[2]
            if (
                value in _VALID_UPGRADE_MODES
                and gear_type in _VALID_GEAR_TYPES
                and count in _VALID_UPGRADE_COUNTS | {"none"}
            ):
                await self._render_gear(inter, gear_type, mode=value, count=None if count == "none" else count)
        elif cid.startswith("upgrade_count_select:"):
            parts = cid.split(":")
            if len(parts) != 3:
                return
            gear_type, mode = parts[1], parts[2]
            if (
                value in _VALID_UPGRADE_COUNTS
                and gear_type in _VALID_GEAR_TYPES
                and mode in _VALID_UPGRADE_MODES | {"none"}
            ):
                await self._render_gear(inter, gear_type, mode=None if mode == "none" else mode, count=value)
        elif cid == "affix_gear_select":
            if value in _VALID_GEAR_TYPES:
                await self._render_affix(inter, value)
        elif cid.startswith("affix_slot_select:"):
            gear_type = cid.split(":", 1)[1]
            if gear_type not in _VALID_GEAR_TYPES:
                return
            affix_type, sep, raw_value = value.partition(":")
            if not sep or affix_type not in _VALID_AFFIX_TYPES or raw_value not in _VALID_AUTO_AFFIX_VALUES:
                return
            await self._render_affix(inter, gear_type, selected_group=(affix_type, int(raw_value)))

        elif cid == "auto_tool_type_select":
            if value in _VALID_GEAR_TYPES:
                await self._render_auto_tool(inter, selected_tool=value)
        elif cid.startswith("auto_tool_target_select:"):
            tool_type = cid.split(":", 1)[1]
            if tool_type in _VALID_GEAR_TYPES and value in UI_BUILDING_TARGETS:
                await self._render_auto_tool(inter, selected_tool=tool_type, selected_target=value)
        elif cid.startswith("auto_tool_add_select:") or cid.startswith("auto_tool_sub_select:"):
            parts = cid.split(":")
            if len(parts) < 3 or parts[1] not in _VALID_GEAR_TYPES:
                return
            tool_type = parts[1]
            target = None if parts[2] == "none" else parts[2]
            try:
                delta = int(value)
            except ValueError:
                return
            await self._render_auto_tool(
                inter, selected_tool=tool_type, selected_target=target, selected_delta=delta
            )
        elif cid.startswith(("auto_affix_target:", "auto_affix_value:", "auto_affix_material:", "auto_affix_scope:")):
            parts = cid.split(":")
            state = _parse_auto_affix_state(parts)
            prefix = parts[0]
            valid_values = {
                "auto_affix_target": {"any", *_VALID_AFFIX_TYPES},
                "auto_affix_value": _VALID_AUTO_AFFIX_VALUES,
                "auto_affix_material": {"tool", "universal"},
                "auto_affix_scope": {"one", "all"},
            }
            if state is None or value not in valid_values[prefix]:
                return
            gear, target, threshold, source, scope = state
            if prefix == "auto_affix_target":
                target = value
            elif prefix == "auto_affix_value":
                threshold = value
            elif prefix == "auto_affix_material":
                source = value
            else:
                scope = value
            await self._render_auto_affix(
                inter, gear if gear != "none" else None,
                target_affix_type=target if target != "none" else None,
                min_value=int(threshold) if threshold != "none" else None,
                material_source=source if source != "none" else None,
                scope=scope if scope != "none" else None,
            )
        elif cid == "trial_target_select":
            try:
                target = int(value)
            except (TypeError, ValueError):
                await self._render_main(inter, trial_message="⚠️ 試煉目標無效，請重新選擇。")
                return

            now = datetime.now(timezone.utc)
            trial_message = None
            trial_started_event = None
            async with get_connection() as db:
                try:
                    info = await trial_manager.start_trial(db, now, target)
                    await db.commit()
                    divisor = get_env_int("TRIAL_REWARD_DIVISOR")
                    duration = get_env_int("TRIAL_DURATION_SECONDS")
                    trial_started_event = {
                        "type": "trial_start",
                        "resource_type": info["resource_type"],
                        "target": info["target"],
                        "reward_pool": info["target"] // divisor,
                        "deadline_unix": int(now.timestamp()) + duration,
                    }
                    trial_message = "✅ 試煉已開始！"
                except trial_manager.TrialStartError as error:
                    trial_message = {
                        "active": "⚠️ 試煉已由其他玩家開啟。",
                        "cooldown": "⚠️ 試煉仍在冷卻中。",
                        "invalid_target": "⚠️ 試煉目標無效，請重新選擇。",
                        "stale_target": "⚠️ 資源已變動，所選目標已無法支付。",
                    }[error.reason]
            await self._render_main(inter, trial_message=trial_message)
            if trial_started_event is not None:
                await notification.dispatch_events(self.bot, [trial_started_event])


def setup(bot: commands.Bot) -> None:
    bot.add_cog(ActionsCog(bot))

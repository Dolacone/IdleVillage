from datetime import datetime, timedelta, timezone

import disnake
from disnake.ext import commands

from cogs.ui_renderer import (
    ACTION_EMOJIS,
    ACTION_LABELS,
    RESOURCE_LABELS,
    UI_BUILDING_TARGETS,
    build_affix_components,
    build_affix_embed,
    build_gear_components,
    build_gear_embed,
    build_main_components,
    build_main_embed,
    build_ranking_text,
)
from core import notification
from core.config import get_discord_guild_id, get_env_int
from core.formula import ACTION_MATERIAL_COL
from core.settlement import change_action, settle_burst, settle_complete_cycles
from core.utils import dt_str
from database.schema import get_connection
from managers import affix_manager, building_manager, gear_manager, player_manager, resource_manager, trial_manager

_OWN_BUTTONS = frozenset({"burst_execute", "open_gear_upgrade", "open_trial_start", "back_to_main"})
_OWN_BUTTON_PREFIXES = ("confirm_action:", "attempt_upgrade:", "clear_affix:", "sacrifice_material:", "open_affix_mgmt:", "affix_extract:", "affix_clear:", "back_to_gear:")
_OWN_DROPDOWNS = frozenset({"action_select", "building_target_select", "gear_type_select", "affix_gear_select"})
_OWN_DROPDOWN_PREFIXES = ("upgrade_mode_select:", "affix_slot_select:")
_OWN_MODAL_PREFIXES = ("modal_sacrifice:", "modal_start_trial")
_VALID_GEAR_TYPES = frozenset({"gathering", "building", "combat", "research"})
_VALID_ACTIONS = frozenset({"gathering", "building", "combat", "research"})
_VALID_UPGRADE_MODES = frozenset(gear_manager.UPGRADE_MODES)
_TRIAL_RESOURCE_LABELS_TO_TYPE = {"食物": "food", "木頭": "wood", "知識": "knowledge"}


def _parse_trial_resource(raw: str) -> str | None:
    raw = raw.strip()
    if raw in _TRIAL_RESOURCE_LABELS_TO_TYPE:
        return _TRIAL_RESOURCE_LABELS_TO_TYPE[raw]
    lowered = raw.lower()
    if lowered in trial_manager.TRIAL_RESOURCE_TYPES:
        return lowered
    return None


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
        await notification.dispatch_events(self.bot, events)

        async with get_connection() as db:
            await self._get_or_create_player(db, user_id, now)
            stage_data, resources, buildings, action_counts, player_row, trial_data, trial_contribution = (
                await self._fetch_all_data(db, user_id)
            )
            ap = await player_manager.get_ap(db, user_id, now)

        player_row["_ap"] = ap
        embed = build_main_embed(
            stage_data, resources, buildings, action_counts, player_row,
            trial_data, trial_contribution, trial_message,
        )
        components = build_main_components(
            player_row, buildings, pending_action=pending_action, pending_target=pending_target,
            trial_data=trial_data,
        )
        if respond is not None:
            await respond(embed=embed, components=components)
        else:
            await inter.edit_original_response(embed=embed, components=components)

    async def _render_gear(
        self, inter, gear_type: str | None, *, mode: str | None = None, result: dict | None = None, respond=None
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
            affixes=affixes, max_slots=max_slots, materials=upgrade_info["materials"],
        )
        if respond is not None:
            await respond(embed=embed, components=components)
        else:
            await inter.edit_original_response(embed=embed, components=components)

    async def _render_affix(self, inter, gear_type: str | None, *, selected_slot: int | None = None) -> None:
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
        embed = build_affix_embed(gear_type, player_gear, affixes, max_slots, selected_slot=selected_slot)
        components = build_affix_components(
            gear_type, player_gear, upgrade_info["gear_cap"], affixes, max_slots, selected_slot=selected_slot
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

    @commands.slash_command(name="idlevillage-ranking", description="查看各工具等級排行榜")
    async def idlevillage_ranking(self, inter: disnake.ApplicationCommandInteraction) -> None:
        if not self._check_guild(inter):
            return await inter.response.send_message(
                "此指令僅限指定伺服器使用。", ephemeral=True
            )
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

        elif cid == "open_trial_start":
            await inter.response.send_modal(
                disnake.ui.Modal(
                    title="🏆 開啟試煉",
                    custom_id="modal_start_trial",
                    components=[
                        disnake.ui.TextInput(
                            label="資源類型（食物 / 木頭 / 知識）",
                            custom_id="trial_resource",
                            style=disnake.TextInputStyle.short,
                            placeholder="食物 / 木頭 / 知識",
                            required=True,
                        ),
                        disnake.ui.TextInput(
                            label="目標值（1000 的整數倍）",
                            custom_id="trial_target",
                            style=disnake.TextInputStyle.short,
                            placeholder="例如：5000",
                            required=True,
                        ),
                    ],
                )
            )

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
            gear_type = parts[1] if len(parts) > 1 else ""
            mode = parts[2] if len(parts) > 2 else "normal"
            if gear_type not in _VALID_GEAR_TYPES or mode not in _VALID_UPGRADE_MODES:
                return
            await inter.response.defer()
            now = datetime.now(timezone.utc)
            result: dict | None = None
            try:
                async with get_connection() as db:
                    result = await gear_manager.attempt_upgrade(db, user_id, gear_type, now, mode=mode)
                    await db.commit()
            except ValueError as exc:
                result = {"success": False, "new_level": 0, "rate": 0.0, "error": str(exc)}
            if result and "error" not in result:
                if result.get("success"):
                    gear_event = {
                        "type": "gear_success",
                        "user_display_name": inter.user.display_name,
                        "gear_type": gear_type,
                        "current_level": result.get("current_level", 0),
                        "target_level": result.get("new_level", result.get("current_level", 0) + 1),
                        "failure_count": result.get("pity_before", 0),
                        "mode": result.get("mode", "normal"),
                    }
                else:
                    gear_event = {
                        "type": "gear_fail",
                        "user_display_name": inter.user.display_name,
                        "gear_type": gear_type,
                        "current_level": result.get("current_level", 0),
                        "target_level": result.get("target_level", result.get("current_level", 0) + 1),
                        "failure_count": result.get("pity_after", 0),
                        "mode": result.get("mode", "normal"),
                    }
                await notification.dispatch_events(self.bot, [gear_event])
            await self._render_gear(inter, gear_type, mode=mode, result=result)

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

        elif cid == "modal_start_trial":
            raw_resource = inter.text_values.get("trial_resource", "")
            raw_target = inter.text_values.get("trial_target", "").strip()
            resource = _parse_trial_resource(raw_resource)
            now = datetime.now(timezone.utc)
            trial_message: str
            trial_started_event: dict | None = None

            if resource is None:
                trial_message = "⚠️ 資源類型須為「食物」「木頭」或「知識」。"
            else:
                try:
                    target = int(raw_target)
                except ValueError:
                    target = None

                if target is None:
                    trial_message = "⚠️ 目標值須為整數。"
                else:
                    step = trial_manager.get_invalid_target_step(target)
                    if step is not None:
                        trial_message = f"⚠️ 目標值必須為 {step} 的整數倍。"
                    else:
                        async with get_connection() as db:
                            info = await trial_manager.get_trial_info(db)
                            if info.get("is_active"):
                                trial_message = "⚠️ 目前已有試煉進行中，無法開啟新試煉。"
                            elif trial_manager.is_cooldown_active(info.get("ended_at"), now):
                                cooldown_end_unix = trial_manager.get_cooldown_deadline_unix(info.get("ended_at"))
                                trial_message = f"⚠️ 試煉冷卻中，<t:{cooldown_end_unix}:R> 才能再次開啟試煉。"
                            elif not await resource_manager.can_afford(db, resource, target):
                                balance = await resource_manager.balance(db, resource)
                                r_label = RESOURCE_LABELS.get(resource, resource)
                                trial_message = f"⚠️ 村莊{r_label}不足，目前僅有 {balance} 個，需要 {target} 個。"
                            else:
                                try:
                                    await trial_manager.start_trial(db, resource, target, str(inter.user.id), now)
                                    await db.commit()
                                    trial_message = "✅ 試煉已開始！"
                                    divisor = get_env_int("TRIAL_REWARD_DIVISOR")
                                    duration = get_env_int("TRIAL_DURATION_SECONDS")
                                    trial_started_event = {
                                        "type": "trial_start",
                                        "user_id": str(inter.user.id),
                                        "resource_type": resource,
                                        "target": target,
                                        "reward_pool": target // divisor,
                                        "deadline_unix": int(now.timestamp()) + duration,
                                    }
                                except ValueError:
                                    trial_message = "⚠️ 開啟試煉失敗，請重新嘗試。"

            await self._render_main(
                inter, trial_message=trial_message,
                respond=lambda **kw: inter.response.edit_message(**kw),
            )
            if trial_started_event is not None:
                await notification.dispatch_events(self.bot, [trial_started_event])

    @commands.Cog.listener("on_dropdown")
    async def on_dropdown(self, inter: disnake.MessageInteraction) -> None:
        if not self._check_guild(inter):
            return
        cid = inter.component.custom_id
        if not _is_own_dropdown(cid):
            return

        value = inter.values[0]
        user_id = str(inter.user.id)
        await inter.response.defer()

        if cid == "action_select":
            await self._render_main(inter, pending_action=value)
        elif cid == "building_target_select":
            await self._render_main(inter, pending_action="building", pending_target=value)
        elif cid == "gear_type_select":
            if value in _VALID_GEAR_TYPES:
                await self._render_gear(inter, value)
        elif cid.startswith("upgrade_mode_select:"):
            gear_type = cid.split(":", 1)[1]
            if value in _VALID_UPGRADE_MODES and gear_type in _VALID_GEAR_TYPES:
                await self._render_gear(inter, gear_type, mode=value)
        elif cid == "affix_gear_select":
            if value in _VALID_GEAR_TYPES:
                await self._render_affix(inter, value)
        elif cid.startswith("affix_slot_select:"):
            gear_type = cid.split(":", 1)[1]
            if gear_type not in _VALID_GEAR_TYPES:
                return
            try:
                slot_index = int(value)
            except ValueError:
                return
            await self._render_affix(inter, gear_type, selected_slot=slot_index)


def setup(bot: commands.Bot) -> None:
    bot.add_cog(ActionsCog(bot))

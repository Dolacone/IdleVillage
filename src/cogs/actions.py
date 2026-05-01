import time
from datetime import datetime, timedelta, timezone

import disnake
from disnake.ext import commands

from cogs.ui_renderer import (
    UI_BUILDING_TARGETS,
    build_gear_components,
    build_gear_embed,
    build_main_components,
    build_main_embed,
)
from core.config import get_discord_guild_id, get_env_int
from core.settlement import change_action, settle_burst, settle_complete_cycles
from core.utils import dt_str
from database.schema import get_connection
from managers import gear_manager, player_manager

_OWN_BUTTONS = frozenset(
    {"refresh", "burst_execute", "open_gear_upgrade", "back_to_main"}
)
_OWN_BUTTON_PREFIXES = ("confirm_action:", "attempt_upgrade:")
_OWN_DROPDOWNS = frozenset({"action_select", "building_target_select", "gear_type_select"})
_VALID_GEAR_TYPES = frozenset({"gathering", "building", "combat", "research"})
_VALID_ACTIONS = frozenset({"gathering", "building", "combat", "research"})


def _is_own_button(cid: str) -> bool:
    return cid in _OWN_BUTTONS or any(cid.startswith(p) for p in _OWN_BUTTON_PREFIXES)


class ActionsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._refresh_cooldowns: dict[str, float] = {}

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
    ) -> tuple[dict, dict, dict, list, dict]:
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

        return stage_data, resources, buildings, action_counts, player_row

    async def _render_main(
        self,
        inter,
        *,
        pending_action: str | None = None,
        pending_target: str | None = None,
    ) -> None:
        user_id = str(inter.user.id)
        now = datetime.now(timezone.utc)
        await settle_complete_cycles(user_id, now)

        async with get_connection() as db:
            await self._get_or_create_player(db, user_id, now)
            stage_data, resources, buildings, action_counts, player_row = (
                await self._fetch_all_data(db, user_id)
            )
            ap = await player_manager.get_ap(db, user_id, now)

        player_row["_ap"] = ap
        embed = build_main_embed(stage_data, resources, buildings, action_counts, player_row)
        components = build_main_components(
            player_row, buildings, pending_action=pending_action, pending_target=pending_target
        )
        await inter.edit_original_response(embed=embed, components=components)

    async def _render_gear(
        self, inter, gear_type: str, *, result: dict | None = None
    ) -> None:
        user_id = str(inter.user.id)
        now = datetime.now(timezone.utc)
        async with get_connection() as db:
            upgrade_info = await gear_manager.get_upgrade_info(db, user_id, gear_type, now)

        embed = build_gear_embed(upgrade_info, gear_type, result)
        components = build_gear_components(gear_type, upgrade_info["can_attempt"])
        await inter.edit_original_response(embed=embed, components=components)

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

        if cid == "refresh":
            now_mono = time.monotonic()
            last = self._refresh_cooldowns.get(user_id, 0.0)
            cooldown = get_env_int("REFRESH_COOLDOWN_SECONDS")
            if now_mono - last < cooldown:
                remaining = max(1, int(cooldown - (now_mono - last)))
                return await inter.response.send_message(
                    f"冷卻中，請 {remaining} 秒後再試。", ephemeral=True
                )
            self._refresh_cooldowns[user_id] = now_mono
            await inter.response.defer()
            await self._render_main(inter)

        elif cid == "burst_execute":
            await inter.response.defer()
            now = datetime.now(timezone.utc)
            await settle_burst(user_id, now)
            await self._render_main(inter)

        elif cid == "open_gear_upgrade":
            await inter.response.defer()
            await self._render_gear(inter, "gathering")

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
                await change_action(user_id, action, target, now)
            except ValueError:
                pass
            await self._render_main(inter)

        elif cid.startswith("attempt_upgrade:"):
            gear_type = cid.split(":", 1)[1]
            if gear_type not in _VALID_GEAR_TYPES:
                return
            await inter.response.defer()
            now = datetime.now(timezone.utc)
            result: dict | None = None
            try:
                async with get_connection() as db:
                    result = await gear_manager.attempt_upgrade(db, user_id, gear_type, now)
                    await db.commit()
            except ValueError as exc:
                result = {"success": False, "new_level": 0, "rate": 0.0, "error": str(exc)}
            await self._render_gear(inter, gear_type, result=result)

    @commands.Cog.listener("on_dropdown")
    async def on_dropdown(self, inter: disnake.MessageInteraction) -> None:
        if not self._check_guild(inter):
            return
        cid = inter.component.custom_id
        if cid not in _OWN_DROPDOWNS:
            return

        value = inter.values[0]
        await inter.response.defer()

        if cid == "action_select":
            await self._render_main(inter, pending_action=value)
        elif cid == "building_target_select":
            await self._render_main(inter, pending_action="building", pending_target=value)
        elif cid == "gear_type_select":
            if value in _VALID_GEAR_TYPES:
                await self._render_gear(inter, value)


def setup(bot: commands.Bot) -> None:
    bot.add_cog(ActionsCog(bot))

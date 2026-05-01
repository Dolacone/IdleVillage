from datetime import datetime, timezone

import disnake
from disnake.ext import commands

from cogs.ui_renderer import (
    build_admin_components,
    build_admin_embed,
    build_village_embed,
)
from core.config import get_discord_guild_id, get_env_int, is_admin
from database.schema import get_connection
from managers import resource_manager

_OWN_BUTTON_PREFIXES = (
    "resource_add_small:",
    "resource_add_large:",
    "resource_sub_small:",
    "resource_sub_large:",
    "resource_set_custom:",
)
_VALID_RESOURCES = frozenset({"food", "wood", "knowledge"})
_VALID_ACTIONS = frozenset({"gathering", "building", "combat", "research"})
_VALID_GEAR_TYPES = frozenset({"gathering", "building", "combat", "research"})

HELP_TEXT = (
    "**Idle Village 指令說明**\n\n"
    "`/idlevillage` — 開啟個人主介面，查看村莊狀態、管理行動與裝備強化。\n"
    "`/idlevillage-help` — 顯示此說明。\n\n"
    "**行動類型**\n"
    "🌾 採集、🔨 建設、⚔️ 戰鬥、🔬 研究\n\n"
    "**AP 系統**\n"
    "AP 會隨時間自動回復，可用於爆發執行（即時結算 3 個週期）或裝備強化。\n\n"
    "**裝備強化**\n"
    "消耗 1 AP + 對應素材，成功升等裝備；失敗時保底計數 +1 以提高下次成功率。"
)


def _is_own_button(cid: str) -> bool:
    return any(cid.startswith(p) for p in _OWN_BUTTON_PREFIXES)


class GeneralCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _check_guild(self, inter) -> bool:
        return str(inter.guild_id) == get_discord_guild_id()

    def _check_admin(self, inter) -> bool:
        return is_admin(inter.user.id)

    async def _fetch_village_data(self, db) -> tuple[dict, dict, dict, list]:
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

        return stage_data, resources, buildings, action_counts

    @commands.slash_command(
        name="idlevillage-help", description="顯示 Idle Village 遊戲說明"
    )
    async def help_cmd(self, inter: disnake.ApplicationCommandInteraction) -> None:
        if not self._check_guild(inter):
            return await inter.response.send_message(
                "此指令僅限指定伺服器使用。", ephemeral=True
            )
        await inter.response.send_message(HELP_TEXT, ephemeral=True)

    @commands.slash_command(
        name="idlevillage-announcement",
        description="（管理員）設定村莊公告頻道並發布公告",
    )
    async def announcement(self, inter: disnake.ApplicationCommandInteraction) -> None:
        if not self._check_guild(inter):
            return await inter.response.send_message(
                "此指令僅限指定伺服器使用。", ephemeral=True
            )
        if not self._check_admin(inter):
            return await inter.response.send_message(
                "此指令僅限管理員使用。", ephemeral=True
            )
        await inter.response.defer(ephemeral=True)

        channel_id = str(inter.channel_id)
        now_str = datetime.now(timezone.utc).isoformat()
        async with get_connection() as db:
            await db.execute(
                "UPDATE village_state SET announcement_channel_id=?, updated_at=? WHERE id=1",
                (channel_id, now_str),
            )
            await db.commit()
            stage_data, resources, buildings, action_counts = (
                await self._fetch_village_data(db)
            )

        embed = build_village_embed(stage_data, resources, buildings, action_counts)
        dashboard_msg = await inter.channel.send(embed=embed)
        now_str = datetime.now(timezone.utc).isoformat()
        async with get_connection() as db:
            await db.execute(
                "UPDATE village_state SET dashboard_channel_id=?, dashboard_message_id=?, updated_at=? WHERE id=1",
                (str(inter.channel_id), str(dashboard_msg.id), now_str),
            )
            await db.commit()
        await inter.edit_original_response(content="✅ 公告頻道已設定，村莊狀態公告已發布。")

    @commands.slash_command(
        name="idlevillage-manage",
        description="（管理員）管理村莊資源",
    )
    async def manage(self, inter: disnake.ApplicationCommandInteraction) -> None:
        if not self._check_guild(inter):
            return await inter.response.send_message(
                "此指令僅限指定伺服器使用。", ephemeral=True
            )
        if not self._check_admin(inter):
            return await inter.response.send_message(
                "此指令僅限管理員使用。", ephemeral=True
            )
        await inter.response.defer(ephemeral=True)

        resource_type = "food"
        async with get_connection() as db:
            amount = await resource_manager.balance(db, resource_type)

        embed = build_admin_embed(resource_type, amount)
        components = build_admin_components(resource_type)
        await inter.edit_original_response(embed=embed, components=components)

    @commands.Cog.listener("on_button_click")
    async def on_button_click(self, inter: disnake.MessageInteraction) -> None:
        cid = inter.component.custom_id
        if not _is_own_button(cid):
            return
        if not self._check_guild(inter):
            return
        if not self._check_admin(inter):
            return await inter.response.send_message(
                "此操作僅限管理員。", ephemeral=True
            )

        parts = cid.split(":", 1)
        operation = parts[0]
        resource_type = parts[1] if len(parts) > 1 else "food"

        if resource_type not in _VALID_RESOURCES:
            return

        if operation == "resource_set_custom":
            return await inter.response.send_modal(
                title=f"設定 {resource_type} 數量",
                custom_id=f"modal_set_resource:{resource_type}",
                components=[
                    disnake.ui.TextInput(
                        label="數量（整數 ≥ 0）",
                        custom_id="amount",
                        style=disnake.TextInputStyle.short,
                        required=True,
                        placeholder="請輸入整數",
                    )
                ],
            )

        await inter.response.defer()

        small = get_env_int("ADMIN_RESOURCE_DELTA_SMALL")
        large = get_env_int("ADMIN_RESOURCE_DELTA_LARGE")
        delta_map = {
            "resource_add_small": small,
            "resource_add_large": large,
            "resource_sub_small": -small,
            "resource_sub_large": -large,
        }
        delta = delta_map.get(operation, 0)
        now = datetime.now(timezone.utc)

        async with get_connection() as db:
            if delta > 0:
                await resource_manager.deposit(db, resource_type, delta, now)
            elif delta < 0:
                await resource_manager.withdraw(db, resource_type, abs(delta), now)
            await db.commit()
            amount = await resource_manager.balance(db, resource_type)

        embed = build_admin_embed(resource_type, amount)
        components = build_admin_components(resource_type)
        await inter.edit_original_response(embed=embed, components=components)

    @commands.Cog.listener("on_dropdown")
    async def on_dropdown(self, inter: disnake.MessageInteraction) -> None:
        cid = inter.component.custom_id
        if cid != "resource_select":
            return
        if not self._check_guild(inter):
            return
        if not self._check_admin(inter):
            return await inter.response.send_message(
                "此操作僅限管理員。", ephemeral=True
            )

        resource_type = inter.values[0]
        if resource_type not in _VALID_RESOURCES:
            return

        await inter.response.defer()
        now = datetime.now(timezone.utc)
        async with get_connection() as db:
            amount = await resource_manager.balance(db, resource_type)

        embed = build_admin_embed(resource_type, amount)
        components = build_admin_components(resource_type)
        await inter.edit_original_response(embed=embed, components=components)

    @commands.Cog.listener("on_modal_submit")
    async def on_modal_submit(self, inter: disnake.ModalInteraction) -> None:
        if not inter.custom_id.startswith("modal_set_resource:"):
            return
        if not self._check_guild(inter):
            return
        if not self._check_admin(inter):
            return await inter.response.send_message(
                "此操作僅限管理員。", ephemeral=True
            )

        resource_type = inter.custom_id.split(":", 1)[1]
        if resource_type not in _VALID_RESOURCES:
            return

        raw = inter.text_values.get("amount", "").strip()
        try:
            new_amount = int(raw)
            if new_amount < 0:
                raise ValueError
        except ValueError:
            return await inter.response.send_message(
                "請輸入 ≥ 0 的整數。", ephemeral=True
            )

        await inter.response.defer()
        now = datetime.now(timezone.utc)
        async with get_connection() as db:
            current = await resource_manager.balance(db, resource_type)
            if new_amount >= current:
                await resource_manager.deposit(db, resource_type, new_amount - current, now)
            else:
                await resource_manager.withdraw(db, resource_type, current - new_amount, now)
            await db.commit()

        embed = build_admin_embed(resource_type, new_amount)
        components = build_admin_components(resource_type)
        await inter.edit_original_response(embed=embed, components=components)


def setup(bot: commands.Bot) -> None:
    bot.add_cog(GeneralCog(bot))

from datetime import datetime, timezone

import disnake
from disnake.ext import commands

from cogs.ui_renderer import build_manager_components, build_manager_embed
from core.config import get_discord_guild_id, is_admin
from database.schema import get_connection
from managers import player_manager


class PlayerManagerCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _check_guild(self, inter) -> bool:
        return str(inter.guild_id) == get_discord_guild_id()

    def _check_admin(self, inter) -> bool:
        return is_admin(inter.user.id)

    async def _fetch_player_data(self, db, user_id: str) -> dict | None:
        """Query all managed player fields from DB. Returns a dict or None if not found."""
        async with db.execute(
            "SELECT gear_gathering, gear_building, gear_combat, gear_research, "
            "materials_gathering, materials_building, materials_combat, materials_research, "
            "materials_universal, "
            "pity_gathering, pity_building, pity_combat, pity_research, "
            "risky_failed_levels FROM players WHERE user_id=?",
            (user_id,),
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            return None
        (
            gear_gathering, gear_building, gear_combat, gear_research,
            materials_gathering, materials_building, materials_combat, materials_research,
            materials_universal,
            pity_gathering, pity_building, pity_combat, pity_research,
            risky_failed_levels,
        ) = row
        return {
            "gear_gathering": gear_gathering,
            "gear_building": gear_building,
            "gear_combat": gear_combat,
            "gear_research": gear_research,
            "materials_gathering": materials_gathering,
            "materials_building": materials_building,
            "materials_combat": materials_combat,
            "materials_research": materials_research,
            "materials_universal": materials_universal,
            "pity_gathering": pity_gathering,
            "pity_building": pity_building,
            "pity_combat": pity_combat,
            "pity_research": pity_research,
            "risky_failed_levels": risky_failed_levels,
        }

    @commands.slash_command(
        name="idlevillage-manager",
        description="（管理員）管理玩家數據",
    )
    async def manager(self, inter: disnake.ApplicationCommandInteraction) -> None:
        if not self._check_guild(inter):
            return await inter.response.send_message("此指令僅限指定伺服器使用。", ephemeral=True)
        if not self._check_admin(inter):
            return await inter.response.send_message("此指令僅限管理員使用。", ephemeral=True)
        await inter.response.defer(ephemeral=True)
        await inter.edit_original_response(
            content="請選擇要管理的玩家：",
            components=[
                disnake.ui.ActionRow(
                    disnake.ui.UserSelect(
                        custom_id="mgr_player_select",
                        placeholder="選擇玩家...",
                    )
                )
            ],
        )

    @commands.Cog.listener("on_dropdown")
    async def on_dropdown(self, inter: disnake.MessageInteraction) -> None:
        if inter.data.custom_id != "mgr_player_select":
            return

        if not self._check_guild(inter):
            return await inter.response.send_message("此指令僅限指定伺服器使用。", ephemeral=True)
        if not self._check_admin(inter):
            return await inter.response.send_message("此指令僅限管理員使用。", ephemeral=True)

        await inter.response.defer()

        target_user_id = inter.values[0]

        async with get_connection() as db:
            player_data = await self._fetch_player_data(db, target_user_id)

        if player_data is None:
            return await inter.edit_original_response(content="尚未加入遊戲", components=[])

        # Resolve display name from guild member if possible, fall back to user_id
        target_member = inter.guild.get_member(int(target_user_id)) if inter.guild else None
        display_name = target_member.display_name if target_member else target_user_id

        embed = build_manager_embed(display_name, player_data)
        components = build_manager_components(target_user_id)
        await inter.edit_original_response(embed=embed, components=components)


    @commands.Cog.listener("on_button_click")
    async def on_button_click(self, inter: disnake.MessageInteraction) -> None:
        custom_id: str = inter.data.custom_id
        if not custom_id.startswith("mgr_edit_"):
            return

        if not self._check_guild(inter):
            return await inter.response.send_message("此指令僅限指定伺服器使用。", ephemeral=True)
        if not self._check_admin(inter):
            return await inter.response.send_message("此指令僅限管理員使用。", ephemeral=True)

        # Parse: mgr_edit_{type}:{target_user_id}
        rest = custom_id[len("mgr_edit_"):]  # e.g. "gear:123456789"
        if ":" not in rest:
            return
        edit_type, target_user_id = rest.split(":", 1)

        if edit_type == "gear":
            modal = disnake.ui.Modal(
                title="編輯工具等級",
                custom_id=f"mgr_modal_gear:{target_user_id}",
                components=[
                    disnake.ui.TextInput(label="採集", custom_id="gear_gathering", style=disnake.TextInputStyle.short, required=True),
                    disnake.ui.TextInput(label="建設", custom_id="gear_building", style=disnake.TextInputStyle.short, required=True),
                    disnake.ui.TextInput(label="戰鬥", custom_id="gear_combat", style=disnake.TextInputStyle.short, required=True),
                    disnake.ui.TextInput(label="研究", custom_id="gear_research", style=disnake.TextInputStyle.short, required=True),
                ],
            )
        elif edit_type == "material":
            modal = disnake.ui.Modal(
                title="編輯素材數量",
                custom_id=f"mgr_modal_material:{target_user_id}",
                components=[
                    disnake.ui.TextInput(label="採集", custom_id="mat_gathering", style=disnake.TextInputStyle.short, required=True),
                    disnake.ui.TextInput(label="建設", custom_id="mat_building", style=disnake.TextInputStyle.short, required=True),
                    disnake.ui.TextInput(label="戰鬥", custom_id="mat_combat", style=disnake.TextInputStyle.short, required=True),
                    disnake.ui.TextInput(label="研究", custom_id="mat_research", style=disnake.TextInputStyle.short, required=True),
                    disnake.ui.TextInput(label="萬能", custom_id="mat_universal", style=disnake.TextInputStyle.short, required=True),
                ],
            )
        elif edit_type == "pity":
            modal = disnake.ui.Modal(
                title="編輯保底計數",
                custom_id=f"mgr_modal_pity:{target_user_id}",
                components=[
                    disnake.ui.TextInput(label="採集", custom_id="pity_gathering", style=disnake.TextInputStyle.short, required=True),
                    disnake.ui.TextInput(label="建設", custom_id="pity_building", style=disnake.TextInputStyle.short, required=True),
                    disnake.ui.TextInput(label="戰鬥", custom_id="pity_combat", style=disnake.TextInputStyle.short, required=True),
                    disnake.ui.TextInput(label="研究", custom_id="pity_research", style=disnake.TextInputStyle.short, required=True),
                ],
            )
        elif edit_type == "risky":
            modal = disnake.ui.Modal(
                title="編輯鐵齒失敗累積",
                custom_id=f"mgr_modal_risky:{target_user_id}",
                components=[
                    disnake.ui.TextInput(label="鐵齒失敗累積", custom_id="risky_failed_levels", style=disnake.TextInputStyle.short, required=True),
                ],
            )
        else:
            return

        await inter.response.send_modal(modal)

    @commands.Cog.listener("on_modal_submit")
    async def on_modal_submit(self, inter: disnake.ModalInteraction) -> None:
        custom_id: str = inter.custom_id
        if not custom_id.startswith("mgr_modal_"):
            return

        if not self._check_guild(inter):
            return await inter.response.send_message("此指令僅限指定伺服器使用。", ephemeral=True)
        if not self._check_admin(inter):
            return await inter.response.send_message("此指令僅限管理員使用。", ephemeral=True)

        await inter.response.defer(ephemeral=True)

        # Parse: mgr_modal_{type}:{target_user_id}
        rest = custom_id[len("mgr_modal_"):]  # e.g. "gear:123456789"
        if ":" not in rest:
            return
        modal_type, target_user_id = rest.split(":", 1)

        # Validate all inputs are non-negative integers
        text_values: dict = inter.text_values
        parsed: dict = {}
        for field_id, raw_value in text_values.items():
            try:
                value = int(raw_value)
            except ValueError:
                return await inter.edit_original_response(
                    content=f"輸入錯誤：「{raw_value}」不是有效整數，請輸入非負整數。"
                )
            if value < 0:
                return await inter.edit_original_response(
                    content=f"輸入錯誤：數值不可為負數（{field_id}={value}）。"
                )
            parsed[field_id] = value

        ts = datetime.now(timezone.utc)

        try:
            async with get_connection() as db:
                if modal_type == "gear":
                    for gear_type in ("gathering", "building", "combat", "research"):
                        await player_manager.set_gear_level(db, target_user_id, gear_type, parsed[f"gear_{gear_type}"], ts)
                elif modal_type == "material":
                    for gear_type in ("gathering", "building", "combat", "research"):
                        await player_manager.set_material(db, target_user_id, gear_type, parsed[f"mat_{gear_type}"], ts)
                    await player_manager.set_universal_material(db, target_user_id, parsed["mat_universal"], ts)
                elif modal_type == "pity":
                    for gear_type in ("gathering", "building", "combat", "research"):
                        await player_manager.set_pity(db, target_user_id, gear_type, parsed[f"pity_{gear_type}"], ts)
                elif modal_type == "risky":
                    await player_manager.set_risky_failed_levels(db, target_user_id, parsed["risky_failed_levels"], ts)
                else:
                    return
                await db.commit()
        except KeyError as exc:
            return await inter.edit_original_response(
                content=f"輸入錯誤：缺少必要欄位 {exc}，請重新操作。"
            )

        # Re-query player data and refresh panel
        async with get_connection() as db:
            player_data = await self._fetch_player_data(db, target_user_id)

        if player_data is None:
            return await inter.edit_original_response(content="尚未加入遊戲", components=[])

        target_member = inter.guild.get_member(int(target_user_id)) if inter.guild else None
        display_name = target_member.display_name if target_member else target_user_id

        embed = build_manager_embed(display_name, player_data)
        components = build_manager_components(target_user_id)
        await inter.edit_original_response(embed=embed, components=components)


def setup(bot: commands.Bot) -> None:
    bot.add_cog(PlayerManagerCog(bot))

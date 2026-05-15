import disnake
from disnake.ext import commands

from cogs.ui_renderer import build_manager_components, build_manager_embed
from core.config import get_discord_guild_id, is_admin
from database.schema import get_connection


class PlayerManagerCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _check_guild(self, inter) -> bool:
        return str(inter.guild_id) == get_discord_guild_id()

    def _check_admin(self, inter) -> bool:
        return is_admin(inter.user.id)

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
            async with db.execute(
                "SELECT gear_gathering, gear_building, gear_combat, gear_research, "
                "materials_gathering, materials_building, materials_combat, materials_research, "
                "pity_gathering, pity_building, pity_combat, pity_research, "
                "risky_failed_levels FROM players WHERE user_id=?",
                (target_user_id,),
            ) as cur:
                row = await cur.fetchone()

        if row is None:
            return await inter.edit_original_response(content="尚未加入遊戲", components=[])

        (
            gear_gathering, gear_building, gear_combat, gear_research,
            materials_gathering, materials_building, materials_combat, materials_research,
            pity_gathering, pity_building, pity_combat, pity_research,
            risky_failed_levels,
        ) = row

        player_data = {
            "gear_gathering": gear_gathering,
            "gear_building": gear_building,
            "gear_combat": gear_combat,
            "gear_research": gear_research,
            "materials_gathering": materials_gathering,
            "materials_building": materials_building,
            "materials_combat": materials_combat,
            "materials_research": materials_research,
            "pity_gathering": pity_gathering,
            "pity_building": pity_building,
            "pity_combat": pity_combat,
            "pity_research": pity_research,
            "risky_failed_levels": risky_failed_levels,
        }

        # Resolve display name from guild member if possible, fall back to user_id
        target_member = inter.guild.get_member(int(target_user_id)) if inter.guild else None
        display_name = target_member.display_name if target_member else target_user_id

        embed = build_manager_embed(display_name, player_data)
        components = build_manager_components(target_user_id)
        await inter.edit_original_response(embed=embed, components=components)


def setup(bot: commands.Bot) -> None:
    bot.add_cog(PlayerManagerCog(bot))

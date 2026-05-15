from datetime import datetime, timezone

import disnake
from disnake.ext import commands

from core.config import get_discord_guild_id, is_admin
from core.formula import ACTION_GEAR_COL, ACTION_MATERIAL_COL, VALID_ACTIONS
from database.schema import get_connection
from managers import player_manager

_GEAR_TYPES = list(VALID_ACTIONS)  # gathering, building, combat, research


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
        pass

    @manager.sub_command(name="player-view", description="查看玩家所有數據")
    async def player_view(
        self,
        inter: disnake.ApplicationCommandInteraction,
        user: disnake.Member,
    ) -> None:
        if not self._check_guild(inter):
            return await inter.response.send_message("此指令僅限指定伺服器使用。", ephemeral=True)
        if not self._check_admin(inter):
            return await inter.response.send_message("此指令僅限管理員使用。", ephemeral=True)
        await inter.response.defer(ephemeral=True)

        user_id = str(user.id)
        async with get_connection() as db:
            async with db.execute(
                "SELECT gear_gathering, gear_building, gear_combat, gear_research, "
                "materials_gathering, materials_building, materials_combat, materials_research, "
                "pity_gathering, pity_building, pity_combat, pity_research, "
                "risky_failed_levels FROM players WHERE user_id=?",
                (user_id,),
            ) as cur:
                row = await cur.fetchone()

        if row is None:
            return await inter.edit_original_response(content=f"玩家 {user.mention} 尚未加入遊戲。")

        (gl_g, gl_b, gl_c, gl_r,
         mat_g, mat_b, mat_c, mat_r,
         py_g, py_b, py_c, py_r,
         risky) = row

        embed = disnake.Embed(title=f"玩家數據：{user.display_name}", color=disnake.Color.blue())
        embed.add_field(
            name="工具等級",
            value=f"採集 {gl_g} ｜ 建設 {gl_b} ｜ 戰鬥 {gl_c} ｜ 研究 {gl_r}",
            inline=False,
        )
        embed.add_field(
            name="素材數量",
            value=f"採集 {mat_g} ｜ 建設 {mat_b} ｜ 戰鬥 {mat_c} ｜ 研究 {mat_r}",
            inline=False,
        )
        embed.add_field(
            name="保底計數",
            value=f"採集 {py_g} ｜ 建設 {py_b} ｜ 戰鬥 {py_c} ｜ 研究 {py_r}",
            inline=False,
        )
        embed.add_field(name="鐵齒失敗累積", value=str(risky), inline=False)
        await inter.edit_original_response(embed=embed)

    @manager.sub_command(name="player-gear", description="設定玩家工具等級")
    async def player_gear(
        self,
        inter: disnake.ApplicationCommandInteraction,
        user: disnake.Member,
        gear_type: str = commands.Param(choices=_GEAR_TYPES),
        level: int = commands.Param(ge=0),
    ) -> None:
        if not self._check_guild(inter):
            return await inter.response.send_message("此指令僅限指定伺服器使用。", ephemeral=True)
        if not self._check_admin(inter):
            return await inter.response.send_message("此指令僅限管理員使用。", ephemeral=True)
        if level < 0:
            return await inter.response.send_message("等級不能為負數。", ephemeral=True)
        await inter.response.defer(ephemeral=True)

        user_id = str(user.id)
        now = datetime.now(timezone.utc)
        async with get_connection() as db:
            old = await player_manager.get_gear_level(db, user_id, gear_type)
            if old == 0:
                async with db.execute("SELECT user_id FROM players WHERE user_id=?", (user_id,)) as cur:
                    if await cur.fetchone() is None:
                        return await inter.edit_original_response(content=f"玩家 {user.mention} 尚未加入遊戲。")
            await player_manager.set_gear_level(db, user_id, gear_type, level, now)
            await db.commit()

        await inter.edit_original_response(
            content=f"✅ {user.mention} `{gear_type}` 工具等級：{old} → {level}"
        )

    @manager.sub_command(name="player-material", description="設定玩家素材數量")
    async def player_material(
        self,
        inter: disnake.ApplicationCommandInteraction,
        user: disnake.Member,
        gear_type: str = commands.Param(choices=_GEAR_TYPES),
        amount: int = commands.Param(ge=0),
    ) -> None:
        if not self._check_guild(inter):
            return await inter.response.send_message("此指令僅限指定伺服器使用。", ephemeral=True)
        if not self._check_admin(inter):
            return await inter.response.send_message("此指令僅限管理員使用。", ephemeral=True)
        if amount < 0:
            return await inter.response.send_message("數量不能為負數。", ephemeral=True)
        await inter.response.defer(ephemeral=True)

        user_id = str(user.id)
        now = datetime.now(timezone.utc)
        col = ACTION_MATERIAL_COL[gear_type]
        async with get_connection() as db:
            async with db.execute(f"SELECT {col} FROM players WHERE user_id=?", (user_id,)) as cur:
                row = await cur.fetchone()
            if row is None:
                return await inter.edit_original_response(content=f"玩家 {user.mention} 尚未加入遊戲。")
            old = row[0]
            await player_manager.set_material(db, user_id, gear_type, amount, now)
            await db.commit()

        await inter.edit_original_response(
            content=f"✅ {user.mention} `{gear_type}` 素材數量：{old} → {amount}"
        )

    @manager.sub_command(name="player-pity", description="設定玩家保底計數")
    async def player_pity(
        self,
        inter: disnake.ApplicationCommandInteraction,
        user: disnake.Member,
        gear_type: str = commands.Param(choices=_GEAR_TYPES),
        count: int = commands.Param(ge=0),
    ) -> None:
        if not self._check_guild(inter):
            return await inter.response.send_message("此指令僅限指定伺服器使用。", ephemeral=True)
        if not self._check_admin(inter):
            return await inter.response.send_message("此指令僅限管理員使用。", ephemeral=True)
        if count < 0:
            return await inter.response.send_message("保底計數不能為負數。", ephemeral=True)
        await inter.response.defer(ephemeral=True)

        user_id = str(user.id)
        now = datetime.now(timezone.utc)
        async with get_connection() as db:
            old = await player_manager.get_pity(db, user_id, gear_type)
            async with db.execute("SELECT user_id FROM players WHERE user_id=?", (user_id,)) as cur:
                if await cur.fetchone() is None:
                    return await inter.edit_original_response(content=f"玩家 {user.mention} 尚未加入遊戲。")
            await player_manager.set_pity(db, user_id, gear_type, count, now)
            await db.commit()

        await inter.edit_original_response(
            content=f"✅ {user.mention} `{gear_type}` 保底計數：{old} → {count}"
        )

    @manager.sub_command(name="player-risky", description="設定玩家鐵齒失敗累積值")
    async def player_risky(
        self,
        inter: disnake.ApplicationCommandInteraction,
        user: disnake.Member,
        value: int = commands.Param(ge=0),
    ) -> None:
        if not self._check_guild(inter):
            return await inter.response.send_message("此指令僅限指定伺服器使用。", ephemeral=True)
        if not self._check_admin(inter):
            return await inter.response.send_message("此指令僅限管理員使用。", ephemeral=True)
        if value < 0:
            return await inter.response.send_message("鐵齒失敗累積值不能為負數。", ephemeral=True)
        await inter.response.defer(ephemeral=True)

        user_id = str(user.id)
        now = datetime.now(timezone.utc)
        async with get_connection() as db:
            async with db.execute("SELECT risky_failed_levels FROM players WHERE user_id=?", (user_id,)) as cur:
                row = await cur.fetchone()
            if row is None:
                return await inter.edit_original_response(content=f"玩家 {user.mention} 尚未加入遊戲。")
            old = row[0]
            await player_manager.set_risky_failed_levels(db, user_id, value, now)
            await db.commit()

        await inter.edit_original_response(
            content=f"✅ {user.mention} 鐵齒失敗累積：{old} → {value}"
        )


def setup(bot: commands.Bot) -> None:
    bot.add_cog(PlayerManagerCog(bot))

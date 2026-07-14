from datetime import datetime, timezone

import disnake
from disnake.ext import commands

from core import notification
from core.config import get_discord_guild_id, get_env_int
from core.utils import parse_dt
from database.schema import get_connection
from managers import resource_manager, trial_manager

RESOURCE_CHOICES = {"食物": "food", "木頭": "wood", "知識": "knowledge"}
RESOURCE_LABELS = {"food": "食物", "wood": "木頭", "knowledge": "知識"}


class TrialCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _check_guild(self, inter) -> bool:
        return str(inter.guild_id) == get_discord_guild_id()

    @commands.slash_command(name="idlevillage-trial", description="開啟村莊試煉")
    async def idlevillage_trial(
        self,
        inter: disnake.ApplicationCommandInteraction,
        resource: str = commands.Param(choices=RESOURCE_CHOICES, description="花費的資源類型"),
        target: int = commands.Param(description="試煉目標值（須為 1000 的整數倍）"),
    ) -> None:
        if not self._check_guild(inter):
            return await inter.response.send_message(
                "此指令僅限指定伺服器使用。", ephemeral=True
            )

        step = get_env_int("TRIAL_TARGET_STEP")
        if target < step or target % step != 0:
            return await inter.response.send_message(
                f"目標值必須為 {step} 的整數倍。", ephemeral=True
            )

        await inter.response.defer(ephemeral=True)
        now = datetime.now(timezone.utc)

        async with get_connection() as db:
            info = await trial_manager.get_trial_info(db)
            if info.get("is_active"):
                return await inter.edit_original_response(
                    content="目前已有試煉進行中，無法開啟新試煉。"
                )

            ended_at_str = info.get("ended_at")
            if ended_at_str:
                cooldown = get_env_int("TRIAL_COOLDOWN_SECONDS")
                ended_at = parse_dt(ended_at_str)
                elapsed = (now - ended_at).total_seconds()
                if elapsed < cooldown:
                    cooldown_end_unix = int(ended_at.timestamp()) + cooldown
                    return await inter.edit_original_response(
                        content=f"試煉冷卻中，<t:{cooldown_end_unix}:R> 才能再次開啟試煉。"
                    )

            if not await resource_manager.can_afford(db, resource, target):
                balance = await resource_manager.balance(db, resource)
                r_label = RESOURCE_LABELS.get(resource, resource)
                return await inter.edit_original_response(
                    content=f"村莊{r_label}不足，目前僅有 {balance} 個，需要 {target} 個。"
                )

            try:
                await trial_manager.start_trial(db, resource, target, str(inter.user.id), now)
            except ValueError:
                return await inter.edit_original_response(content="開啟試煉失敗，請重新嘗試。")
            await db.commit()

        await inter.edit_original_response(content="✅ 試煉已開始！")

        divisor = get_env_int("TRIAL_REWARD_DIVISOR")
        duration = get_env_int("TRIAL_DURATION_SECONDS")
        trial_start_event = {
            "type": "trial_start",
            "user_id": str(inter.user.id),
            "resource_type": resource,
            "target": target,
            "reward_pool": target // divisor,
            "deadline_unix": int(now.timestamp()) + duration,
        }
        await notification.dispatch_events(self.bot, [trial_start_event])


def setup(bot: commands.Bot) -> None:
    bot.add_cog(TrialCog(bot))

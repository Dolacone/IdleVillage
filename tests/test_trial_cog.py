"""
Tests for cogs.trial_cog — /idlevillage-trial slash command.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from tests.support import ALL_TEST_ENV, DatabaseTestCase
from database.schema import get_connection


def _make_inter(user_id=111222333):
    inter = MagicMock()
    inter.guild_id = int(ALL_TEST_ENV["DISCORD_GUILD_ID"])
    inter.user.id = user_id
    inter.response.send_message = AsyncMock()
    inter.response.defer = AsyncMock()
    inter.edit_original_response = AsyncMock()
    return inter


class TestTrialCommandGuildCheck(DatabaseTestCase):
    async def test_rejects_when_not_in_configured_guild(self):
        from cogs.trial_cog import TrialCog

        inter = _make_inter()
        inter.guild_id = 999999999999999999
        cog = TrialCog(bot=MagicMock())

        await TrialCog.idlevillage_trial.callback(cog, inter, resource="food", target=1000)

        inter.response.send_message.assert_awaited_once()
        self.assertIn("指定伺服器", inter.response.send_message.call_args.args[0])
        inter.response.defer.assert_not_awaited()


class TestTrialCommandValidation(DatabaseTestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        async with get_connection() as db:
            await db.execute("UPDATE village_resources SET amount=5000 WHERE resource_type='food'")
            await db.commit()

    async def test_rejects_target_not_multiple_of_step(self):
        from cogs.trial_cog import TrialCog

        inter = _make_inter()
        cog = TrialCog(bot=MagicMock())

        await TrialCog.idlevillage_trial.callback(cog, inter, resource="food", target=1500)

        inter.response.send_message.assert_awaited_once()
        self.assertIn("1000", inter.response.send_message.call_args.args[0])
        inter.response.defer.assert_not_awaited()
        row = await self.fetchone("SELECT amount FROM village_resources WHERE resource_type='food'")
        self.assertEqual(row[0], 5000)

    async def test_rejects_when_trial_already_active(self):
        from cogs.trial_cog import TrialCog

        now = datetime.now(timezone.utc)
        async with get_connection() as db:
            await db.execute(
                """UPDATE trial_state SET
                   is_active=1, resource_type='wood', target=2000, progress=0,
                   started_at=?, updated_at=? WHERE id=1""",
                (now.isoformat(), now.isoformat()),
            )
            await db.commit()

        inter = _make_inter()
        cog = TrialCog(bot=MagicMock())
        await TrialCog.idlevillage_trial.callback(cog, inter, resource="food", target=1000)

        inter.edit_original_response.assert_awaited_once()
        self.assertIn("已有試煉進行中", inter.edit_original_response.call_args.kwargs["content"])
        row = await self.fetchone("SELECT amount FROM village_resources WHERE resource_type='food'")
        self.assertEqual(row[0], 5000)

    async def test_rejects_when_cooldown_not_elapsed(self):
        from cogs.trial_cog import TrialCog

        now = datetime.now(timezone.utc)
        async with get_connection() as db:
            await db.execute(
                "UPDATE trial_state SET is_active=0, ended_at=? WHERE id=1",
                (now.isoformat(),),
            )
            await db.commit()

        inter = _make_inter()
        cog = TrialCog(bot=MagicMock())
        await TrialCog.idlevillage_trial.callback(cog, inter, resource="food", target=1000)

        inter.edit_original_response.assert_awaited_once()
        self.assertIn("冷卻中", inter.edit_original_response.call_args.kwargs["content"])
        row = await self.fetchone("SELECT amount FROM village_resources WHERE resource_type='food'")
        self.assertEqual(row[0], 5000)

    async def test_rejects_when_resource_insufficient(self):
        from cogs.trial_cog import TrialCog

        inter = _make_inter()
        cog = TrialCog(bot=MagicMock())
        await TrialCog.idlevillage_trial.callback(cog, inter, resource="food", target=10000)

        inter.edit_original_response.assert_awaited_once()
        message = inter.edit_original_response.call_args.kwargs["content"]
        self.assertIn("不足", message)
        self.assertIn("5000", message)
        row = await self.fetchone("SELECT amount FROM village_resources WHERE resource_type='food'")
        self.assertEqual(row[0], 5000)


class TestTrialCommandSuccess(DatabaseTestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        async with get_connection() as db:
            await db.execute("UPDATE village_resources SET amount=5000 WHERE resource_type='food'")
            await db.commit()

    async def test_success_opens_trial_and_dispatches_start_notification(self):
        from cogs.trial_cog import TrialCog

        inter = _make_inter(user_id=555)
        cog = TrialCog(bot=MagicMock())

        with patch("cogs.trial_cog.notification.dispatch_events", new=AsyncMock()) as dispatch:
            await TrialCog.idlevillage_trial.callback(cog, inter, resource="food", target=3000)

        inter.edit_original_response.assert_any_await(content="✅ 試煉已開始！")
        row = await self.fetchone("SELECT amount FROM village_resources WHERE resource_type='food'")
        self.assertEqual(row[0], 2000)
        row = await self.fetchone("SELECT is_active, target, resource_type FROM trial_state WHERE id=1")
        self.assertEqual(row, (1, 3000, "food"))

        dispatch.assert_awaited_once()
        _, events = dispatch.call_args.args
        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(event["type"], "trial_start")
        self.assertEqual(event["user_id"], "555")
        self.assertEqual(event["resource_type"], "food")
        self.assertEqual(event["target"], 3000)
        self.assertEqual(event["reward_pool"], 30)

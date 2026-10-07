"""
tests/test_discord_commands.py — focused tests for Discord command routing and UI rendering.
"""

import sys
import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

# Support module must be loaded before any src imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from tests.support import ALL_TEST_ENV, DatabaseTestCase
from database import schema


class TestGuildCheck(unittest.TestCase):
    """Guild enforcement: commands reject interactions outside DISCORD_GUILD_ID."""

    def setUp(self):
        for k, v in ALL_TEST_ENV.items():
            os.environ[k] = v

    def _make_inter(self, guild_id: str):
        inter = MagicMock()
        inter.guild_id = guild_id
        return inter

    def _check_guild(self, inter) -> bool:
        from core.config import get_discord_guild_id
        return str(inter.guild_id) == get_discord_guild_id()

    def test_correct_guild_accepted(self):
        inter = self._make_inter(ALL_TEST_ENV["DISCORD_GUILD_ID"])
        self.assertTrue(self._check_guild(inter))

    def test_wrong_guild_rejected(self):
        inter = self._make_inter("999999999999999999")
        self.assertFalse(self._check_guild(inter))

    def test_empty_guild_rejected(self):
        inter = self._make_inter("")
        self.assertFalse(self._check_guild(inter))


class TestNewPlayerCreation(DatabaseTestCase):
    """New player is created with 0 AP (ap_full_time far in the future)."""

    async def asyncSetUp(self):
        await super().asyncSetUp()
        from database.schema import get_connection
        from managers import player_manager

        self.get_connection = get_connection
        self.player_manager = player_manager

    async def test_new_player_has_zero_ap(self):
        from core.config import get_env_int
        from core.utils import dt_str
        from database.schema import get_connection

        user_id = "new_player_001"
        now = datetime.now(timezone.utc)
        ap_cap = get_env_int("AP_CAP")
        recovery_mins = get_env_int("AP_RECOVERY_MINUTES")
        ap_full_time = now + timedelta(minutes=ap_cap * recovery_mins)

        async with get_connection() as db:
            await db.execute(
                """INSERT OR IGNORE INTO players
                   (user_id, created_at, updated_at, ap_full_time)
                   VALUES (?, ?, ?, ?)""",
                (user_id, dt_str(now), dt_str(now), dt_str(ap_full_time)),
            )
            await db.commit()
            ap = await self.player_manager.get_ap(db, user_id, now)

        self.assertEqual(ap, 0, "New player should start with 0 AP")

    async def test_new_player_ap_full_after_recovery(self):
        from core.config import get_env_int
        from core.utils import dt_str
        from database.schema import get_connection

        user_id = "new_player_002"
        now = datetime.now(timezone.utc)
        ap_cap = get_env_int("AP_CAP")
        recovery_mins = get_env_int("AP_RECOVERY_MINUTES")
        ap_full_time = now + timedelta(minutes=ap_cap * recovery_mins)

        async with get_connection() as db:
            await db.execute(
                """INSERT OR IGNORE INTO players
                   (user_id, created_at, updated_at, ap_full_time)
                   VALUES (?, ?, ?, ?)""",
                (user_id, dt_str(now), dt_str(now), dt_str(ap_full_time)),
            )
            await db.commit()
            future = ap_full_time + timedelta(seconds=1)
            ap = await self.player_manager.get_ap(db, user_id, future)

        self.assertEqual(ap, ap_cap, "Player should have full AP after recovery period")

    async def test_concurrent_player_creation_is_idempotent(self):
        from core.utils import dt_str
        from core.config import get_env_int
        from database.schema import get_connection

        user_id = "new_player_003"
        now = datetime.now(timezone.utc)
        ap_cap = get_env_int("AP_CAP")
        recovery_mins = get_env_int("AP_RECOVERY_MINUTES")
        ap_full_time = now + timedelta(minutes=ap_cap * recovery_mins)

        async with get_connection() as db:
            # INSERT OR IGNORE twice — second should be silently ignored
            for _ in range(2):
                await db.execute(
                    """INSERT OR IGNORE INTO players
                       (user_id, created_at, updated_at, ap_full_time)
                       VALUES (?, ?, ?, ?)""",
                    (user_id, dt_str(now), dt_str(now), dt_str(ap_full_time)),
                )
            await db.commit()

            async with db.execute(
                "SELECT COUNT(*) FROM players WHERE user_id=?", (user_id,)
            ) as cur:
                count = (await cur.fetchone())[0]

        self.assertEqual(count, 1, "Duplicate INSERT OR IGNORE should result in exactly 1 row")


class TestRenderMainTrialWiring(DatabaseTestCase):
    async def test_render_main_shows_trial_progress_and_personal_contribution(self):
        from cogs.actions import ActionsCog
        from database.schema import get_connection

        user_id = "987654321"
        now = datetime.now(timezone.utc)
        async with get_connection() as db:
            await db.execute(
                "INSERT INTO players (user_id, created_at, updated_at, ap_full_time) VALUES (?, ?, ?, ?)",
                (user_id, now.isoformat(), now.isoformat(), now.isoformat()),
            )
            await db.execute(
                """UPDATE trial_state SET
                   is_active=1, resource_type='food', target=1000, progress=300,
                   started_at=?, updated_at=?
                   WHERE id=1""",
                (now.isoformat(), now.isoformat()),
            )
            await db.execute(
                "INSERT INTO trial_contributions (user_id, contribution, updated_at) VALUES (?, 77, ?)",
                (user_id, now.isoformat()),
            )
            await db.commit()

        inter = MagicMock()
        inter.guild_id = int(ALL_TEST_ENV["DISCORD_GUILD_ID"])
        inter.user.id = int(user_id)
        inter.edit_original_response = AsyncMock()

        cog = ActionsCog(bot=MagicMock())
        with patch("cogs.actions.notification.dispatch_events", new=AsyncMock()):
            await cog._render_main(inter)

        embed = inter.edit_original_response.call_args.kwargs["embed"]
        self.assertIn("🏆 試煉", embed.description)
        self.assertIn("300 / 1000", embed.description)
        self.assertIn("🏆 試煉貢獻：77", embed.description)


class TestTrialStartButton(DatabaseTestCase):
    TRIAL_AMOUNT = 50000

    def _make_button_inter(self, custom_id="open_trial_start", user_id=111222333):
        inter = MagicMock()
        inter.guild_id = int(ALL_TEST_ENV["DISCORD_GUILD_ID"])
        inter.component.custom_id = custom_id
        inter.user.id = user_id
        inter.response.defer = AsyncMock()
        inter.edit_original_response = AsyncMock()
        return inter

    def _make_dropdown_inter(self, value, user_id=111222333):
        inter = self._make_button_inter("trial_target_select", user_id)
        inter.values = [value]
        return inter

    def _dispatched_trial_start_events(self, dispatch):
        events = []
        for call in dispatch.call_args_list:
            events.extend(e for e in call.args[1] if e.get("type") == "trial_start")
        return events

    async def _set_resource(self, resource_type, amount):
        async with schema.get_connection() as db:
            await db.execute(
                "UPDATE village_resources SET amount=? WHERE resource_type=?",
                (amount, resource_type),
            )
            await db.commit()

    async def test_open_only_shows_targets_without_spending_or_notifying(self):
        from cogs.actions import ActionsCog

        await self._set_resource("wood", 60000)
        inter = self._make_button_inter()
        with patch("cogs.actions.notification.dispatch_events", new=AsyncMock()) as dispatch:
            await ActionsCog(bot=MagicMock()).on_button_click(inter)

        components = inter.edit_original_response.call_args.kwargs["components"]
        self.assertEqual(components[0].children[0].custom_id, "trial_target_select")
        self.assertEqual(self._dispatched_trial_start_events(dispatch), [])
        row = await self.fetchone("SELECT is_active FROM trial_state WHERE id=1")
        self.assertEqual(row[0], 0)
        row = await self.fetchone("SELECT amount FROM village_resources WHERE resource_type='wood'")
        self.assertEqual(row[0], 60000)

    async def test_open_active_returns_main_without_select(self):
        from cogs.actions import ActionsCog

        now = datetime.now(timezone.utc)
        async with schema.get_connection() as db:
            await db.execute(
                "UPDATE trial_state SET is_active=1, started_at=?, updated_at=? WHERE id=1",
                (now.isoformat(), now.isoformat()),
            )
            await db.commit()
        inter = self._make_button_inter()
        with patch("cogs.actions.notification.dispatch_events", new=AsyncMock()):
            await ActionsCog(bot=MagicMock()).on_button_click(inter)
        embed = inter.edit_original_response.call_args.kwargs["embed"]
        self.assertIn("⚠️ 試煉已由其他玩家開啟。", embed.description)
        self.assertFalse(any(c.custom_id == "trial_target_select" for row in inter.edit_original_response.call_args.kwargs["components"] for c in row.children))

    async def test_open_cooldown_returns_main_without_select(self):
        from cogs.actions import ActionsCog

        now = datetime.now(timezone.utc)
        async with schema.get_connection() as db:
            await db.execute(
                "UPDATE trial_state SET is_active=0, ended_at=? WHERE id=1", (now.isoformat(),)
            )
            await db.commit()
        inter = self._make_button_inter()
        with patch("cogs.actions.notification.dispatch_events", new=AsyncMock()):
            await ActionsCog(bot=MagicMock()).on_button_click(inter)
        embed = inter.edit_original_response.call_args.kwargs["embed"]
        self.assertIn("⚠️ 試煉仍在冷卻中。", embed.description)
        self.assertFalse(any(c.custom_id == "trial_target_select" for row in inter.edit_original_response.call_args.kwargs["components"] for c in row.children))

    async def test_open_without_legal_target_returns_main_without_empty_select(self):
        from cogs.actions import ActionsCog

        await self._set_resource("food", 34999)
        inter = self._make_button_inter()
        with patch("cogs.actions.notification.dispatch_events", new=AsyncMock()):
            await ActionsCog(bot=MagicMock()).on_button_click(inter)
        embed = inter.edit_original_response.call_args.kwargs["embed"]
        self.assertIn("⚠️ 村莊資源不足，尚無法開啟試煉。", embed.description)
        self.assertFalse(any(c.custom_id == "trial_target_select" for row in inter.edit_original_response.call_args.kwargs["components"] for c in row.children))

    async def test_page_rereads_resources_clamps_page_and_does_not_spend(self):
        from cogs.actions import ActionsCog

        await self._set_resource("wood", 660000)
        open_inter = self._make_button_inter()
        with patch("cogs.actions.notification.dispatch_events", new=AsyncMock()):
            await ActionsCog(bot=MagicMock()).on_button_click(open_inter)
        await self._set_resource("wood", 35000)
        page_inter = self._make_button_inter("trial_target_page:999")
        with patch("cogs.actions.notification.dispatch_events", new=AsyncMock()) as dispatch:
            await ActionsCog(bot=MagicMock()).on_button_click(page_inter)
        options = page_inter.edit_original_response.call_args.kwargs["components"][0].children[0].options
        self.assertEqual([option.value for option in options], ["25000"])
        self.assertEqual(self._dispatched_trial_start_events(dispatch), [])
        row = await self.fetchone("SELECT amount FROM village_resources WHERE resource_type='wood'")
        self.assertEqual(row[0], 35000)

    async def test_select_success_spends_stores_target_and_dispatches_dynamic_event(self):
        from cogs.actions import ActionsCog

        await self._set_resource("wood", 160000)
        started_before = int(datetime.now(timezone.utc).timestamp())
        inter = self._make_dropdown_inter("150000")
        with patch("cogs.actions.notification.dispatch_events", new=AsyncMock()) as dispatch:
            await ActionsCog(bot=MagicMock()).on_dropdown(inter)
        row = await self.fetchone("SELECT is_active, target, resource_type FROM trial_state WHERE id=1")
        self.assertEqual(row, (1, 150000, "wood"))
        row = await self.fetchone("SELECT amount FROM village_resources WHERE resource_type='wood'")
        self.assertEqual(row[0], 10000)
        events = self._dispatched_trial_start_events(dispatch)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["target"], 150000)
        self.assertEqual(events[0]["reward_pool"], 1500)
        self.assertGreaterEqual(events[0]["deadline_unix"], started_before + 43200)

    async def test_select_non_integer_or_non_step_target_is_invalid_without_notification(self):
        from cogs.actions import ActionsCog

        await self._set_resource("wood", 60000)
        for value in ("not-an-integer", "12500"):
            with self.subTest(value=value):
                inter = self._make_dropdown_inter(value)
                with patch("cogs.actions.notification.dispatch_events", new=AsyncMock()) as dispatch:
                    await ActionsCog(bot=MagicMock()).on_dropdown(inter)
                embed = inter.edit_original_response.call_args.kwargs["embed"]
                self.assertIn("⚠️ 試煉目標無效，請重新選擇。", embed.description)
                self.assertEqual(self._dispatched_trial_start_events(dispatch), [])
        row = await self.fetchone("SELECT is_active FROM trial_state WHERE id=1")
        self.assertEqual(row[0], 0)

    async def test_select_stale_target_is_invalid_without_notification(self):
        from cogs.actions import ActionsCog

        await self._set_resource("wood", 60000)
        inter = self._make_dropdown_inter("50000")
        await self._set_resource("wood", 10000)
        with patch("cogs.actions.notification.dispatch_events", new=AsyncMock()) as dispatch:
            await ActionsCog(bot=MagicMock()).on_dropdown(inter)
        embed = inter.edit_original_response.call_args.kwargs["embed"]
        self.assertIn("⚠️ 資源已變動，所選目標已無法支付。", embed.description)
        self.assertEqual(self._dispatched_trial_start_events(dispatch), [])


class TestAnnouncementCommand(DatabaseTestCase):
    async def test_announcement_command_stores_sent_dashboard_reference(self):
        from cogs.general import GeneralCog
        from database.schema import get_connection

        sent_message = MagicMock()
        sent_message.id = 456
        inter = MagicMock()
        inter.guild_id = int(ALL_TEST_ENV["DISCORD_GUILD_ID"])
        inter.channel_id = 123
        inter.user.id = int(ALL_TEST_ENV["ADMIN_IDS"].split(",")[0])
        inter.response.defer = AsyncMock()
        inter.channel.send = AsyncMock(return_value=sent_message)
        inter.edit_original_response = AsyncMock()

        cog = GeneralCog(bot=MagicMock())
        await GeneralCog.announcement.callback(cog, inter)

        async with get_connection() as db:
            async with db.execute(
                "SELECT announcement_channel_id, dashboard_channel_id, dashboard_message_id FROM village_state WHERE id=1"
            ) as cur:
                row = await cur.fetchone()

        self.assertEqual(row, ("123", "123", "456"))

    async def test_announcement_dashboard_embed_shows_active_trial(self):
        from cogs.general import GeneralCog
        from database.schema import get_connection

        async with get_connection() as db:
            await db.execute(
                """UPDATE trial_state SET
                   is_active=1, resource_type='knowledge', target=2000, progress=500,
                   started_at=?, updated_at=?
                   WHERE id=1""",
                (datetime.now(timezone.utc).isoformat(), datetime.now(timezone.utc).isoformat()),
            )
            await db.commit()

        inter = MagicMock()
        inter.guild_id = int(ALL_TEST_ENV["DISCORD_GUILD_ID"])
        inter.channel_id = 123
        inter.user.id = int(ALL_TEST_ENV["ADMIN_IDS"].split(",")[0])
        inter.response.defer = AsyncMock()
        inter.channel.send = AsyncMock(return_value=MagicMock(id=456))
        inter.edit_original_response = AsyncMock()

        cog = GeneralCog(bot=MagicMock())
        await GeneralCog.announcement.callback(cog, inter)

        embed = inter.channel.send.call_args.kwargs["embed"]
        self.assertIn("🏆 試煉", embed.description)
        self.assertIn("500 / 2000", embed.description)


class TestManageCommand(DatabaseTestCase):
    async def test_manage_command_does_not_create_dashboard_message(self):
        from cogs.general import GeneralCog

        inter = MagicMock()
        inter.guild_id = int(ALL_TEST_ENV["DISCORD_GUILD_ID"])
        inter.channel_id = 123
        inter.user.id = int(ALL_TEST_ENV["ADMIN_IDS"].split(",")[0])
        inter.response.defer = AsyncMock()
        inter.channel.send = AsyncMock()
        inter.edit_original_response = AsyncMock()

        cog = GeneralCog(bot=MagicMock())
        await GeneralCog.manage.callback(cog, inter)

        inter.channel.send.assert_not_called()
        inter.edit_original_response.assert_awaited_once()


class TestUIBuildingTargets(unittest.TestCase):
    """UI_BUILDING_TARGETS must not include research_lab."""

    def test_research_lab_excluded(self):
        from cogs.ui_renderer import UI_BUILDING_TARGETS
        self.assertNotIn("research_lab", UI_BUILDING_TARGETS)

    def test_all_three_targets_present(self):
        from cogs.ui_renderer import UI_BUILDING_TARGETS
        self.assertIn("gathering_field", UI_BUILDING_TARGETS)
        self.assertIn("workshop", UI_BUILDING_TARGETS)
        self.assertIn("hunting_ground", UI_BUILDING_TARGETS)

    def test_forged_research_lab_rejected(self):
        """Forged confirm_action:building:research_lab should be rejected at UI level."""
        from cogs.ui_renderer import UI_BUILDING_TARGETS
        forged_target = "research_lab"
        self.assertNotIn(forged_target, UI_BUILDING_TARGETS)


class TestConfirmActionCustomIdParsing(unittest.TestCase):
    """confirm_action:* custom_id parsing logic."""

    def _parse(self, cid: str):
        parts = cid.split(":")
        if len(parts) < 2:
            return None, None
        action = parts[1]
        target = parts[2] if len(parts) >= 3 else None
        return action, target

    def test_gathering(self):
        action, target = self._parse("confirm_action:gathering")
        self.assertEqual(action, "gathering")
        self.assertIsNone(target)

    def test_building_with_target(self):
        action, target = self._parse("confirm_action:building:workshop")
        self.assertEqual(action, "building")
        self.assertEqual(target, "workshop")

    def test_research(self):
        action, target = self._parse("confirm_action:research")
        self.assertEqual(action, "research")
        self.assertIsNone(target)


class TestRendererVillageEmbed(unittest.TestCase):
    """build_village_embed produces embeds with expected content."""

    def setUp(self):
        for k, v in ALL_TEST_ENV.items():
            os.environ[k] = v

    def _make_stage_data(self):
        now = datetime.now(timezone.utc).isoformat()
        return {
            "stages_cleared": 3,
            "current_stage_type": "combat",
            "current_stage_progress": 50,
            "current_stage_target": 100,
            "stage_started_at": now,
            "updated_at": now,
            "overtime_notified": 0,
        }

    def test_embed_contains_stage_info(self):
        from cogs.ui_renderer import build_village_embed
        resources = {"food": 100, "wood": 200, "knowledge": 50}
        buildings = {}
        action_counts = [("gathering", None, 3), ("combat", None, 1)]
        embed = build_village_embed(self._make_stage_data(), resources, buildings, action_counts)
        desc = embed.description
        self.assertIn("📋 關卡 3: 戰鬥", desc)
        self.assertIn("⏰ 期限:", desc)
        self.assertIn("50 / 100", desc)

    def test_embed_contains_resource_values(self):
        from cogs.ui_renderer import build_village_embed
        resources = {"food": 999, "wood": 888, "knowledge": 777}
        embed = build_village_embed(self._make_stage_data(), resources, {}, [])
        desc = embed.description
        self.assertIn("公用資源", desc)
        self.assertIn("999", desc)
        self.assertIn("888", desc)
        self.assertIn("777", desc)

    def test_building_rows_are_plain_percentage_only(self):
        from cogs.ui_renderer import build_village_embed

        buildings = {
            "gathering_field": {"level": 1, "xp_progress": 50},
            "workshop": {"level": 1, "xp_progress": 25},
            "hunting_ground": {"level": 1, "xp_progress": 0},
            "research_lab": {"level": 1, "xp_progress": 100},
        }
        embed = build_village_embed(self._make_stage_data(), {}, buildings, [])
        desc = embed.description

        self.assertIn("公用設施 (等級上限：Lv1)", desc)
        self.assertIn("🌾 採集場 Lv1 (2%)", desc)
        self.assertNotIn("50/", desc)
        self.assertNotIn("Village Buildings", desc)

    def test_capped_building_row_shows_actual_xp_percentage(self):
        from cogs.ui_renderer import build_village_embed

        buildings = {
            "gathering_field": {"level": 1, "xp_progress": 1000},
            "workshop": {"level": 0, "xp_progress": 0},
            "hunting_ground": {"level": 1, "xp_progress": 2000},
        }
        embed = build_village_embed(self._make_stage_data(), {}, buildings, [])
        desc = embed.description

        self.assertIn("🌾 採集場 Lv1 (50%)", desc)
        self.assertIn("🔨 加工廠 Lv0 (0%)", desc)
        self.assertIn("⚔️ 狩獵場 Lv1 (100%)", desc)

    def test_capped_building_at_full_xp_shows_100_percent(self):
        from cogs.ui_renderer import build_village_embed

        xp_per = int(ALL_TEST_ENV["BUILDING_XP_PER_LEVEL"])
        buildings = {
            "gathering_field": {"level": 1, "xp_progress": 2 * xp_per},
        }
        embed = build_village_embed(self._make_stage_data(), {}, buildings, [])

        self.assertIn("🌾 採集場 Lv1 (100%)", embed.description)

    def test_embed_action_counts_sorted_desc(self):
        from cogs.ui_renderer import build_village_embed
        action_counts = [("gathering", None, 1), ("combat", None, 5)]
        embed = build_village_embed(self._make_stage_data(), {}, {}, action_counts)
        desc = embed.description
        combat_idx = desc.index("戰鬥")
        gather_idx = desc.index("採集")
        self.assertLess(combat_idx, gather_idx, "Higher count action should appear first")

    def _make_trial_data(self, is_active=1):
        now = datetime.now(timezone.utc).isoformat()
        return {
            "is_active": is_active,
            "resource_type": "wood",
            "target": 5000,
            "progress": 2000,
            "started_at": now,
            "ended_at": None,
        }

    def test_embed_shows_trial_line_when_active(self):
        from cogs.ui_renderer import build_village_embed
        embed = build_village_embed(
            self._make_stage_data(), {}, {}, [], self._make_trial_data()
        )
        desc = embed.description
        self.assertIn("🏆 試煉 2000 / 5000 (40%)", desc)
        self.assertNotIn("木頭", desc)

    def test_embed_shows_insufficient_resources_when_inactive_and_no_resource_enough(self):
        from cogs.ui_renderer import build_village_embed
        embed = build_village_embed(
            self._make_stage_data(), {}, {}, [], self._make_trial_data(is_active=0)
        )
        self.assertIn("🏆 試煉 ⚠️ 資源不足，尚無法開啟", embed.description)

    def test_embed_shows_insufficient_resources_when_trial_data_not_provided(self):
        from cogs.ui_renderer import build_village_embed
        embed = build_village_embed(self._make_stage_data(), {}, {}, [])
        self.assertIn("🏆 試煉 ⚠️ 資源不足，尚無法開啟", embed.description)

    def test_embed_shows_openable_when_inactive_and_resource_enough(self):
        from cogs.ui_renderer import build_village_embed
        trial_amount = 35000
        resources = {"food": trial_amount, "wood": 0, "knowledge": 0}
        embed = build_village_embed(
            self._make_stage_data(), resources, {}, [], self._make_trial_data(is_active=0)
        )
        self.assertIn("🏆 試煉 ✅ 可開啟試煉", embed.description)

    def test_trial_status_respects_reserved_resource_boundary(self):
        from cogs.ui_renderer import build_village_embed

        below = build_village_embed(
            self._make_stage_data(), {"food": 34999}, {}, [], self._make_trial_data(is_active=0)
        )
        at_boundary = build_village_embed(
            self._make_stage_data(), {"food": 35000}, {}, [], self._make_trial_data(is_active=0)
        )
        self.assertIn("🏆 試煉 ⚠️ 資源不足，尚無法開啟", below.description)
        self.assertIn("🏆 試煉 ✅ 可開啟試煉", at_boundary.description)

    def test_embed_shows_cooldown_deadline_when_recently_ended(self):
        from cogs.ui_renderer import build_village_embed
        now = datetime.now(timezone.utc)
        cooldown = int(ALL_TEST_ENV["TRIAL_COOLDOWN_SECONDS"])
        ended_at = now - timedelta(seconds=cooldown - 100)
        trial_data = self._make_trial_data(is_active=0)
        trial_data["ended_at"] = ended_at.isoformat()
        embed = build_village_embed(self._make_stage_data(), {}, {}, [], trial_data)
        deadline_unix = int(ended_at.timestamp()) + cooldown
        self.assertIn(f"🏆 試煉 ⏳ 可於 <t:{deadline_unix}:t> 後開啟", embed.description)

    def test_embed_shows_openable_when_cooldown_elapsed(self):
        from cogs.ui_renderer import build_village_embed
        now = datetime.now(timezone.utc)
        cooldown = int(ALL_TEST_ENV["TRIAL_COOLDOWN_SECONDS"])
        ended_at = now - timedelta(seconds=cooldown + 100)
        trial_data = self._make_trial_data(is_active=0)
        trial_data["ended_at"] = ended_at.isoformat()
        trial_amount = 35000
        resources = {"food": trial_amount, "wood": 0, "knowledge": 0}
        embed = build_village_embed(self._make_stage_data(), resources, {}, [], trial_data)
        self.assertIn("🏆 試煉 ✅ 可開啟試煉", embed.description)


class TestRendererTrialTargets(unittest.TestCase):
    def setUp(self):
        for k, v in ALL_TEST_ENV.items():
            os.environ[k] = v

    @staticmethod
    def _resources(balance):
        return {"food": balance, "wood": 0, "knowledge": 0}

    @staticmethod
    def _components(resources, page=0):
        from cogs.ui_renderer import build_trial_target_components

        return build_trial_target_components(resources, page)

    def test_example_resources_render_twelve_targets_with_matching_values(self):
        rows = self._components({"food": 51000, "wood": 310000, "knowledge": 220000})
        options = rows[0].children[0].options
        self.assertEqual(len(options), 12)
        self.assertEqual(options[0].label, "25000")
        self.assertEqual(options[-1].label, "300000")
        self.assertTrue(all(option.label == option.value for option in options))

    def test_six_hundred_twenty_five_thousand_fits_one_page(self):
        rows = self._components(self._resources(635000))
        options = rows[0].children[0].options
        self.assertEqual(len(options), 25)
        self.assertTrue(rows[1].children[1].disabled)

    def test_six_hundred_fifty_thousand_uses_second_page_for_final_target(self):
        rows = self._components(self._resources(660000), page=1)
        options = rows[0].children[0].options
        self.assertEqual(len(options), 1)
        self.assertEqual(options[0].value, "650000")
        previous, next_page, back = rows[1].children
        self.assertEqual(previous.custom_id, "trial_target_page:0")
        self.assertFalse(previous.disabled)
        self.assertTrue(next_page.disabled)
        self.assertEqual(back.custom_id, "back_to_main")

    def test_page_navigation_disables_edges_and_clamps_out_of_range_pages(self):
        first_page = self._components(self._resources(660000), page=-1)
        last_page = self._components(self._resources(660000), page=999)
        self.assertTrue(first_page[1].children[0].disabled)
        self.assertEqual(first_page[0].children[0].options[0].value, "25000")
        self.assertTrue(last_page[1].children[1].disabled)
        self.assertEqual(last_page[0].children[0].options[0].value, "650000")

    def test_no_legal_target_returns_only_back_button(self):
        rows = self._components(self._resources(9999))
        components = [component for row in rows for component in row.children]
        self.assertEqual(len(components), 1)
        self.assertEqual(components[0].custom_id, "back_to_main")

    def test_target_embed_reports_clamped_page(self):
        from cogs.ui_renderer import build_trial_target_embed

        embed = build_trial_target_embed(self._resources(660000), page=999)
        self.assertIn("第 2/2 頁", embed.description)
        self.assertIn("650000", embed.description)


class TestRendererMainEmbed(unittest.TestCase):
    """build_main_embed includes player status section."""

    def setUp(self):
        for k, v in ALL_TEST_ENV.items():
            os.environ[k] = v

    def _make_stage_data(self):
        now = datetime.now(timezone.utc).isoformat()
        return {
            "stages_cleared": 0,
            "current_stage_type": "gathering",
            "current_stage_progress": 0,
            "current_stage_target": 100,
            "stage_started_at": now,
            "updated_at": now,
            "overtime_notified": 0,
        }

    def _make_player(self, ap=5, action=None):
        return {
            "user_id": "111",
            "action": action,
            "action_target": None,
            "completion_time": None,
            "_ap": ap,
            "gear_gathering": 0,
            "gear_building": 1,
            "gear_combat": 0,
            "gear_research": 0,
            "materials_gathering": 3,
            "materials_building": 2,
            "materials_combat": 1,
            "materials_research": 0,
        }

    def test_embed_contains_player_status(self):
        from cogs.ui_renderer import build_main_embed
        player = self._make_player(ap=5)
        embed = build_main_embed(
            self._make_stage_data(), {}, {}, [], player
        )
        self.assertIn("個人資訊", embed.description)
        self.assertIn("⚡ AP：5", embed.description)

    def test_embed_no_action_shows_unset(self):
        from cogs.ui_renderer import build_main_embed
        player = self._make_player(action=None)
        embed = build_main_embed(self._make_stage_data(), {}, {}, [], player)
        self.assertIn("未設定", embed.description)

    def test_embed_shows_trial_contribution_when_active(self):
        from cogs.ui_renderer import build_main_embed
        player = self._make_player()
        trial_data = {"is_active": 1, "resource_type": "food", "target": 1000, "progress": 100}
        embed = build_main_embed(
            self._make_stage_data(), {}, {}, [], player, trial_data, 42
        )
        self.assertIn("🏆 試煉貢獻：42", embed.description)

    def test_embed_omits_trial_contribution_when_inactive(self):
        from cogs.ui_renderer import build_main_embed
        player = self._make_player()
        embed = build_main_embed(self._make_stage_data(), {}, {}, [], player)
        self.assertNotIn("試煉貢獻", embed.description)

    def test_embed_shows_trial_status_line_when_inactive(self):
        from cogs.ui_renderer import build_main_embed
        player = self._make_player()
        embed = build_main_embed(self._make_stage_data(), {}, {}, [], player)
        self.assertIn("🏆 試煉 ⚠️ 資源不足，尚無法開啟", embed.description)

    def test_embed_gear_levels_shown(self):
        from cogs.ui_renderer import build_main_embed
        player = self._make_player()
        player["gear_building"] = 3
        embed = build_main_embed(self._make_stage_data(), {}, {}, [], player)
        self.assertIn("🏅 工具：🌾 0 | 🔨 3 | ⚔️ 0 | 🔬 0", embed.description)
        self.assertIn("🎒 素材：🌾 3 | 🔨 2 | ⚔️ 1 | 🔬 0 | 🌟 0", embed.description)

    def test_embed_universal_material_shown_in_materials_line(self):
        from cogs.ui_renderer import build_main_embed
        player = self._make_player()
        player["materials_universal"] = 9
        embed = build_main_embed(self._make_stage_data(), {}, {}, [], player)
        self.assertIn("🎒 素材：🌾 3 | 🔨 2 | ⚔️ 1 | 🔬 0 | 🌟 9", embed.description)

    def test_embed_efficiency_line_uses_documented_formula(self):
        from cogs.ui_renderer import build_main_embed

        stage_data = self._make_stage_data()
        stage_data["stages_cleared"] = 19
        buildings = {
            "gathering_field": {"level": 4, "xp_progress": 0},
            "workshop": {"level": 2, "xp_progress": 0},
            "hunting_ground": {"level": 1, "xp_progress": 0},
            "research_lab": {"level": 4, "xp_progress": 0},
        }
        player = self._make_player()
        player["gear_gathering"] = 4
        player["gear_building"] = 4
        player["gear_combat"] = 4
        player["gear_research"] = 4
        embed = build_main_embed(stage_data, {}, buildings, [], player)

        efficiency_line = "📊 效率：🌾 25(+27%) | 🔨 25(+25%) | ⚔️ 24(+24%) | 🔬 25(+27%)"
        self.assertIn(efficiency_line, embed.description)
        self.assertLess(embed.description.index("📊 效率"), embed.description.index("🏅 工具"))

    def _make_player_with_ap_time(self, ap, ap_full_time_iso):
        p = self._make_player(ap=ap)
        p["ap_full_time"] = ap_full_time_iso
        return p

    def test_ap_next_recovery_shown_when_not_full(self):
        """AP < cap: shows （下次：<t:…:R>） suffix."""
        from cogs.ui_renderer import build_main_embed
        from core.config import get_env_int
        ap_cap = get_env_int("AP_CAP")
        recovery_mins = get_env_int("AP_RECOVERY_MINUTES")
        # ap_full_time placed exactly (ap_cap - ap) intervals ahead
        ap = 5
        base_unix = 1_800_000_000
        ap_full_time_unix = base_unix + (ap_cap - ap) * recovery_mins * 60
        ap_full_time_iso = datetime.fromtimestamp(ap_full_time_unix, tz=timezone.utc).isoformat()
        player = self._make_player_with_ap_time(ap, ap_full_time_iso)
        embed = build_main_embed(self._make_stage_data(), {}, {}, [], player)
        expected_next = ap_full_time_unix - (ap_cap - ap - 1) * recovery_mins * 60
        self.assertIn(f"⚡ AP：{ap} / {ap_cap}（下次：<t:{expected_next}:R>）", embed.description)

    def test_ap_no_next_recovery_when_full(self):
        """AP == cap: AP line has no timestamp suffix."""
        from cogs.ui_renderer import build_main_embed
        from core.config import get_env_int
        ap_cap = get_env_int("AP_CAP")
        ap_full_time_iso = datetime.fromtimestamp(1_700_000_000, tz=timezone.utc).isoformat()
        player = self._make_player_with_ap_time(ap_cap, ap_full_time_iso)
        embed = build_main_embed(self._make_stage_data(), {}, {}, [], player)
        self.assertIn(f"⚡ AP：{ap_cap} / {ap_cap}", embed.description)
        self.assertNotIn("<t:", embed.description.split("⚡ AP")[1].split("\n")[0])

    def test_ap_next_recovery_exact_value_ap_zero(self):
        """AP = 0: next_ap_unix = ap_full_time - (cap - 1) × recovery_mins × 60."""
        from cogs.ui_renderer import build_main_embed
        from core.config import get_env_int
        ap_cap = get_env_int("AP_CAP")
        recovery_mins = get_env_int("AP_RECOVERY_MINUTES")
        ap_full_time_unix = 1_800_000_000
        ap_full_time_iso = datetime.fromtimestamp(ap_full_time_unix, tz=timezone.utc).isoformat()
        player = self._make_player_with_ap_time(0, ap_full_time_iso)
        embed = build_main_embed(self._make_stage_data(), {}, {}, [], player)
        expected_next = ap_full_time_unix - (ap_cap - 1) * recovery_mins * 60
        self.assertIn(f"<t:{expected_next}:R>", embed.description)

    def test_ap_next_recovery_exact_value_non_integer_boundary(self):
        """Non-integer-minute ap_full_time: next_ap_unix still computed correctly."""
        from cogs.ui_renderer import build_main_embed
        from core.config import get_env_int
        ap_cap = get_env_int("AP_CAP")
        recovery_mins = get_env_int("AP_RECOVERY_MINUTES")
        ap = ap_cap - 2
        # Add 37 extra seconds to make it a non-integer boundary
        ap_full_time_unix = 1_800_000_000 + recovery_mins * 60 + 37
        ap_full_time_iso = datetime.fromtimestamp(ap_full_time_unix, tz=timezone.utc).isoformat()
        player = self._make_player_with_ap_time(ap, ap_full_time_iso)
        embed = build_main_embed(self._make_stage_data(), {}, {}, [], player)
        expected_next = ap_full_time_unix - (ap_cap - ap - 1) * recovery_mins * 60
        self.assertIn(f"<t:{expected_next}:R>", embed.description)


class TestRendererMainComponents(unittest.TestCase):
    """build_main_components follows documented button enablement rules."""

    def setUp(self):
        for k, v in ALL_TEST_ENV.items():
            os.environ[k] = v

    def _make_player(self, ap=1, gear_level=2):
        return {
            "_ap": ap,
            "action": "gathering",
            "gear_gathering": gear_level,
            "gear_building": gear_level,
            "gear_combat": gear_level,
            "gear_research": gear_level,
        }

    def test_gear_upgrade_enabled_when_all_gear_at_cap(self):
        # The gear upgrade submenu is the only entry to affix management and material sacrifice,
        # so max-level players must still be able to open it.
        from cogs.ui_renderer import build_main_components

        buildings = {"research_lab": {"level": 2, "xp_progress": 0}}
        rows = build_main_components(self._make_player(ap=1, gear_level=2), buildings)
        gear_button = next(
            component
            for row in rows
            for component in row.children
            if getattr(component, "custom_id", None) == "open_gear_upgrade"
        )

        self.assertFalse(
            gear_button.disabled,
            "Gear upgrade button must stay enabled at research-lab cap to reach affix management",
        )

    def test_gear_upgrade_enabled_when_no_ap_but_not_at_cap(self):
        from cogs.ui_renderer import build_main_components

        buildings = {"research_lab": {"level": 3, "xp_progress": 0}}
        rows = build_main_components(self._make_player(ap=0, gear_level=1), buildings)
        gear_button = next(
            component
            for row in rows
            for component in row.children
            if getattr(component, "custom_id", None) == "open_gear_upgrade"
        )

        self.assertFalse(
            gear_button.disabled,
            "Gear upgrade button should be enabled when AP=0 but gear is not at cap",
        )

    def _trial_button(self, rows):
        return next(
            component
            for row in rows
            for component in row.children
            if getattr(component, "custom_id", None) == "open_trial_start"
        )

    def _abundant_resources(self):
        amount = 35000
        return {"food": amount, "wood": 0, "knowledge": 0}

    def test_trial_start_enabled_when_no_trial_and_no_cooldown(self):
        from cogs.ui_renderer import build_main_components

        buildings = {"research_lab": {"level": 3, "xp_progress": 0}}
        rows = build_main_components(
            self._make_player(), buildings, trial_data=None, resources=self._abundant_resources()
        )
        self.assertFalse(self._trial_button(rows).disabled)

    def test_trial_start_disabled_when_no_resource_has_enough(self):
        from cogs.ui_renderer import build_main_components

        buildings = {"research_lab": {"level": 3, "xp_progress": 0}}
        rows = build_main_components(
            self._make_player(), buildings, trial_data=None, resources={"food": 1, "wood": 1, "knowledge": 1}
        )
        self.assertTrue(self._trial_button(rows).disabled)

    def test_trial_start_uses_reserve_boundary(self):
        from cogs.ui_renderer import build_main_components

        buildings = {"research_lab": {"level": 3, "xp_progress": 0}}
        below_reserve_boundary = build_main_components(
            self._make_player(), buildings, trial_data=None, resources={"food": 34999}
        )
        at_reserve_boundary = build_main_components(
            self._make_player(), buildings, trial_data=None, resources={"food": 35000}
        )
        self.assertTrue(self._trial_button(below_reserve_boundary).disabled)
        self.assertFalse(self._trial_button(at_reserve_boundary).disabled)

    def test_trial_start_disabled_when_trial_active(self):
        from cogs.ui_renderer import build_main_components

        buildings = {"research_lab": {"level": 3, "xp_progress": 0}}
        trial_data = {"is_active": 1, "target": 50000, "progress": 100, "ended_at": None}
        rows = build_main_components(
            self._make_player(), buildings, trial_data=trial_data, resources=self._abundant_resources()
        )
        self.assertTrue(self._trial_button(rows).disabled)

    def test_trial_start_disabled_during_cooldown(self):
        from cogs.ui_renderer import build_main_components

        now = datetime.now(timezone.utc)
        trial_data = {"is_active": 0, "ended_at": now.isoformat()}
        buildings = {"research_lab": {"level": 3, "xp_progress": 0}}
        rows = build_main_components(
            self._make_player(), buildings, trial_data=trial_data, resources=self._abundant_resources()
        )
        self.assertTrue(self._trial_button(rows).disabled)

    def test_trial_start_enabled_after_cooldown_elapsed(self):
        from cogs.ui_renderer import build_main_components

        cooldown = int(ALL_TEST_ENV["TRIAL_COOLDOWN_SECONDS"])
        ended_at = datetime.now(timezone.utc) - timedelta(seconds=cooldown + 10)
        trial_data = {"is_active": 0, "ended_at": ended_at.isoformat()}
        buildings = {"research_lab": {"level": 3, "xp_progress": 0}}
        rows = build_main_components(
            self._make_player(), buildings, trial_data=trial_data, resources=self._abundant_resources()
        )
        self.assertFalse(self._trial_button(rows).disabled)

    def test_burst_and_gear_buttons_are_first_row_without_refresh(self):
        from cogs.ui_renderer import build_main_components

        buildings = {"research_lab": {"level": 3, "xp_progress": 0}}
        rows = build_main_components(self._make_player(ap=1, gear_level=1), buildings)
        first_row_ids = [component.custom_id for component in rows[0].children]
        all_ids = [
            component.custom_id
            for row in rows
            for component in row.children
            if getattr(component, "custom_id", None)
        ]

        self.assertEqual(
            first_row_ids,
            ["burst_execute", "open_gear_upgrade", "open_trial_start", "open_auto_tool"],
        )
        self.assertNotIn("refresh", all_ids)
        self.assertEqual(rows[0].children[0].label, "⚡ 消耗AP立刻完成三次行動")

    def test_action_dropdown_options_have_descriptions(self):
        from cogs.ui_renderer import build_main_components

        rows = build_main_components(self._make_player(), {})
        action_select = rows[1].children[0]
        descriptions = {option.value: option.description for option in action_select.options}

        self.assertEqual(descriptions["gathering"], "產出 🌾食物 + 🪵木頭")
        self.assertEqual(descriptions["building"], "消耗 🪵木頭 | 產出 建築XP")
        self.assertEqual(descriptions["combat"], "消耗 🪵木頭 | 產出 🧠知識")
        self.assertEqual(descriptions["research"], "消耗 🧠知識 | 產出 研究所XP")


class TestRendererGearEmbed(unittest.TestCase):
    """build_gear_embed shows upgrade info and results."""

    def setUp(self):
        for k, v in ALL_TEST_ENV.items():
            os.environ[k] = v

    def _make_info(self, gear_level=2, pity=1, ap=3, materials=5, universal_materials=0):
        from core.config import get_env_float, get_env_int
        import math
        min_rate = get_env_float("GEAR_MIN_SUCCESS_RATE")
        loss_per = get_env_float("GEAR_RATE_LOSS_PER_LEVEL")
        pity_bonus = get_env_float("GEAR_PITY_BONUS")
        base = max(min_rate, 1.0 - gear_level * loss_per)
        rate = min(1.0, base + pity * pity_bonus)
        return {
            "gear_level": gear_level,
            "target_level": gear_level + 1,
            "material_cost": gear_level + 1,
            "rate": rate,
            "pity": pity,
            "ap": ap,
            "can_attempt": True,
            "gear_cap": 5,
            "materials": materials,
            "universal_materials": universal_materials,
        }

    def test_embed_shows_levels(self):
        from cogs.ui_renderer import build_gear_embed
        info = self._make_info(gear_level=2)
        embed = build_gear_embed(info, "gathering")
        self.assertIn("Lv2 → Lv3", embed.description)

    def test_success_result_shown(self):
        from cogs.ui_renderer import build_gear_embed
        info = self._make_info()
        result = {"success": True, "new_level": 3, "rate": 0.8}
        embed = build_gear_embed(info, "combat", result)
        self.assertIn("強化成功", embed.description)

    def test_failure_result_shown(self):
        from cogs.ui_renderer import build_gear_embed
        info = self._make_info()
        result = {"success": False, "new_level": 2, "rate": 0.5}
        embed = build_gear_embed(info, "combat", result)
        self.assertIn("強化失敗", embed.description)

    def test_materials_displayed(self):
        from cogs.ui_renderer import build_gear_embed
        info = self._make_info(materials=7)
        embed = build_gear_embed(info, "gathering")
        self.assertIn("持有素材：7 個", embed.description)

    def test_universal_materials_displayed(self):
        from cogs.ui_renderer import build_gear_embed
        info = self._make_info(materials=7, universal_materials=12)
        embed = build_gear_embed(info, "gathering")
        self.assertIn("持有素材：7 個 ｜ 🌟 萬能素材：12 個", embed.description)

    def test_level_6_rate_display_uses_decimal_intent(self):
        from cogs.ui_renderer import build_gear_embed
        info = self._make_info(gear_level=6, pity=0)
        embed = build_gear_embed(info, "gathering")
        self.assertIn("成功率：40%（+保底0% +鐵齒0%）= 40%", embed.description)


class TestRendererGearComponents(unittest.TestCase):
    """build_gear_components shows documented gear option descriptions."""

    def setUp(self):
        for k, v in ALL_TEST_ENV.items():
            os.environ[k] = v

    def test_gear_options_show_level_transition_descriptions(self):
        from cogs.ui_renderer import build_gear_components

        player_gear = {"gathering": 1, "building": 0, "combat": 2, "research": 1}
        rows = build_gear_components("combat", "normal", True, player_gear, gear_cap=5)
        gear_select = rows[0].children[0]
        descriptions = {option.value: option.description for option in gear_select.options}

        self.assertEqual(descriptions["gathering"], "Lv1 → Lv2: 採集產出 +5% → +10%")
        self.assertEqual(descriptions["building"], "Lv0 → Lv1: 建設產出 +0% → +5%")
        self.assertEqual(descriptions["combat"], "Lv2 → Lv3: 戰鬥產出 +10% → +15%")

    def test_gear_options_show_cap_description(self):
        from cogs.ui_renderer import build_gear_components

        player_gear = {"gathering": 3, "building": 1, "combat": 0, "research": 2}
        rows = build_gear_components("gathering", "normal", False, player_gear, gear_cap=3)
        gear_select = rows[0].children[0]
        descriptions = {option.value: option.description for option in gear_select.options}

        self.assertEqual(descriptions["gathering"], "已達等級上限 Lv3")

    def test_capped_gear_keeps_sacrifice_and_affix_management_available(self):
        from cogs.ui_renderer import build_gear_components

        player_gear = {"gathering": 5, "building": 5, "combat": 5, "research": 5}
        rows = build_gear_components(
            "gathering", "normal", False, player_gear, gear_cap=5, max_slots=1, materials=3
        )
        buttons = {
            component.custom_id: component
            for row in rows
            for component in row.children
            if getattr(component, "custom_id", None)
            in {
                "attempt_upgrade:gathering:normal",
                "sacrifice_material:gathering",
                "open_affix_mgmt:gathering",
            }
        }

        self.assertTrue(buttons["attempt_upgrade:gathering:normal"].disabled)
        self.assertFalse(
            buttons["sacrifice_material:gathering"].disabled,
            "Max-level players must still reach affix management and material sacrifice",
        )
        self.assertFalse(
            buttons["open_affix_mgmt:gathering"].disabled,
            "Max-level players must still reach affix management and material sacrifice",
        )


class TestGearEmbedRiskyLine(unittest.TestCase):
    """鐵齒等級 line visibility in gear upgrade embed."""

    def setUp(self):
        for k, v in ALL_TEST_ENV.items():
            os.environ[k] = v

    def _make_info(self, mode="normal", risky_failed_levels=0, risky_bonus_pct=0.0):
        from core.config import get_env_float
        min_rate = get_env_float("GEAR_MIN_SUCCESS_RATE")
        loss_per = get_env_float("GEAR_RATE_LOSS_PER_LEVEL")
        pity_bonus = get_env_float("GEAR_PITY_BONUS")
        gear_level = 3
        pity = 2
        base = max(min_rate, 1.0 - gear_level * loss_per)
        rate = min(1.0, base + pity * pity_bonus + risky_failed_levels * 0.0001)
        info = {
            "gear_level": gear_level,
            "target_level": gear_level + 1,
            "material_cost": gear_level + 1,
            "rate": rate,
            "pity": pity,
            "ap": 3,
            "can_attempt": True,
            "gear_cap": 5,
            "materials": 5,
            "mode": mode,
        }
        if mode in ("normal", "risky"):
            info["risky_failed_levels"] = risky_failed_levels
            info["risky_bonus_pct"] = risky_bonus_pct
        return info

    def test_risky_line_appears_in_risky_mode(self):
        from cogs.ui_renderer import build_gear_embed
        info = self._make_info(mode="risky", risky_failed_levels=5, risky_bonus_pct=0.05)
        embed = build_gear_embed(info, "gathering")
        self.assertIn("鐵齒率：5 x 0.01% = 0.05%", embed.description)

    def test_risky_line_appears_in_normal_mode(self):
        from cogs.ui_renderer import build_gear_embed
        info = self._make_info(mode="normal", risky_failed_levels=5, risky_bonus_pct=0.05)
        embed = build_gear_embed(info, "gathering")
        self.assertIn("鐵齒率：5 x 0.01% = 0.05%", embed.description)

    def test_normal_mode_rate_reflects_risky_failed_levels(self):
        from cogs.ui_renderer import build_gear_embed
        info = self._make_info(mode="normal", risky_failed_levels=1000, risky_bonus_pct=10.0)
        embed = build_gear_embed(info, "gathering")
        # rate = base+pity+bonus; embed should display this boosted rate
        self.assertIn(f"{round(info['rate'] * 100)}%", embed.description)

    def test_risky_line_not_in_buffer_mode(self):
        from cogs.ui_renderer import build_gear_embed
        info = self._make_info(mode="buffer")
        embed = build_gear_embed(info, "gathering")
        self.assertNotIn("鐵齒率", embed.description)

    def test_risky_line_zero_failed_levels(self):
        from cogs.ui_renderer import build_gear_embed
        info = self._make_info(mode="risky", risky_failed_levels=0, risky_bonus_pct=0.0)
        embed = build_gear_embed(info, "combat")
        self.assertIn("鐵齒率：0 x 0.01% = 0%", embed.description)


class TestGearComponentsBlankState(unittest.TestCase):
    """build_gear_embed and build_gear_components with gear_type=None show no pre-selected defaults."""

    def setUp(self):
        for k, v in ALL_TEST_ENV.items():
            os.environ[k] = v

    def _player_gear(self):
        return {"gathering": 1, "building": 0, "combat": 0, "research": 0}

    def test_blank_embed_returned_when_gear_type_is_none(self):
        from cogs.ui_renderer import build_gear_embed
        embed = build_gear_embed({}, None)
        self.assertIn("🔨 工具強化", embed.description)

    def test_gear_dropdown_has_no_default_when_gear_type_is_none(self):
        from cogs.ui_renderer import build_gear_components
        rows = build_gear_components(None, None, False, self._player_gear(), gear_cap=5)
        gear_select = rows[0].children[0]
        self.assertFalse(any(opt.default for opt in gear_select.options))

    def test_mode_dropdown_has_no_default_when_mode_is_none(self):
        from cogs.ui_renderer import build_gear_components
        rows = build_gear_components(None, None, False, self._player_gear(), gear_cap=5)
        mode_select = rows[1].children[0]
        self.assertFalse(any(opt.default for opt in mode_select.options))

    def test_attempt_button_disabled_when_mode_is_none(self):
        from cogs.ui_renderer import build_gear_components
        rows = build_gear_components("gathering", None, True, self._player_gear(), gear_cap=5)
        buttons = {c.custom_id: c for row in rows for c in row.children if hasattr(c, "custom_id")}
        attempt_btn = next((c for cid, c in buttons.items() if cid.startswith("attempt_upgrade:")), None)
        self.assertIsNotNone(attempt_btn)
        self.assertTrue(attempt_btn.disabled)

    def test_mode_dropdown_custom_id_uses_sentinel_when_gear_type_is_none(self):
        from cogs.ui_renderer import build_gear_components
        rows = build_gear_components(None, None, False, self._player_gear(), gear_cap=5)
        mode_select = rows[1].children[0]
        self.assertEqual(mode_select.custom_id, "upgrade_mode_select:none")


class TestRiskyDropdownDescription(unittest.TestCase):
    """Risky dropdown description reflects updated mechanics."""

    def setUp(self):
        for k, v in ALL_TEST_ENV.items():
            os.environ[k] = v

    def test_risky_dropdown_description_updated(self):
        from cogs.ui_renderer import build_gear_components
        player_gear = {"gathering": 1, "building": 0, "combat": 1, "research": 0}
        rows = build_gear_components("gathering", "risky", True, player_gear, gear_cap=5)
        mode_select = rows[1].children[0]
        descriptions = {option.value: option.description for option in mode_select.options}
        self.assertEqual(
            descriptions["risky"],
            "僅消耗 1 個素材，成功 +1~+3（50/35/15%），失敗則工具等級與 pity 均歸零",
        )

    def test_normal_and_buffer_descriptions_unchanged(self):
        from cogs.ui_renderer import build_gear_components
        player_gear = {"gathering": 1, "building": 0, "combat": 1, "research": 0}
        rows = build_gear_components("gathering", "normal", True, player_gear, gear_cap=5)
        mode_select = rows[1].children[0]
        descriptions = {option.value: option.description for option in mode_select.options}
        self.assertIn("正常", descriptions["normal"])
        self.assertIn("一半素材", descriptions["buffer"])


class TestAffixEmbedSection(unittest.TestCase):
    """Affix slot display in gear embed."""

    def setUp(self):
        for k, v in ALL_TEST_ENV.items():
            os.environ[k] = v

    def _make_info(self, gear_level=5):
        from core.config import get_env_float
        info = {
            "gear_level": gear_level,
            "target_level": gear_level + 1,
            "material_cost": gear_level + 1,
            "rate": 0.8,
            "pity": 0,
            "ap": 2,
            "can_attempt": True,
            "gear_cap": 10,
            "materials": 10,
            "mode": "normal",
            "risky_failed_levels": 0,
            "risky_bonus_pct": 0.0,
        }
        return info

    def test_no_slots_hides_affix_section(self):
        from cogs.ui_renderer import build_gear_embed
        embed = build_gear_embed(self._make_info(gear_level=4), "gathering", max_slots=0)
        self.assertNotIn("詞條槽", embed.description)

    def test_empty_slots_shown_with_count(self):
        from cogs.ui_renderer import build_gear_embed
        embed = build_gear_embed(self._make_info(gear_level=5), "gathering", affixes=[], max_slots=1)
        self.assertIn("詞條槽（0/1）", embed.description)
        self.assertIn("（尚無詞條）", embed.description)
        self.assertNotIn("槽 0:", embed.description)

    def test_filled_slot_shows_affix_type_and_value(self):
        from cogs.ui_renderer import build_gear_embed
        affixes = [{"slot_index": 0, "affix_type": "efficiency", "value": 3}]
        embed = build_gear_embed(self._make_info(gear_level=5), "gathering", affixes=affixes, max_slots=1)
        self.assertIn("詞條槽（1/1）", embed.description)
        self.assertIn("行動效率: 3%", embed.description)
        self.assertNotIn("槽 0:", embed.description)

    def test_same_type_slots_are_summed_in_fixed_label_order(self):
        from cogs.ui_renderer import build_gear_embed
        affixes = [
            {"slot_index": 0, "affix_type": "cycle_time_reduce", "value": 2},
            {"slot_index": 1, "affix_type": "efficiency", "value": 3},
            {"slot_index": 2, "affix_type": "efficiency", "value": 4},
            {"slot_index": 3, "affix_type": "upgrade_success", "value": 0},
        ]
        embed = build_gear_embed(self._make_info(gear_level=10), "gathering", affixes=affixes, max_slots=5)
        self.assertIn("詞條槽（4/5）", embed.description)
        self.assertLess(embed.description.index("行動效率: 7%"), embed.description.index("週期縮短: 2%"))
        self.assertNotIn("強化成功:", embed.description)
        self.assertNotIn("槽 ", embed.description)

    def test_upgrade_cost_reduce_uses_positive_sign_and_new_label(self):
        from cogs.ui_renderer import build_gear_embed
        affixes = [{"slot_index": 0, "affix_type": "upgrade_cost_reduce", "value": 5}]
        embed = build_gear_embed(self._make_info(gear_level=5), "gathering", affixes=affixes, max_slots=1)
        self.assertIn("素材減免: 5%", embed.description)
        self.assertNotIn("素材減免: -5%", embed.description)


class TestAffixManagementEmbed(unittest.TestCase):
    def test_summary_precedes_divider_and_slot_list_remains(self):
        from cogs.ui_renderer import build_affix_embed
        player_gear = {"gathering": 5, "building": 0, "combat": 0, "research": 0}
        affixes = [
            {"slot_index": 0, "affix_type": "upgrade_cost_reduce", "value": 5},
            {"slot_index": 2, "affix_type": "efficiency", "value": 3},
        ]
        embed = build_affix_embed("gathering", player_gear, affixes, 3, selected_group=("upgrade_cost_reduce", 5), materials=7)
        summary_index = embed.description.index("詞條合計")
        divider_index = embed.description.index("─────────────────────────────")
        self.assertLess(embed.description.index("持有素材：7 個"), summary_index)
        self.assertLess(summary_index, divider_index)
        self.assertIn("個\n\n詞條合計", embed.description)
        self.assertIn("素材減免: 5%", embed.description)
        self.assertIn("素材減免（+5%） x 1", embed.description)
        self.assertIn("行動效率（+3%） x 1", embed.description)
        self.assertIn("空槽 x 1", embed.description)
        self.assertIn("即將清除：素材減免（+5%）", embed.description)
        self.assertNotIn("即將清除：槽", embed.description)

    def test_grouped_list_counts_orders_and_hides_slot_numbers(self):
        import re
        from cogs.ui_renderer import build_affix_embed
        player_gear = {"gathering": 5, "building": 0, "combat": 0, "research": 0}
        affixes = (
            [{"slot_index": i, "affix_type": "cycle_time_reduce", "value": 5} for i in range(10)]
            + [{"slot_index": 10, "affix_type": "cycle_time_reduce", "value": 4}]
            + [{"slot_index": i, "affix_type": "cycle_time_reduce", "value": 3} for i in range(11, 14)]
        )
        desc = build_affix_embed("gathering", player_gear, affixes, 24).description
        self.assertIn("詞條槽（14/24）", desc)
        order = ["週期縮短（+5%） x 10", "週期縮短（+4%） x 1", "週期縮短（+3%） x 3", "空槽 x 10"]
        positions = [desc.index(t) for t in order]
        self.assertEqual(positions, sorted(positions))
        self.assertIsNone(re.search(r"槽 \d", desc))

    def test_full_slots_show_no_empty_row(self):
        from cogs.ui_renderer import build_affix_embed
        player_gear = {"gathering": 5, "building": 0, "combat": 0, "research": 0}
        affixes = [{"slot_index": 0, "affix_type": "efficiency", "value": 3}]
        self.assertNotIn("空槽", build_affix_embed("gathering", player_gear, affixes, 1).description)

    def test_selected_group_absent_from_affixes_shows_no_pending_clear(self):
        from cogs.ui_renderer import build_affix_embed
        player_gear = {"gathering": 5, "building": 0, "combat": 0, "research": 0}
        affixes = [{"slot_index": 0, "affix_type": "efficiency", "value": 3}]
        embed = build_affix_embed("gathering", player_gear, affixes, 2, selected_group=("efficiency", 5))
        self.assertNotIn("即將清除", embed.description)

    def test_empty_affixes_still_show_summary_before_empty_slot_list(self):
        from cogs.ui_renderer import build_affix_embed
        player_gear = {"gathering": 5, "building": 0, "combat": 0, "research": 0}
        embed = build_affix_embed("gathering", player_gear, [], 2, selected_group=("efficiency", 5), materials=7)
        summary_index = embed.description.index("詞條合計")
        divider_index = embed.description.index("─────────────────────────────")
        self.assertLess(summary_index, embed.description.index("（尚無詞條）"))
        self.assertLess(summary_index, divider_index)
        self.assertIn("空槽 x 2", embed.description)
        self.assertNotIn("即將清除", embed.description)

    def test_summary_hidden_when_no_slot_unlocked(self):
        from cogs.ui_renderer import build_affix_embed
        player_gear = {"gathering": 1, "building": 0, "combat": 0, "research": 0}
        embed = build_affix_embed("gathering", player_gear, [], 0, selected_group=None, materials=7)
        self.assertNotIn("詞條合計", embed.description)
        self.assertNotIn("（尚無詞條）", embed.description)
        self.assertNotIn("詞條槽", embed.description)
        self.assertIn("持有素材：7 個", embed.description)


class TestAffixComponents(unittest.TestCase):
    """Affix management interface components (build_affix_components) and gear upgrade button changes."""

    def setUp(self):
        for k, v in ALL_TEST_ENV.items():
            os.environ[k] = v

    def _player_gear(self, level=5):
        return {"gathering": level, "building": 0, "combat": 0, "research": 0}

    def test_gear_mgmt_button_disabled_when_no_slots(self):
        from cogs.ui_renderer import build_gear_components
        rows = build_gear_components("gathering", "normal", True, self._player_gear(), gear_cap=10, max_slots=0)
        buttons = {c.custom_id: c for row in rows for c in row.children if hasattr(c, "custom_id")}
        self.assertIn("open_affix_mgmt:gathering", buttons)
        self.assertTrue(buttons["open_affix_mgmt:gathering"].disabled)

    def test_gear_mgmt_button_enabled_when_slots_unlocked(self):
        from cogs.ui_renderer import build_gear_components
        rows = build_gear_components("gathering", "normal", True, self._player_gear(), gear_cap=10, max_slots=1)
        buttons = {c.custom_id: c for row in rows for c in row.children if hasattr(c, "custom_id")}
        self.assertIn("open_affix_mgmt:gathering", buttons)
        self.assertFalse(buttons["open_affix_mgmt:gathering"].disabled)

    def test_no_extract_or_clear_buttons_in_gear_components(self):
        from cogs.ui_renderer import build_gear_components
        rows = build_gear_components("gathering", "normal", True, self._player_gear(), gear_cap=10, max_slots=2)
        custom_ids = [c.custom_id for row in rows for c in row.children if hasattr(c, "custom_id")]
        self.assertFalse(any("extract_affix" in cid or "clear_affix" in cid for cid in custom_ids))

    def test_gear_action_button_labels(self):
        from cogs.ui_renderer import build_gear_components
        rows = build_gear_components("gathering", "normal", True, self._player_gear(), gear_cap=10)
        labels = {
            c.custom_id: c.label
            for row in rows for c in row.children
            if hasattr(c, "custom_id") and hasattr(c, "label") and c.label
        }
        self.assertEqual(labels.get("attempt_upgrade:gathering:normal"), "🎲 強化工具")
        self.assertEqual(labels.get("sacrifice_material:gathering"), "🩸 獻祭素材")
        self.assertEqual(labels.get("open_affix_mgmt:gathering"), "🔮 詞條管理")

    def test_affix_components_gear_type_dropdown(self):
        from cogs.ui_renderer import build_affix_components
        rows = build_affix_components("gathering", self._player_gear(), gear_cap=10, affixes=[], max_slots=1)
        custom_ids = [c.custom_id for row in rows for c in row.children if hasattr(c, "custom_id")]
        self.assertIn("affix_gear_select", custom_ids)

    def test_affix_components_no_slot_dropdown_when_empty(self):
        from cogs.ui_renderer import build_affix_components
        rows = build_affix_components("gathering", self._player_gear(), gear_cap=10, affixes=[], max_slots=1)
        custom_ids = [c.custom_id for row in rows for c in row.children if hasattr(c, "custom_id")]
        self.assertFalse(any("affix_slot_select" in cid for cid in custom_ids))

    def test_affix_components_slot_dropdown_shown_when_affixes_exist(self):
        from cogs.ui_renderer import build_affix_components
        affixes = [{"slot_index": 0, "affix_type": "efficiency", "value": 3}]
        rows = build_affix_components("gathering", self._player_gear(), gear_cap=10, affixes=affixes, max_slots=1)
        custom_ids = [c.custom_id for row in rows for c in row.children if hasattr(c, "custom_id")]
        self.assertIn("affix_slot_select:gathering", custom_ids)

    def test_affix_group_dropdown_option_uses_positive_value_and_new_label(self):
        from cogs.ui_renderer import build_affix_components
        affixes = [{"slot_index": 0, "affix_type": "upgrade_cost_reduce", "value": 5}]
        rows = build_affix_components("gathering", self._player_gear(), gear_cap=10, affixes=affixes, max_slots=1)
        slot_select = next(c for row in rows for c in row.children if c.custom_id == "affix_slot_select:gathering")
        self.assertEqual(slot_select.options[0].label, "素材減免（+5%） x 1")
        self.assertEqual(slot_select.options[0].value, "upgrade_cost_reduce:5")
        self.assertIsNone(slot_select.options[0].description)

    def test_affix_components_with_26_filled_slots_fit_discord_select_limit(self):
        # Test for correct design — currently fails due to bug in src/cogs/ui_renderer.py.
        # Discord rejects a select with more than 25 options, so the management screen never opens.
        from cogs.ui_renderer import build_affix_components
        affixes = [{"slot_index": i, "affix_type": "efficiency", "value": 1} for i in range(26)]
        rows = build_affix_components("gathering", self._player_gear(), gear_cap=300, affixes=affixes, max_slots=26)
        option_counts = [len(c.options) for row in rows for c in row.children if hasattr(c, "options")]
        self.assertEqual([n for n in option_counts if n > 25], [])
        slot_select = next(c for row in rows for c in row.children if c.custom_id == "affix_slot_select:gathering")
        self.assertEqual(len(slot_select.options), 1)
        self.assertEqual(slot_select.options[0].label, "行動效率（+1%） x 26")
        self.assertEqual(slot_select.options[0].value, "efficiency:1")

    def test_affix_group_dropdown_truncates_to_25_lowest_value_groups_in_list_order(self):
        from cogs.ui_renderer import AFFIX_TYPE_LABELS, build_affix_components
        affixes = [
            {"slot_index": 0, "affix_type": t, "value": v}
            for t in AFFIX_TYPE_LABELS for v in (1, 2, 3, 4)
        ]
        affixes += [
            {"slot_index": 0, "affix_type": "efficiency", "value": 5},
            {"slot_index": 0, "affix_type": "material_drop", "value": 5},
        ]
        rows = build_affix_components("gathering", self._player_gear(), gear_cap=300, affixes=affixes, max_slots=30)
        slot_select = next(c for row in rows for c in row.children if c.custom_id == "affix_slot_select:gathering")
        values = [o.value for o in slot_select.options]
        self.assertEqual(len(values), 25)
        for excluded in ("efficiency:5", "material_drop:5", "upgrade_ap_refund:4",
                         "upgrade_material_refund:4", "cycle_time_reduce:4"):
            self.assertNotIn(excluded, values)
        expected = [
            f"{t}:{v}" for t in AFFIX_TYPE_LABELS for v in (5, 4, 3, 2, 1)
            if f"{t}:{v}" in values
        ]
        self.assertEqual(values, expected)
        self.assertEqual(slot_select.placeholder, "選擇要清除的詞條...（另有 5 組未列出）")

    def test_affix_group_dropdown_marks_selected_group_default(self):
        from cogs.ui_renderer import build_affix_components
        affixes = [
            {"slot_index": 0, "affix_type": "efficiency", "value": 3},
            {"slot_index": 1, "affix_type": "efficiency", "value": 2},
        ]
        rows = build_affix_components(
            "gathering", self._player_gear(), gear_cap=10, affixes=affixes, max_slots=2,
            selected_group=("efficiency", 2),
        )
        slot_select = next(c for row in rows for c in row.children if c.custom_id == "affix_slot_select:gathering")
        self.assertEqual({o.value: o.default for o in slot_select.options}, {"efficiency:3": False, "efficiency:2": True})
        self.assertEqual(slot_select.placeholder, "選擇要清除的詞條...")

    def test_affix_components_clear_disabled_without_selection(self):
        from cogs.ui_renderer import build_affix_components
        affixes = [{"slot_index": 0, "affix_type": "efficiency", "value": 3}]
        rows = build_affix_components("gathering", self._player_gear(), gear_cap=10, affixes=affixes, max_slots=1)
        buttons = {c.custom_id: c for row in rows for c in row.children if hasattr(c, "custom_id")}
        self.assertIn("affix_clear:gathering:none:none", buttons)
        self.assertTrue(buttons["affix_clear:gathering:none:none"].disabled)

    def test_affix_components_clear_enabled_with_selection(self):
        from cogs.ui_renderer import build_affix_components
        affixes = [{"slot_index": 0, "affix_type": "efficiency", "value": 3}]
        rows = build_affix_components("gathering", self._player_gear(), gear_cap=10, affixes=affixes, max_slots=1, selected_group=("efficiency", 3))
        buttons = {c.custom_id: c for row in rows for c in row.children if hasattr(c, "custom_id")}
        self.assertIn("affix_clear:gathering:efficiency:3", buttons)
        self.assertFalse(buttons["affix_clear:gathering:efficiency:3"].disabled)

    def test_affix_components_extract_disabled_when_full(self):
        from cogs.ui_renderer import build_affix_components
        affixes = [{"slot_index": 0, "affix_type": "efficiency", "value": 3}]
        rows = build_affix_components("gathering", self._player_gear(), gear_cap=10, affixes=affixes, max_slots=1)
        buttons = {c.custom_id: c for row in rows for c in row.children if hasattr(c, "custom_id")}
        self.assertTrue(buttons["affix_extract:gathering"].disabled)

    def test_affix_components_extract_enabled_when_slot_available(self):
        from cogs.ui_renderer import build_affix_components
        rows = build_affix_components("gathering", self._player_gear(), gear_cap=10, affixes=[], max_slots=2)
        buttons = {c.custom_id: c for row in rows for c in row.children if hasattr(c, "custom_id")}
        self.assertFalse(buttons["affix_extract:gathering"].disabled)

    def test_affix_components_back_button_routes_to_gear(self):
        from cogs.ui_renderer import build_affix_components
        rows = build_affix_components("gathering", self._player_gear(), gear_cap=10, affixes=[], max_slots=1)
        custom_ids = [c.custom_id for row in rows for c in row.children if hasattr(c, "custom_id")]
        self.assertIn("back_to_gear:gathering", custom_ids)


class TestAffixComponentsBlankState(unittest.TestCase):
    """build_affix_embed and build_affix_components with gear_type=None show no pre-selected defaults."""

    def setUp(self):
        for k, v in ALL_TEST_ENV.items():
            os.environ[k] = v

    def _player_gear(self):
        return {"gathering": 0, "building": 0, "combat": 0, "research": 0}

    def test_blank_embed_returned_when_gear_type_is_none(self):
        from cogs.ui_renderer import build_affix_embed
        embed = build_affix_embed(None, self._player_gear(), [], 0)
        self.assertIn("🔮 詞條管理", embed.description)

    def test_material_holdings_displayed_when_gear_type_selected(self):
        from cogs.ui_renderer import build_affix_embed
        embed = build_affix_embed(
            "gathering", self._player_gear(), [], 5, materials=7, universal_materials=12
        )
        self.assertIn("持有素材：7 個 ｜ 🌟 萬能素材：12 個", embed.description)

    def test_gear_dropdown_has_no_default_when_gear_type_is_none(self):
        from cogs.ui_renderer import build_affix_components
        rows = build_affix_components(None, self._player_gear(), gear_cap=10, affixes=[], max_slots=0)
        gear_select = rows[0].children[0]
        self.assertFalse(any(opt.default for opt in gear_select.options))

    def test_back_button_uses_sentinel_when_gear_type_is_none(self):
        from cogs.ui_renderer import build_affix_components
        rows = build_affix_components(None, self._player_gear(), gear_cap=10, affixes=[], max_slots=0)
        custom_ids = [c.custom_id for row in rows for c in row.children if hasattr(c, "custom_id")]
        self.assertIn("back_to_gear:none", custom_ids)


class TestAutoAffixComponents(unittest.TestCase):
    def test_entry_requires_selected_gear_and_empty_slot(self):
        from cogs.ui_renderer import build_affix_components
        gear = {"gathering": 0, "building": 5}
        for selected, affixes, slots, disabled in ((None, [], 1, True), ("gathering", [], 1, True),
                                                     ("building", [], 0, True), ("building", [{"slot_index": 0, "affix_type": "efficiency", "value": 1}], 1, True),
                                                     ("building", [], 1, False)):
            rows = build_affix_components(selected, gear, 10, affixes, slots)
            button = next(c for row in rows for c in row.children if c.custom_id.startswith("open_auto_affix:"))
            self.assertEqual(button.disabled, disabled)

    def test_settings_require_complete_choices_and_selected_balance(self):
        from cogs.ui_renderer import build_auto_affix_components
        common = ("research", 0, 0, 1, [])
        rows = build_auto_affix_components(*common)
        confirm = next(c for row in rows for c in row.children if c.custom_id.startswith("auto_affix_run:"))
        self.assertTrue(confirm.disabled)
        self.assertEqual(confirm.custom_id.rsplit(":", 1)[1], "none")
        rows = build_auto_affix_components("research", 1, 0, 1, [], "any", None, 1, "tool", confirmation_token="abcdefgh")
        confirm = next(c for row in rows for c in row.children if c.custom_id.startswith("auto_affix_run:"))
        self.assertFalse(confirm.disabled)
        rows = build_auto_affix_components("research", 99, 4, 1, [], "any", None, 1, "universal", confirmation_token="abcdefgh")
        confirm = next(c for row in rows for c in row.children if c.custom_id.startswith("auto_affix_run:"))
        self.assertTrue(confirm.disabled)
        rows = build_auto_affix_components("research", 0, 5, 1, [], "specific", "efficiency", 5, "universal", confirmation_token="abcdefgh")
        confirm = next(c for row in rows for c in row.children if c.custom_id.startswith("auto_affix_run:"))
        self.assertFalse(confirm.disabled)

    def test_choices_and_selected_state_are_rendered_in_custom_ids(self):
        from cogs.ui_renderer import build_auto_affix_components, AFFIX_TYPE_LABELS
        rows = build_auto_affix_components("research", 3, 25, 2, [], "specific", "cycle_time_reduce", 4, "universal", confirmation_token="abcdefgh")
        self.assertEqual(len(rows), 5)
        selects = [row.children[0] for row in rows if isinstance(row.children[0], __import__("disnake").ui.StringSelect)]
        self.assertEqual([o.label for o in selects[0].options], ["任意", "特定效果"])
        self.assertEqual([o.label for o in selects[1].options], list(AFFIX_TYPE_LABELS.values()))
        self.assertEqual(
            [o.label for o in selects[1].options],
            ["行動效率", "素材掉落", "強化成功", "素材減免", "ＡＰ退還", "素材退還", "週期縮短"],
        )
        self.assertEqual([o.label for o in selects[2].options], ["1+", "2+", "3+", "4+", "5"])
        self.assertEqual([o.label for o in selects[3].options], ["工具素材", "萬能素材"])
        self.assertTrue(selects[0].options[1].default)
        self.assertTrue(selects[1].options[-1].default)
        self.assertTrue(selects[2].options[3].default)
        self.assertTrue(selects[3].options[1].default)
        selector_ids = [c.custom_id for row in rows for c in row.children if c.custom_id.startswith("auto_affix_") and not c.custom_id.startswith("auto_affix_run:")]
        self.assertTrue(all(cid.endswith(":research:specific:cycle_time_reduce:4:universal") for cid in selector_ids))
        confirm = next(c for row in rows for c in row.children if c.custom_id.startswith("auto_affix_run:"))
        self.assertTrue(confirm.custom_id.endswith(":research:specific:cycle_time_reduce:4:universal:0:abcdefgh"))

    def test_confirm_needs_real_empty_slot_and_valid_gear(self):
        from cogs.ui_renderer import build_auto_affix_components
        settings = ("any", None, 1, "tool")
        for gear, affixes, slots in ((None, [], 1), ("invalid", [], 1),
                                     ("research", [{"slot_index": 0}], 1)):
            rows = build_auto_affix_components(gear, 1, 0, slots, affixes, *settings, confirmation_token="abcdefgh")
            confirm = next(c for row in rows for c in row.children if c.custom_id.startswith("auto_affix_run:"))
            self.assertTrue(confirm.disabled)
        rows = build_auto_affix_components("research", 1, 0, 1, [{"slot_index": 8}], *settings, confirmation_token="abcdefgh")
        confirm = next(c for row in rows for c in row.children if c.custom_id.startswith("auto_affix_run:"))
        self.assertFalse(confirm.disabled)

    def test_auto_affix_embed_shows_fifth_threshold_and_cost(self):
        from cogs.ui_renderer import build_auto_affix_embed
        embed = build_auto_affix_embed("research", 1, 5, 1, [], "any", None, 5, "universal")
        self.assertIn("目標數值：5", embed.description)
        self.assertIn("每次抽選：1 工具素材或 5 萬能素材", embed.description)

    def test_custom_ids_stay_within_limit_for_all_setting_combinations(self):
        from itertools import product
        from cogs.ui_renderer import build_auto_affix_components
        for mode, effect, value, source in product((None, "any", "specific"), (None, "upgrade_material_refund"),
                                                    (None, 1, 2, 3, 4, 5), (None, "tool", "universal")):
            for candidate_effect in ((None, "upgrade_material_refund") if mode == "specific" else (None,)):
                rows = build_auto_affix_components("research", 999, 999, 3, [], mode,
                                                   candidate_effect, value, source, confirmation_token="abcdefgh")
                self.assertLessEqual(len(rows), 5)
                for row in rows:
                    for component in row.children:
                        self.assertLessEqual(len(component.custom_id), 100)

    def test_confirmation_binds_first_empty_slot_and_stays_within_limit(self):
        from cogs.ui_renderer import build_auto_affix_components
        settings = ("specific", "upgrade_material_refund", 5, "universal")
        rows = build_auto_affix_components("research", 0, 5, 2, [{"slot_index": 0}], *settings, confirmation_token="abcdefgh")
        confirm = next(c for row in rows for c in row.children if c.custom_id.startswith("auto_affix_run:"))
        self.assertEqual(confirm.custom_id, "auto_affix_run:research:specific:upgrade_material_refund:5:universal:1:abcdefgh")
        self.assertFalse(confirm.disabled)
        rows = build_auto_affix_components("research", 0, 5, 2, [{"slot_index": 0}, {"slot_index": 1}], *settings, confirmation_token="abcdefgh")
        confirm = next(c for row in rows for c in row.children if c.custom_id.startswith("auto_affix_run:"))
        self.assertTrue(confirm.disabled)
        self.assertTrue(confirm.custom_id.endswith(":none:abcdefgh"))
        longest_id = "auto_affix_run:research:specific:upgrade_material_refund:5:universal:2147483647:abcdefgh"
        self.assertLessEqual(len(longest_id), 100)


class TestAffixRouteRegistration(unittest.TestCase):
    """Affix interface interaction routes are registered."""

    def setUp(self):
        for k, v in ALL_TEST_ENV.items():
            os.environ[k] = v

    def test_clear_affix_is_own_button(self):
        from cogs.actions import _is_own_button
        self.assertTrue(_is_own_button("clear_affix:gathering:0"))

    def test_open_affix_mgmt_is_own_button(self):
        from cogs.actions import _is_own_button
        self.assertTrue(_is_own_button("open_affix_mgmt:gathering"))

    def test_affix_extract_is_own_button(self):
        from cogs.actions import _is_own_button
        self.assertTrue(_is_own_button("affix_extract:gathering"))

    def test_affix_clear_is_own_button(self):
        from cogs.actions import _is_own_button
        self.assertTrue(_is_own_button("affix_clear:gathering:0"))

    def test_back_to_gear_is_own_button(self):
        from cogs.actions import _is_own_button
        self.assertTrue(_is_own_button("back_to_gear:gathering"))


class TestAutoAffixHandlerIntegration(DatabaseTestCase):
    async def _player(self, *, tool=0, universal=0, level=5):
        from database.schema import get_connection
        from core.utils import dt_str
        now = dt_str(datetime.now(timezone.utc))
        async with get_connection() as db:
            await db.execute(
                "INSERT INTO players (user_id, created_at, updated_at, ap_full_time, materials_research, materials_universal, gear_research) VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("12345", now, now, now, tool, universal, level),
            )
            await db.commit()

    def _inter(self, cid, value=None):
        inter = MagicMock()
        inter.guild_id = int(ALL_TEST_ENV["DISCORD_GUILD_ID"])
        inter.user.id = 12345
        inter.user.display_name = "TestUser"
        inter.component.custom_id = cid
        inter.values = [value] if value is not None else []
        inter.response.defer = AsyncMock()
        inter.edit_original_response = AsyncMock()
        return inter

    async def _select(self, cog, prefix, state, selected):
        inter = self._inter(f"{prefix}:{state}", selected)
        await cog.on_dropdown(inter)
        return inter

    async def _select_id(self, cog, custom_id, selected):
        inter = self._inter(custom_id, selected)
        await cog.on_dropdown(inter)
        return inter

    @staticmethod
    def _component_id(inter, prefix):
        return next(
            component.custom_id for row in inter.edit_original_response.call_args.kwargs["components"]
            for component in row.children if component.custom_id.startswith(prefix)
        )

    async def _render_confirm(self, cog, *, mode="any", effect=None, threshold=1, source="tool", gear="research"):
        inter = self._inter(f"open_auto_affix:{gear}")
        await cog.on_button_click(inter)
        await cog._render_auto_affix(
            inter, gear, target_mode=mode, target_affix_type=effect,
            min_value=threshold, material_source=source,
        )
        custom_id = next(
            component.custom_id
            for row in inter.edit_original_response.call_args.kwargs["components"]
            for component in row.children if component.custom_id.startswith("auto_affix_run:")
        )
        return custom_id, inter

    async def test_full_configuration_success_uses_real_manager_renderer_and_notification(self):
        from cogs.actions import ActionsCog
        from database.schema import get_connection
        await self._player(tool=3)
        sent = AsyncMock()
        bot = MagicMock()
        bot.get_channel.return_value.send = sent
        cog = ActionsCog(bot)
        state = "research:none:none:none:none"
        await self._select(cog, "auto_affix_kind", state, "specific")
        state = "research:specific:none:none:none"
        await self._select(cog, "auto_affix_effect", state, "cycle_time_reduce")
        state = "research:specific:cycle_time_reduce:none:none"
        await self._select(cog, "auto_affix_value", state, "4")
        state = "research:specific:cycle_time_reduce:4:none"
        last = await self._select(cog, "auto_affix_material", state, "tool")
        self.assertIn("research:specific:cycle_time_reduce:4:tool", last.edit_original_response.call_args.kwargs["components"][0].children[0].custom_id)
        confirm_id = next(
            component.custom_id for row in last.edit_original_response.call_args.kwargs["components"]
            for component in row.children if component.custom_id.startswith("auto_affix_run:")
        )
        with patch("cogs.actions.affix_manager.random.choice", return_value="cycle_time_reduce"), patch(
            "cogs.actions.affix_manager.random.randint", return_value=4
        ):
            confirm = self._inter(confirm_id)
            await cog.on_button_click(confirm)
        self.assertTrue(confirm.response.defer.awaited)
        self.assertEqual(sent.await_count, 1)
        self.assertIn("抽到詞條：週期縮短（+4%）", sent.call_args.args[0])
        async with get_connection() as db:
            self.assertEqual(await (await db.execute("SELECT materials_research FROM players WHERE user_id='12345'")).fetchone(), (2,))
            self.assertEqual(await (await db.execute("SELECT slot_index, affix_type, value FROM gear_affixes WHERE user_id='12345'")).fetchone(), (0, "cycle_time_reduce", 4))

    async def test_any_mode_ignores_stale_effect_and_stops_at_first_match(self):
        from cogs.actions import ActionsCog
        from database.schema import get_connection
        await self._player(tool=5)
        sent = AsyncMock()
        bot = MagicMock()
        bot.get_channel.return_value.send = sent
        cog = ActionsCog(bot)
        cid, _ = await self._render_confirm(cog, mode="any", effect="upgrade_success", threshold=3)
        with patch("cogs.actions.affix_manager.random.choice", side_effect=["efficiency", "cycle_time_reduce"]), patch(
            "cogs.actions.affix_manager.random.randint", side_effect=[1, 3]
        ):
            await cog.on_button_click(self._inter(cid))
        self.assertEqual(sent.await_count, 1)
        async with get_connection() as db:
            self.assertEqual(await (await db.execute("SELECT materials_research FROM players WHERE user_id='12345'")).fetchone(), (3,))
            self.assertEqual(await (await db.execute("SELECT affix_type, value FROM gear_affixes WHERE user_id='12345'")).fetchone(), ("cycle_time_reduce", 3))

    async def test_incomplete_and_malformed_confirmations_do_not_spend_or_announce(self):
        from cogs.actions import ActionsCog
        await self._player(tool=3)
        bot = MagicMock()
        sent = AsyncMock()
        bot.get_channel.return_value.send = sent
        cog = ActionsCog(bot)
        for cid in ("auto_affix_run:research:none:none:none:none:0", "auto_affix_run:research:any:bogus:1:tool:0", "auto_affix_run:research:any:none:1:tool:0:extra:0", "auto_affix_run:research:any:none:1:tool", "auto_affix_run:research:any:none:1:tool:-1"):
            await cog.on_button_click(self._inter(cid))
        malformed_select = self._inter("auto_affix_value:research:any:none:1:tool")
        malformed_select.values = []
        await cog.on_dropdown(malformed_select)
        self.assertEqual(sent.await_count, 0)
        self.assertEqual(await self.fetchone("SELECT materials_research FROM players WHERE user_id='12345'"), (3,))

    async def test_universal_exhaustion_keeps_remainder_and_emits_one_summary(self):
        from cogs.actions import ActionsCog
        await self._player(tool=8, universal=14)
        sent = AsyncMock()
        bot = MagicMock()
        bot.get_channel.return_value.send = sent
        cog = ActionsCog(bot)
        cid, _ = await self._render_confirm(cog, source="universal", threshold=2)
        with patch("cogs.actions.affix_manager.random.choice", return_value="efficiency"), patch(
            "cogs.actions.affix_manager.random.randint", return_value=1
        ):
            await cog.on_button_click(self._inter(cid))
        self.assertEqual(sent.await_count, 1)
        self.assertIn("未抽到目標詞條，抽選次數2 (10萬能素材)", sent.call_args.args[0])
        self.assertEqual(await self.fetchone("SELECT materials_research, materials_universal FROM players WHERE user_id='12345'"), (8, 4))
        self.assertIsNone(await self.fetchone("SELECT * FROM gear_affixes WHERE user_id='12345'"))

    async def test_specific_requires_both_effect_and_threshold(self):
        from cogs.actions import ActionsCog
        await self._player(tool=2)
        sent = AsyncMock()
        bot = MagicMock()
        bot.get_channel.return_value.send = sent
        cog = ActionsCog(bot)
        cid, _ = await self._render_confirm(cog, mode="specific", effect="efficiency", threshold=2)
        with patch("cogs.actions.affix_manager.random.choice", side_effect=["efficiency", "upgrade_success"]), patch(
            "cogs.actions.affix_manager.random.randint", side_effect=[1, 5]
        ):
            await cog.on_button_click(self._inter(cid))
        self.assertEqual(sent.await_count, 1)
        self.assertIn("未抽到目標詞條，抽選次數2 (2工具素材)", sent.call_args.args[0])
        self.assertEqual(await self.fetchone("SELECT materials_research FROM players WHERE user_id='12345'"), (0,))
        self.assertIsNone(await self.fetchone("SELECT * FROM gear_affixes WHERE user_id='12345'"))

    async def test_full_slot_and_selected_source_shortage_reject_without_fallback(self):
        from cogs.actions import ActionsCog
        await self._player(tool=0, universal=20)
        sent = AsyncMock()
        bot = MagicMock()
        bot.get_channel.return_value.send = sent
        async with schema.get_connection() as db:
            await db.execute("INSERT INTO gear_affixes VALUES ('12345', 'research', 0, 'efficiency', 2)")
            await db.commit()
        cog = ActionsCog(bot)
        full_id, _ = await self._render_confirm(cog, source="universal")
        await cog.on_button_click(self._inter(full_id))
        self.assertEqual(await self.fetchone("SELECT materials_universal FROM players WHERE user_id='12345'"), (20,))
        self.assertEqual(await self.fetchone("SELECT COUNT(*) FROM gear_affixes WHERE user_id='12345'"), (1,))
        async with schema.get_connection() as db:
            await db.execute("DELETE FROM gear_affixes WHERE user_id='12345'")
            await db.commit()
        empty_id, _ = await self._render_confirm(cog)
        await cog.on_button_click(self._inter(empty_id))
        self.assertEqual(await self.fetchone("SELECT materials_universal, materials_research FROM players WHERE user_id='12345'"), (20, 0))
        self.assertEqual(sent.await_count, 0)

    async def test_slot_bound_confirmation_blocks_repeat_and_allows_next_slot(self):
        from cogs.actions import ActionsCog
        await self._player(tool=4, level=10)
        sent = AsyncMock()
        bot = MagicMock()
        bot.get_channel.return_value.send = sent
        cog = ActionsCog(bot)
        first_id, _ = await self._render_confirm(cog)
        self.assertTrue(first_id.startswith("auto_affix_run:research:any:none:1:tool:0:"))
        token = first_id.rsplit(":", 1)[1]
        self.assertEqual(len(token), 8)
        self.assertTrue(all(character.isascii() and (character.isalnum() or character in "-_") for character in token))
        with patch("cogs.actions.affix_manager.random.choice", return_value="efficiency"), patch(
            "cogs.actions.affix_manager.random.randint", return_value=1
        ):
            import asyncio
            await asyncio.gather(cog.on_button_click(self._inter(first_id)), cog.on_button_click(self._inter(first_id)))
        self.assertEqual(sent.await_count, 1)
        self.assertEqual(await self.fetchone("SELECT materials_research FROM players WHERE user_id='12345'"), (3,))
        self.assertEqual(await self.fetchall("SELECT slot_index FROM gear_affixes WHERE user_id='12345' ORDER BY slot_index"), [(0,)])

        await cog.on_button_click(self._inter(first_id))
        self.assertEqual(sent.await_count, 1)
        self.assertEqual(await self.fetchone("SELECT materials_research FROM players WHERE user_id='12345'"), (3,))
        self.assertEqual(await self.fetchall("SELECT slot_index FROM gear_affixes WHERE user_id='12345' ORDER BY slot_index"), [(0,)])

        reopened = self._inter("open_auto_affix:research")
        await cog.on_button_click(reopened)
        await cog._render_auto_affix(reopened, "research", target_mode="any", min_value=1, material_source="tool")
        second_id = next(
            component.custom_id for row in reopened.edit_original_response.call_args.kwargs["components"]
            for component in row.children if component.custom_id.startswith("auto_affix_run:")
        )
        self.assertTrue(second_id.startswith("auto_affix_run:research:any:none:1:tool:1:"))
        await cog.on_button_click(self._inter(second_id))
        self.assertEqual(sent.await_count, 2)
        self.assertEqual(await self.fetchone("SELECT materials_research FROM players WHERE user_id='12345'"), (2,))
        self.assertEqual(await self.fetchall("SELECT slot_index FROM gear_affixes WHERE user_id='12345' ORDER BY slot_index"), [(0,), (1,)])

    async def test_failure_after_real_deduction_rolls_back_and_sends_nothing(self):
        from cogs.actions import ActionsCog
        from managers import player_manager
        await self._player(tool=3)
        original_spend = player_manager.spend_material
        sent = AsyncMock()
        bot = MagicMock()
        bot.get_channel.return_value.send = sent
        cog = ActionsCog(bot)
        cid, _ = await self._render_confirm(cog)
        async def deduct_then_fail(db, user_id, gear_type, amount, now):
            await original_spend(db, user_id, gear_type, amount, now)
            raise RuntimeError("injected after deduction")
        with patch("cogs.actions.affix_manager.random.choice", return_value="efficiency"), patch(
            "cogs.actions.affix_manager.random.randint", return_value=1
        ), patch("managers.player_manager.spend_material", new=deduct_then_fail):
            await cog.on_button_click(self._inter(cid))
        self.assertEqual(await self.fetchone("SELECT materials_research FROM players WHERE user_id='12345'"), (3,))
        self.assertIsNone(await self.fetchone("SELECT * FROM gear_affixes WHERE user_id='12345'"))
        self.assertEqual(sent.await_count, 0)

    async def test_commit_failure_rolls_back_and_sends_nothing(self):
        import aiosqlite
        from cogs.actions import ActionsCog
        await self._player(tool=3)
        sent = AsyncMock()
        bot = MagicMock()
        bot.get_channel.return_value.send = sent
        cog = ActionsCog(bot)
        cid, _ = await self._render_confirm(cog)
        with patch("cogs.actions.affix_manager.random.choice", return_value="efficiency"), patch(
            "cogs.actions.affix_manager.random.randint", return_value=1
        ), patch.object(aiosqlite.core.Connection, "commit", new=AsyncMock(side_effect=RuntimeError("injected commit failure"))):
            await cog.on_button_click(self._inter(cid))
        self.assertEqual(await self.fetchone("SELECT materials_research FROM players WHERE user_id='12345'"), (3,))
        self.assertIsNone(await self.fetchone("SELECT * FROM gear_affixes WHERE user_id='12345'"))
        self.assertEqual(sent.await_count, 0)

    async def test_confirmation_replay_after_clear_is_rejected_and_new_render_works(self):
        from cogs.actions import ActionsCog
        from managers import affix_manager
        from database.schema import get_connection
        await self._player(tool=4)
        sent = AsyncMock()
        bot = MagicMock()
        bot.get_channel.return_value.send = sent
        cog = ActionsCog(bot)
        cid, _ = await self._render_confirm(cog)
        with patch("cogs.actions.affix_manager.random.choice", return_value="efficiency"), patch(
            "cogs.actions.affix_manager.random.randint", return_value=3
        ):
            await cog.on_button_click(self._inter(cid))
        async with get_connection() as db:
            await affix_manager.clear_affix(db, "12345", "research", 0, 5, datetime.now(timezone.utc))
            await db.commit()
        balance_after_clear = await self.fetchone("SELECT materials_research FROM players WHERE user_id='12345'")
        await cog.on_button_click(self._inter(cid))
        self.assertEqual(await self.fetchone("SELECT materials_research FROM players WHERE user_id='12345'"), balance_after_clear)
        self.assertIsNone(await self.fetchone("SELECT * FROM gear_affixes WHERE user_id='12345'"))
        self.assertEqual(sent.await_count, 1)

        async with get_connection() as db:
            from managers import player_manager
            await player_manager.set_material(db, "12345", "research", 1, datetime.now(timezone.utc))
            await db.commit()
        new_id, _ = await self._render_confirm(cog)
        self.assertNotEqual(new_id, cid)
        with patch("cogs.actions.affix_manager.random.choice", return_value="efficiency"), patch(
            "cogs.actions.affix_manager.random.randint", return_value=3
        ):
            await cog.on_button_click(self._inter(new_id))
        self.assertEqual(sent.await_count, 2)
        self.assertEqual(await self.fetchone("SELECT COUNT(*) FROM gear_affixes WHERE user_id='12345'"), (1,))

    async def test_exhausted_confirmation_replay_after_refill_is_rejected(self):
        from cogs.actions import ActionsCog
        from database.schema import get_connection
        from managers import player_manager
        await self._player(tool=1)
        sent = AsyncMock()
        bot = MagicMock()
        bot.get_channel.return_value.send = sent
        cog = ActionsCog(bot)
        cid, _ = await self._render_confirm(cog, mode="specific", effect="efficiency", threshold=5)
        with patch("cogs.actions.affix_manager.random.choice", return_value="upgrade_success"), patch(
            "cogs.actions.affix_manager.random.randint", return_value=5
        ):
            await cog.on_button_click(self._inter(cid))
        self.assertEqual(sent.await_count, 1)
        async with get_connection() as db:
            await player_manager.set_material(db, "12345", "research", 2, datetime.now(timezone.utc))
            await db.commit()
        await cog.on_button_click(self._inter(cid))
        self.assertEqual(await self.fetchone("SELECT materials_research FROM players WHERE user_id='12345'"), (2,))
        self.assertEqual(sent.await_count, 1)
        self.assertIsNone(await self.fetchone("SELECT * FROM gear_affixes WHERE user_id='12345'"))
        new_id, _ = await self._render_confirm(cog, mode="specific", effect="efficiency", threshold=5)
        with patch("cogs.actions.affix_manager.random.choice", return_value="efficiency"), patch(
            "cogs.actions.affix_manager.random.randint", return_value=5
        ):
            await cog.on_button_click(self._inter(new_id))
        self.assertEqual(await self.fetchone("SELECT materials_research FROM players WHERE user_id='12345'"), (1,))
        self.assertEqual(sent.await_count, 2)

    async def test_returning_to_affix_management_invalidates_pending_confirmation(self):
        from cogs.actions import ActionsCog
        await self._player(tool=2)
        sent = AsyncMock()
        bot = MagicMock()
        bot.get_channel.return_value.send = sent
        cog = ActionsCog(bot)
        cid, _ = await self._render_confirm(cog)
        navigation = self._inter("back_to_affix:research")
        stale_click = self._inter(cid)

        async def replay_during_navigation_defer(*args, **kwargs):
            self.assertNotIn("12345", cog._auto_affix_confirmations)
            await cog.on_button_click(stale_click)

        navigation.response.defer = AsyncMock(side_effect=replay_during_navigation_defer)
        with patch("cogs.actions.affix_manager.random.choice", return_value="efficiency") as draw_type, patch(
            "cogs.actions.affix_manager.random.randint", return_value=1
        ) as draw_value:
            await cog.on_button_click(navigation)
        draw_type.assert_not_called()
        draw_value.assert_not_called()
        self.assertTrue(stale_click.response.defer.awaited)
        self.assertEqual(await self.fetchone("SELECT materials_research FROM players WHERE user_id='12345'"), (2,))
        self.assertIsNone(await self.fetchone("SELECT * FROM gear_affixes WHERE user_id='12345'"))
        self.assertEqual(sent.await_count, 0)
        new_id, _ = await self._render_confirm(cog)
        self.assertNotEqual(new_id, cid)
        with patch("cogs.actions.affix_manager.random.choice", return_value="efficiency"), patch(
            "cogs.actions.affix_manager.random.randint", return_value=1
        ):
            await cog.on_button_click(self._inter(new_id))
        self.assertEqual(await self.fetchone("SELECT materials_research FROM players WHERE user_id='12345'"), (1,))
        self.assertEqual(await self.fetchone("SELECT slot_index FROM gear_affixes WHERE user_id='12345'"), (0,))
        self.assertEqual(sent.await_count, 1)

    async def test_selector_change_invalidates_confirmation_before_defer(self):
        from cogs.actions import ActionsCog
        await self._player(tool=2)
        sent = AsyncMock()
        bot = MagicMock()
        bot.get_channel.return_value.send = sent
        cog = ActionsCog(bot)
        cid, page = await self._render_confirm(cog)
        selector_id = self._component_id(page, "auto_affix_kind:")
        selector = self._inter(selector_id, "specific")
        original_defer = selector.response.defer

        async def assert_consumed_before_defer(*args, **kwargs):
            self.assertNotIn("12345", cog._auto_affix_confirmations)
            await original_defer(*args, **kwargs)

        selector.response.defer = AsyncMock(side_effect=assert_consumed_before_defer)
        await cog.on_dropdown(selector)
        with patch("cogs.actions.affix_manager.random.choice", return_value="efficiency") as draw:
            await cog.on_button_click(self._inter(cid))
        draw.assert_not_called()
        self.assertEqual(await self.fetchone("SELECT materials_research FROM players WHERE user_id='12345'"), (2,))
        self.assertIsNone(await self.fetchone("SELECT * FROM gear_affixes WHERE user_id='12345'"))
        self.assertEqual(sent.await_count, 0)

    async def test_main_navigation_and_slash_reopen_invalidate_before_confirmation(self):
        from cogs.actions import ActionsCog
        await self._player(tool=3)
        sent = AsyncMock()
        bot = MagicMock()
        bot.get_channel.return_value.send = sent
        cog = ActionsCog(bot)
        first_id, _ = await self._render_confirm(cog)
        navigation = self._inter("back_to_main")
        stale_click = self._inter(first_id)

        async def replay_during_main_defer(*args, **kwargs):
            self.assertNotIn("12345", cog._auto_affix_confirmations)
            await cog.on_button_click(stale_click)

        navigation.response.defer = AsyncMock(side_effect=replay_during_main_defer)
        with patch("cogs.actions.affix_manager.random.choice", return_value="efficiency") as draw_type:
            await cog.on_button_click(navigation)
        draw_type.assert_not_called()
        self.assertEqual(await self.fetchone("SELECT materials_research FROM players WHERE user_id='12345'"), (3,))

        current_id, _ = await self._render_confirm(cog)
        slash_inter = self._inter("unused")
        stale_slash_click = self._inter(current_id)

        async def replay_during_slash_defer(*args, **kwargs):
            self.assertNotIn("12345", cog._auto_affix_confirmations)
            await cog.on_button_click(stale_slash_click)

        slash_inter.response.defer = AsyncMock(side_effect=replay_during_slash_defer)
        with patch("cogs.actions.affix_manager.random.choice", return_value="efficiency") as reopened_draw:
            await ActionsCog.idlevillage.callback(cog, slash_inter)
        reopened_draw.assert_not_called()
        self.assertEqual(await self.fetchone("SELECT materials_research FROM players WHERE user_id='12345'"), (3,))
        self.assertEqual(sent.await_count, 0)

    async def test_navigation_invalidation_is_per_user(self):
        from cogs.actions import ActionsCog
        from core.utils import dt_str
        await self._player(tool=2)
        now = dt_str(datetime.now(timezone.utc))
        async with schema.get_connection() as db:
            await db.execute(
                "INSERT INTO players (user_id, created_at, updated_at, ap_full_time, materials_research, gear_research) VALUES (?, ?, ?, ?, ?, ?)",
                ("67890", now, now, now, 2, 5),
            )
            await db.commit()
        sent = AsyncMock()
        bot = MagicMock()
        bot.get_channel.return_value.send = sent
        cog = ActionsCog(bot)
        current_id, _ = await self._render_confirm(cog)
        other_page = self._inter("open_auto_affix:research")
        other_page.user.id = 67890
        await cog.on_button_click(other_page)
        await cog._render_auto_affix(other_page, "research", target_mode="any", min_value=1, material_source="tool")
        other_id = self._component_id(other_page, "auto_affix_run:")

        await cog.on_button_click(self._inter("back_to_affix:research"))
        with patch("cogs.actions.affix_manager.random.choice", return_value="efficiency") as draw_type:
            await cog.on_button_click(self._inter(current_id))
        draw_type.assert_not_called()
        with patch("cogs.actions.affix_manager.random.choice", return_value="efficiency"), patch(
            "cogs.actions.affix_manager.random.randint", return_value=1
        ):
            other_click = self._inter(other_id)
            other_click.user.id = 67890
            await cog.on_button_click(other_click)
        self.assertEqual(await self.fetchone("SELECT materials_research FROM players WHERE user_id='12345'"), (2,))
        self.assertEqual(await self.fetchone("SELECT materials_research FROM players WHERE user_id='67890'"), (1,))
        self.assertEqual(await self.fetchall("SELECT user_id, slot_index FROM gear_affixes"), [("67890", 0)])
        self.assertEqual(sent.await_count, 1)

    async def test_obsolete_other_user_and_tampered_ids_do_not_consume_current_confirmation(self):
        from cogs.actions import ActionsCog
        await self._player(tool=2)
        sent = AsyncMock()
        bot = MagicMock()
        bot.get_channel.return_value.send = sent
        cog = ActionsCog(bot)
        old_id, _ = await self._render_confirm(cog)
        current_id, _ = await self._render_confirm(cog)
        await cog.on_button_click(self._inter(old_id))
        other_user = self._inter(current_id)
        other_user.user.id = 67890
        await cog.on_button_click(other_user)
        parts = current_id.split(":")
        parts[4] = "2" if parts[4] == "1" else "1"
        await cog.on_button_click(self._inter(":".join(parts)))
        parts = current_id.split(":")
        parts[7] = "!!!!!!!!"
        await cog.on_button_click(self._inter(":".join(parts)))
        self.assertEqual(await self.fetchone("SELECT materials_research FROM players WHERE user_id='12345'"), (2,))
        self.assertEqual(sent.await_count, 0)
        with patch("cogs.actions.affix_manager.random.choice", return_value="efficiency"), patch(
            "cogs.actions.affix_manager.random.randint", return_value=1
        ):
            await cog.on_button_click(self._inter(current_id))
        self.assertEqual(await self.fetchone("SELECT materials_research FROM players WHERE user_id='12345'"), (1,))
        self.assertEqual(sent.await_count, 1)

    async def test_kind_switch_round_trip_uses_rendered_dropdown_ids_and_retains_settings(self):
        from cogs.actions import ActionsCog
        await self._player(tool=0, universal=50)
        cog = ActionsCog(MagicMock())
        page = self._inter("open_auto_affix:research")
        await cog.on_button_click(page)
        page = await self._select_id(cog, self._component_id(page, "auto_affix_kind:"), "specific")
        page = await self._select_id(cog, self._component_id(page, "auto_affix_effect:"), "cycle_time_reduce")
        page = await self._select_id(cog, self._component_id(page, "auto_affix_value:"), "4")
        page = await self._select_id(cog, self._component_id(page, "auto_affix_material:"), "universal")
        page = await self._select_id(cog, self._component_id(page, "auto_affix_kind:"), "any")
        self.assertIn("目標種類：任意", page.edit_original_response.call_args.kwargs["embed"].description)
        page = await self._select_id(cog, self._component_id(page, "auto_affix_kind:"), "specific")
        component_ids = [component.custom_id for row in page.edit_original_response.call_args.kwargs["components"] for component in row.children]
        self.assertTrue(any(cid.startswith("auto_affix_effect:research:specific:cycle_time_reduce:4:universal") for cid in component_ids))
        self.assertTrue(any(cid.startswith("auto_affix_value:research:specific:cycle_time_reduce:4:universal") for cid in component_ids))
        self.assertTrue(any(cid.startswith("auto_affix_material:research:specific:cycle_time_reduce:4:universal") for cid in component_ids))
        self.assertEqual(await self.fetchone("SELECT materials_research, materials_universal FROM players WHERE user_id='12345'"), (0, 50))


class TestAutoToolRouteRegistration(unittest.TestCase):
    """Auto-tool interface interaction routes are registered."""

    def setUp(self):
        for k, v in ALL_TEST_ENV.items():
            os.environ[k] = v

    def test_open_auto_tool_is_own_button(self):
        from cogs.actions import _is_own_button
        self.assertTrue(_is_own_button("open_auto_tool"))

    def test_auto_tool_confirm_is_own_button(self):
        from cogs.actions import _is_own_button
        self.assertTrue(_is_own_button("auto_tool_confirm:gathering:3:none"))

    def test_auto_tool_type_select_is_own_dropdown(self):
        from cogs.actions import _is_own_dropdown
        self.assertTrue(_is_own_dropdown("auto_tool_type_select"))

    def test_auto_tool_target_select_is_own_dropdown(self):
        from cogs.actions import _is_own_dropdown
        self.assertTrue(_is_own_dropdown("auto_tool_target_select:building"))

    def test_auto_tool_add_select_is_own_dropdown(self):
        from cogs.actions import _is_own_dropdown
        self.assertTrue(_is_own_dropdown("auto_tool_add_select:gathering:none"))

    def test_auto_tool_sub_select_is_own_dropdown(self):
        from cogs.actions import _is_own_dropdown
        self.assertTrue(_is_own_dropdown("auto_tool_sub_select:gathering:none"))

    def test_affix_gear_select_is_own_dropdown(self):
        from cogs.actions import _is_own_dropdown
        self.assertTrue(_is_own_dropdown("affix_gear_select"))

    def test_affix_slot_select_is_own_dropdown(self):
        from cogs.actions import _is_own_dropdown
        self.assertTrue(_is_own_dropdown("affix_slot_select:gathering"))


class TestAdminCheck(unittest.TestCase):
    """Admin guard uses ADMIN_IDS from config."""

    def setUp(self):
        for k, v in ALL_TEST_ENV.items():
            os.environ[k] = v

    def test_admin_id_accepted(self):
        from core.config import is_admin
        # ALL_TEST_ENV has ADMIN_IDS = "151517260622594048"
        self.assertTrue(is_admin(151517260622594048))

    def test_non_admin_rejected(self):
        from core.config import is_admin
        self.assertFalse(is_admin(999999999999999999))


class TestRemovedCommandsAndRoutes(unittest.TestCase):
    """Removed UI commands and routes are no longer registered."""

    def setUp(self):
        for k, v in ALL_TEST_ENV.items():
            os.environ[k] = v

    def test_help_command_removed(self):
        from cogs.general import GeneralCog

        self.assertFalse(hasattr(GeneralCog, "help_cmd"))

    def test_refresh_button_not_owned_by_actions_cog(self):
        from cogs.actions import _is_own_button

        self.assertFalse(_is_own_button("refresh"))


class TestAffixHandlerNotification(unittest.IsolatedAsyncioTestCase):
    """extract_affix and clear_affix handlers dispatch notification events on success."""

    def setUp(self):
        for k, v in ALL_TEST_ENV.items():
            os.environ[k] = v

    def _make_inter(self, cid):
        inter = MagicMock()
        inter.guild_id = int(ALL_TEST_ENV["DISCORD_GUILD_ID"])
        inter.user.id = 12345
        inter.user.display_name = "TestUser"
        inter.component.custom_id = cid
        inter.response.defer = AsyncMock()
        inter.edit_original_response = AsyncMock()
        return inter

    def _make_db_cm(self):
        db_mock = AsyncMock()
        db_mock.commit = AsyncMock()
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=db_mock)
        cm.__aexit__ = AsyncMock(return_value=False)
        return cm

    async def test_render_affix_forwards_selected_group_to_clear_button(self):
        from cogs.actions import ActionsCog

        inter = self._make_inter("affix_gear_select")
        db_mock = AsyncMock()
        execute_cm = MagicMock()
        execute_cm.__aenter__ = AsyncMock(return_value=AsyncMock(fetchone=AsyncMock(return_value=(5, 0, 0, 0))))
        execute_cm.__aexit__ = AsyncMock(return_value=False)
        db_mock.execute = MagicMock(return_value=execute_cm)
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=db_mock)
        cm.__aexit__ = AsyncMock(return_value=False)
        upgrade_info = {"gear_level": 5, "gear_cap": 10, "materials": 0, "universal_materials": 0}
        affixes = [{"slot_index": 0, "affix_type": "efficiency", "value": 3}]
        with (
            patch("cogs.actions.get_connection", return_value=cm),
            patch("cogs.actions.gear_manager.get_upgrade_info", new=AsyncMock(return_value=upgrade_info)),
            patch("cogs.actions.affix_manager.get_affixes", new=AsyncMock(return_value=affixes)),
        ):
            await ActionsCog(bot=MagicMock())._render_affix(inter, "gathering", selected_group=("efficiency", 3))

        kwargs = inter.edit_original_response.call_args.kwargs
        buttons = {c.custom_id: c for row in kwargs["components"] for c in row.children if hasattr(c, "custom_id")}
        self.assertFalse(buttons["affix_clear:gathering:efficiency:3"].disabled)
        self.assertIn("即將清除：行動效率（+3%）", kwargs["embed"].description)

    async def test_affix_slot_select_passes_parsed_group_to_render(self):
        from cogs.actions import ActionsCog

        inter = self._make_inter("affix_slot_select:gathering")
        inter.values = ["efficiency:3"]
        with patch.object(ActionsCog, "_render_affix", new=AsyncMock()) as render:
            await ActionsCog(bot=MagicMock()).on_dropdown(inter)
        render.assert_awaited_once_with(inter, "gathering", selected_group=("efficiency", 3))

    async def test_affix_slot_select_ignores_invalid_values(self):
        from cogs.actions import ActionsCog

        for value in ("0", "bogus:3", "efficiency:6", "efficiency:x"):
            with self.subTest(value=value):
                inter = self._make_inter("affix_slot_select:gathering")
                inter.values = [value]
                with patch.object(ActionsCog, "_render_affix", new=AsyncMock()) as render:
                    await ActionsCog(bot=MagicMock()).on_dropdown(inter)
                render.assert_not_awaited()

    async def test_affix_extract_dispatches_affix_extracted_event(self):
        from cogs.actions import ActionsCog

        inter = self._make_inter("affix_extract:gathering")
        with (
            patch("cogs.actions.get_connection", return_value=self._make_db_cm()),
            patch("cogs.actions.player_manager.get_gear_level", new=AsyncMock(return_value=10)),
            patch(
                "cogs.actions.affix_manager.extract_affix",
                new=AsyncMock(return_value={"slot_index": 0, "affix_type": "efficiency", "value": 3}),
            ),
            patch("cogs.actions.notification.dispatch_events", new=AsyncMock()) as mock_dispatch,
            patch.object(ActionsCog, "_render_affix", new=AsyncMock()),
        ):
            cog = ActionsCog(bot=MagicMock())
            await cog.on_button_click(inter)

        mock_dispatch.assert_awaited_once()
        event = mock_dispatch.call_args[0][1][0]
        self.assertEqual(event["type"], "affix_extracted")
        self.assertEqual(event["user_display_name"], "TestUser")
        self.assertEqual(event["gear_type"], "gathering")
        self.assertEqual(event["affix_type"], "efficiency")
        self.assertEqual(event["value"], 3)

    async def test_affix_extract_no_dispatch_on_failure(self):
        from cogs.actions import ActionsCog

        inter = self._make_inter("affix_extract:gathering")
        with (
            patch("cogs.actions.get_connection", return_value=self._make_db_cm()),
            patch("cogs.actions.player_manager.get_gear_level", new=AsyncMock(return_value=10)),
            patch("cogs.actions.affix_manager.extract_affix", new=AsyncMock(side_effect=ValueError("full"))),
            patch("cogs.actions.notification.dispatch_events", new=AsyncMock()) as mock_dispatch,
            patch.object(ActionsCog, "_render_affix", new=AsyncMock()),
        ):
            cog = ActionsCog(bot=MagicMock())
            await cog.on_button_click(inter)

        mock_dispatch.assert_not_awaited()

    async def test_clear_affix_dispatches_affix_cleared_event(self):
        from cogs.actions import ActionsCog

        inter = self._make_inter("clear_affix:gathering:0")
        with (
            patch("cogs.actions.get_connection", return_value=self._make_db_cm()),
            patch("cogs.actions.player_manager.get_gear_level", new=AsyncMock(return_value=10)),
            patch(
                "cogs.actions.affix_manager.clear_affix",
                new=AsyncMock(return_value={"affix_type": "upgrade_success", "value": 5}),
            ),
            patch("cogs.actions.notification.dispatch_events", new=AsyncMock()) as mock_dispatch,
            patch.object(ActionsCog, "_render_gear", new=AsyncMock()),
        ):
            cog = ActionsCog(bot=MagicMock())
            await cog.on_button_click(inter)

        mock_dispatch.assert_awaited_once()
        event = mock_dispatch.call_args[0][1][0]
        self.assertEqual(event["type"], "affix_cleared")
        self.assertEqual(event["user_display_name"], "TestUser")
        self.assertEqual(event["gear_type"], "gathering")
        self.assertEqual(event["affix_type"], "upgrade_success")
        self.assertEqual(event["value"], 5)

    async def test_clear_affix_no_dispatch_on_failure(self):
        from cogs.actions import ActionsCog

        inter = self._make_inter("clear_affix:gathering:0")
        with (
            patch("cogs.actions.get_connection", return_value=self._make_db_cm()),
            patch("cogs.actions.player_manager.get_gear_level", new=AsyncMock(return_value=10)),
            patch("cogs.actions.affix_manager.clear_affix", new=AsyncMock(side_effect=ValueError("empty"))),
            patch("cogs.actions.notification.dispatch_events", new=AsyncMock()) as mock_dispatch,
            patch.object(ActionsCog, "_render_gear", new=AsyncMock()),
        ):
            cog = ActionsCog(bot=MagicMock())
            await cog.on_button_click(inter)

        mock_dispatch.assert_not_awaited()

    def _make_dropdown_inter(self, cid, value):
        inter = MagicMock()
        inter.guild_id = int(ALL_TEST_ENV["DISCORD_GUILD_ID"])
        inter.user.id = 12345
        inter.user.display_name = "TestUser"
        inter.component.custom_id = cid
        inter.values = [value]
        inter.response.defer = AsyncMock()
        inter.edit_original_response = AsyncMock()
        return inter

    async def test_affix_clear_button_dispatches_affix_cleared_event(self):
        from cogs.actions import ActionsCog

        inter = self._make_inter("affix_clear:gathering:efficiency:3")
        with (
            patch("cogs.actions.get_connection", return_value=self._make_db_cm()),
            patch("cogs.actions.player_manager.get_gear_level", new=AsyncMock(return_value=10)),
            patch(
                "cogs.actions.affix_manager.get_affixes",
                new=AsyncMock(return_value=[{"slot_index": 0, "affix_type": "efficiency", "value": 3}]),
            ),
            patch(
                "cogs.actions.affix_manager.clear_affix",
                new=AsyncMock(return_value={"affix_type": "efficiency", "value": 3}),
            ),
            patch("cogs.actions.notification.dispatch_events", new=AsyncMock()) as mock_dispatch,
            patch.object(ActionsCog, "_render_affix", new=AsyncMock()),
        ):
            cog = ActionsCog(bot=MagicMock())
            await cog.on_button_click(inter)

        mock_dispatch.assert_awaited_once()
        event = mock_dispatch.call_args[0][1][0]
        self.assertEqual(event["type"], "affix_cleared")
        self.assertEqual(event["gear_type"], "gathering")
        self.assertEqual(event["affix_type"], "efficiency")

    async def test_affix_clear_button_no_dispatch_on_failure(self):
        from cogs.actions import ActionsCog

        inter = self._make_inter("affix_clear:gathering:efficiency:3")
        with (
            patch("cogs.actions.get_connection", return_value=self._make_db_cm()),
            patch("cogs.actions.player_manager.get_gear_level", new=AsyncMock(return_value=10)),
            patch(
                "cogs.actions.affix_manager.get_affixes",
                new=AsyncMock(return_value=[{"slot_index": 0, "affix_type": "efficiency", "value": 3}]),
            ),
            patch("cogs.actions.affix_manager.clear_affix", new=AsyncMock(side_effect=ValueError("empty"))),
            patch("cogs.actions.notification.dispatch_events", new=AsyncMock()) as mock_dispatch,
            patch.object(ActionsCog, "_render_affix", new=AsyncMock()),
        ):
            cog = ActionsCog(bot=MagicMock())
            await cog.on_button_click(inter)

        mock_dispatch.assert_not_awaited()


class TestAffixClearByGroup(DatabaseTestCase):
    async def _setup(self, slots, materials=10):
        from database.schema import get_connection
        from core.utils import dt_str
        now = dt_str(datetime.now(timezone.utc))
        async with get_connection() as db:
            await db.execute(
                "INSERT INTO players (user_id, created_at, updated_at, ap_full_time, materials_gathering, gear_gathering) VALUES (?, ?, ?, ?, ?, ?)",
                ("12345", now, now, now, materials, 30),
            )
            for slot, affix_type, value in slots:
                await db.execute(
                    "INSERT INTO gear_affixes (user_id, gear_type, slot_index, affix_type, value) VALUES (?, ?, ?, ?, ?)",
                    ("12345", "gathering", slot, affix_type, value),
                )
            await db.commit()

    def _inter(self, cid):
        inter = MagicMock()
        inter.guild_id = int(ALL_TEST_ENV["DISCORD_GUILD_ID"])
        inter.user.id = 12345
        inter.user.display_name = "TestUser"
        inter.component.custom_id = cid
        inter.response.defer = AsyncMock()
        inter.edit_original_response = AsyncMock()
        return inter

    async def _click(self, cid):
        from cogs.actions import ActionsCog
        cog = ActionsCog(bot=MagicMock())
        inter = self._inter(cid)
        with (
            patch("cogs.actions.notification.dispatch_events", new=AsyncMock()) as dispatch,
            patch.object(ActionsCog, "_render_affix", new=AsyncMock()) as render,
        ):
            await cog.on_button_click(inter)
        return inter, dispatch, render

    async def _state(self):
        from database.schema import get_connection
        from managers import affix_manager
        async with get_connection() as db:
            affixes = await affix_manager.get_affixes(db, "12345", "gathering")
            async with db.execute("SELECT materials_gathering FROM players WHERE user_id='12345'") as cur:
                mats = (await cur.fetchone())[0]
        return [a["slot_index"] for a in affixes], mats

    async def test_clears_highest_slot_of_group_and_dispatches_once(self):
        await self._setup([(0, "efficiency", 3), (1, "efficiency", 2), (3, "efficiency", 3), (5, "efficiency", 3)])
        _, dispatch, render = await self._click("affix_clear:gathering:efficiency:3")
        slots, mats = await self._state()
        self.assertEqual(slots, [0, 1, 3])
        self.assertLess(mats, 10)
        dispatch.assert_awaited_once()
        event = dispatch.call_args[0][1][0]
        self.assertEqual(event["type"], "affix_cleared")
        self.assertEqual((event["affix_type"], event["value"]), ("efficiency", 3))
        render.assert_awaited_once()

    async def test_missing_group_does_not_clear_spend_or_dispatch(self):
        await self._setup([(0, "efficiency", 2)])
        _, dispatch, render = await self._click("affix_clear:gathering:efficiency:3")
        slots, mats = await self._state()
        self.assertEqual(slots, [0])
        self.assertEqual(mats, 10)
        dispatch.assert_not_awaited()
        render.assert_awaited_once()

    async def test_invalid_group_is_ignored(self):
        await self._setup([(0, "efficiency", 3)])
        for cid in (
            "affix_clear:gathering:none:none",
            "affix_clear:gathering:0",
            "affix_clear:gathering:bogus:3",
            "affix_clear:gathering:efficiency:6",
            "affix_clear:gathering:efficiency:x",
            "affix_clear:bogus:efficiency:3",
        ):
            inter, dispatch, render = await self._click(cid)
            inter.response.defer.assert_not_awaited()
            dispatch.assert_not_awaited()
            render.assert_not_awaited()
        slots, mats = await self._state()
        self.assertEqual((slots, mats), ([0], 10))


class TestSacrificeModalSubmit(unittest.IsolatedAsyncioTestCase):
    """on_modal_submit handles modal_sacrifice:{gear_type} correctly."""

    def setUp(self):
        for k, v in ALL_TEST_ENV.items():
            os.environ[k] = v

    def _make_modal_inter(self, cid, amount_value):
        inter = MagicMock()
        inter.guild_id = int(ALL_TEST_ENV["DISCORD_GUILD_ID"])
        inter.user.id = 12345
        inter.custom_id = cid
        inter.text_values = {"sacrifice_amount": amount_value}
        inter.response.defer = AsyncMock()
        inter.edit_original_response = AsyncMock()
        return inter

    def _make_db_cm(self):
        db_mock = AsyncMock()
        db_mock.commit = AsyncMock()
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=db_mock)
        cm.__aexit__ = AsyncMock(return_value=False)
        return cm

    async def test_modal_submit_calls_sacrifice_and_renders(self):
        from cogs.actions import ActionsCog

        inter = self._make_modal_inter("modal_sacrifice:gathering", "3")
        sacrifice_result = {"type": "sacrifice", "sacrificed": 3, "gear_type": "gathering", "risky_failed_levels_after": 3}
        with (
            patch("cogs.actions.get_connection", return_value=self._make_db_cm()),
            patch("cogs.actions.gear_manager.sacrifice_material", new=AsyncMock(return_value=sacrifice_result)),
            patch.object(ActionsCog, "_render_gear", new=AsyncMock()) as mock_render,
        ):
            cog = ActionsCog(bot=MagicMock())
            await cog.on_modal_submit(inter)

        mock_render.assert_awaited_once()
        _, kwargs = mock_render.call_args
        self.assertEqual(kwargs.get("result"), sacrifice_result)

    async def test_modal_submit_invalid_input_returns_error_result(self):
        from cogs.actions import ActionsCog

        inter = self._make_modal_inter("modal_sacrifice:gathering", "not_a_number")
        with (
            patch("cogs.actions.get_connection", return_value=self._make_db_cm()),
            patch("cogs.actions.gear_manager.sacrifice_material", new=AsyncMock()),
            patch.object(ActionsCog, "_render_gear", new=AsyncMock()) as mock_render,
        ):
            cog = ActionsCog(bot=MagicMock())
            await cog.on_modal_submit(inter)

        mock_render.assert_awaited_once()
        _, kwargs = mock_render.call_args
        self.assertIn("error", kwargs.get("result", {}))

    async def test_modal_submit_does_not_dispatch_notification(self):
        from cogs.actions import ActionsCog

        inter = self._make_modal_inter("modal_sacrifice:gathering", "5")
        sacrifice_result = {"type": "sacrifice", "sacrificed": 5, "gear_type": "gathering", "risky_failed_levels_after": 5}
        with (
            patch("cogs.actions.get_connection", return_value=self._make_db_cm()),
            patch("cogs.actions.gear_manager.sacrifice_material", new=AsyncMock(return_value=sacrifice_result)),
            patch("cogs.actions.notification.dispatch_events", new=AsyncMock()) as mock_dispatch,
            patch.object(ActionsCog, "_render_gear", new=AsyncMock()),
        ):
            cog = ActionsCog(bot=MagicMock())
            await cog.on_modal_submit(inter)

        mock_dispatch.assert_not_awaited()


class TestSacrificeButton(unittest.TestCase):
    """Sacrifice material button in gear components and embed result display."""

    def setUp(self):
        for k, v in ALL_TEST_ENV.items():
            os.environ[k] = v

    def _player_gear(self, level=3):
        return {"gathering": level, "building": 0, "combat": 0, "research": 0}

    def test_sacrifice_button_present(self):
        from cogs.ui_renderer import build_gear_components
        rows = build_gear_components("gathering", "normal", True, self._player_gear(), gear_cap=10, materials=5)
        custom_ids = [c.custom_id for row in rows for c in row.children]
        self.assertIn("sacrifice_material:gathering", custom_ids)

    def test_sacrifice_button_disabled_when_no_materials(self):
        from cogs.ui_renderer import build_gear_components
        rows = build_gear_components("gathering", "normal", True, self._player_gear(), gear_cap=10, materials=0)
        buttons = {c.custom_id: c for row in rows for c in row.children}
        self.assertTrue(buttons["sacrifice_material:gathering"].disabled)

    def test_sacrifice_button_enabled_when_materials_available(self):
        from cogs.ui_renderer import build_gear_components
        rows = build_gear_components("gathering", "normal", True, self._player_gear(), gear_cap=10, materials=3)
        buttons = {c.custom_id: c for row in rows for c in row.children}
        self.assertFalse(buttons["sacrifice_material:gathering"].disabled)

    def test_sacrifice_result_shown_in_embed(self):
        from cogs.ui_renderer import build_gear_embed
        info = {"gear_level": 3, "target_level": 4, "rate": 0.7, "pity": 0,
                "material_cost": 4, "ap": 5, "materials": 10, "gear_cap": 10, "mode": "normal",
                "risky_failed_levels": 0, "risky_bonus_pct": 0.0, "can_attempt": True}
        result = {"type": "sacrifice", "sacrificed": 5, "gear_type": "gathering", "risky_failed_levels_after": 5}
        embed = build_gear_embed(info, "gathering", result)
        self.assertIn("🩸 獻祭完成", embed.description)
        self.assertIn("消耗 5 個", embed.description)


class TestGearUpgradeNotificationTargetLevel(unittest.IsolatedAsyncioTestCase):
    """Gear upgrade success notification must use actual new_level, not fixed current+1."""

    def setUp(self):
        for k, v in ALL_TEST_ENV.items():
            os.environ[k] = v

    def _make_inter(self):
        inter = MagicMock()
        inter.guild_id = int(ALL_TEST_ENV["DISCORD_GUILD_ID"])
        inter.user.id = 12345
        inter.user.display_name = "TestUser"
        inter.component.custom_id = "attempt_upgrade:gathering"
        inter.response.defer = AsyncMock()
        inter.edit_original_response = AsyncMock()
        return inter

    def _make_db_cm(self):
        db_mock = AsyncMock()
        db_mock.commit = AsyncMock()
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=db_mock)
        cm.__aexit__ = AsyncMock(return_value=False)
        return cm

    async def test_success_notification_target_level_uses_new_level(self):
        """When risky success yields level_gain=2, notification target_level == new_level (not current+1)."""
        from cogs.actions import ActionsCog

        inter = self._make_inter()
        upgrade_result = {
            "success": True,
            "current_level": 5,
            "new_level": 7,
            "level_gain": 2,
            "target_level": 6,  # old fixed value; should NOT be used for success notification
            "pity_before": 0,
            "pity_after": 0,
            "rate": 0.5,
            "mode": "risky",
        }
        with (
            patch("cogs.actions.get_connection", return_value=self._make_db_cm()),
            patch("cogs.actions.gear_manager.attempt_upgrade", new=AsyncMock(return_value=upgrade_result)),
            patch("cogs.actions.gear_manager.get_upgrade_info", new=AsyncMock(return_value={})),
            patch("cogs.actions.notification.dispatch_events", new=AsyncMock()) as mock_dispatch,
            patch.object(ActionsCog, "_render_gear", new=AsyncMock()),
        ):
            cog = ActionsCog(bot=MagicMock())
            await cog.on_button_click(inter)

        mock_dispatch.assert_awaited_once()
        event = mock_dispatch.call_args[0][1][0]
        self.assertEqual(event["type"], "gear_success")
        self.assertEqual(event["target_level"], 7)


class TestRankingCommand(unittest.IsolatedAsyncioTestCase):
    """/idlevillage-ranking slash command integration."""

    def setUp(self):
        for k, v in ALL_TEST_ENV.items():
            os.environ[k] = v

    def _make_inter(self):
        inter = MagicMock()
        inter.guild_id = int(ALL_TEST_ENV["DISCORD_GUILD_ID"])
        inter.guild = MagicMock()
        inter.guild.fetch_member = AsyncMock(return_value=None)
        inter.response.send_message = AsyncMock()
        inter.response.defer = AsyncMock()
        inter.edit_original_response = AsyncMock()
        return inter

    def _make_db_cm(self, rankings=None):
        db_mock = AsyncMock()
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=db_mock)
        cm.__aexit__ = AsyncMock(return_value=False)
        if rankings is not None:
            from unittest.mock import patch
            pass
        return cm, db_mock

    async def test_ranking_sends_ephemeral_message(self):
        from cogs.actions import ActionsCog
        inter = self._make_inter()
        rankings = {"gathering": [("111111111111111111", 5)], "building": [], "combat": [], "research": []}
        cm, _ = self._make_db_cm()
        with (
            patch("cogs.actions.get_connection", return_value=cm),
            patch("cogs.actions.player_manager.get_gear_rankings", new=AsyncMock(return_value=rankings)),
        ):
            cog = ActionsCog(bot=MagicMock())
            await ActionsCog.idlevillage_ranking.callback(cog, inter)
        inter.response.defer.assert_awaited_once()
        inter.edit_original_response.assert_awaited_once()

    async def test_ranking_wrong_guild_rejected(self):
        from cogs.actions import ActionsCog
        inter = self._make_inter()
        inter.guild_id = 999999999
        cog = ActionsCog(bot=MagicMock())
        await ActionsCog.idlevillage_ranking.callback(cog, inter)
        inter.response.send_message.assert_awaited_once()
        call_args = inter.response.send_message.call_args
        self.assertIn("僅限指定伺服器", call_args[0][0])

    async def test_ranking_overflow_truncated(self):
        from cogs.actions import ActionsCog
        inter = self._make_inter()
        long_entries = [(str(100000000000000000 + i), 99) for i in range(200)]
        name_map_data = {str(100000000000000000 + i): f"Player{'x' * 30}{i}" for i in range(200)}
        inter.guild.get_member = MagicMock(side_effect=lambda uid: MagicMock(display_name=name_map_data.get(str(uid), str(uid))))
        rankings = {"gathering": long_entries, "building": [], "combat": [], "research": []}
        cm, _ = self._make_db_cm()
        with (
            patch("cogs.actions.get_connection", return_value=cm),
            patch("cogs.actions.player_manager.get_gear_rankings", new=AsyncMock(return_value=rankings)),
        ):
            cog = ActionsCog(bot=MagicMock())
            await ActionsCog.idlevillage_ranking.callback(cog, inter)
        text = inter.edit_original_response.call_args[1]["content"]
        self.assertLessEqual(len(text), 1915)
        self.assertIn("省略", text)


class TestBuildRankingText(unittest.TestCase):
    """build_ranking_text formats sliced rankings as plain text."""

    def setUp(self):
        for k, v in ALL_TEST_ENV.items():
            os.environ[k] = v

    def _build(self, sliced, name_map=None):
        from cogs.ui_renderer import build_ranking_text
        return build_ranking_text(sliced, name_map or {})

    def test_standard_top_three(self):
        sliced = {
            "gathering": [("u1", 5), ("u2", 4), ("u3", 3)],
            "building": [], "combat": [], "research": [],
        }
        text = self._build(sliced, {"u1": "Alice", "u2": "Bob", "u3": "Carol"})
        self.assertIn("🌾採集工具:\n- Lv5: Alice\n- Lv4: Bob\n- Lv3: Carol", text)

    def test_no_players_shows_placeholder(self):
        sliced = {"gathering": [], "building": [], "combat": [], "research": []}
        text = self._build(sliced)
        self.assertIn("🌾採集工具:\n- （尚無玩家）", text)
        self.assertIn("🔨建設工具:\n- （尚無玩家）", text)

    def test_same_level_multiple_players(self):
        sliced = {
            "gathering": [("a", 5), ("b", 5), ("c", 4)],
            "building": [], "combat": [], "research": [],
        }
        text = self._build(sliced, {"a": "A", "b": "B", "c": "C"})
        self.assertIn("- Lv5: A", text)
        self.assertIn("- Lv5: B", text)
        self.assertIn("- Lv4: C", text)

    def test_gear_order_gathering_building_combat_research(self):
        sliced = {"gathering": [], "building": [], "combat": [], "research": []}
        text = self._build(sliced)
        idx_g = text.index("採集工具")
        idx_b = text.index("建設工具")
        idx_c = text.index("狩獵工具")
        idx_r = text.index("研究工具")
        self.assertLess(idx_g, idx_b)
        self.assertLess(idx_b, idx_c)
        self.assertLess(idx_c, idx_r)

    def test_combat_type_uses_gear_label_not_action_label(self):
        sliced = {"gathering": [], "building": [], "combat": [("u1", 3)], "research": []}
        text = self._build(sliced, {"u1": "X"})
        self.assertIn("狩獵工具", text)
        self.assertNotIn("戰鬥:", text)

    def test_missing_user_id_falls_back_to_raw_id(self):
        sliced = {"gathering": [("unknown_id", 3)], "building": [], "combat": [], "research": []}
        text = self._build(sliced, {})
        self.assertIn("- Lv3: unknown_id", text)


class TestSliceTopLevels(unittest.TestCase):
    """slice_top_levels returns top top_n players, extended if boundary level is tied."""

    def setUp(self):
        for k, v in ALL_TEST_ENV.items():
            os.environ[k] = v

    def _slice(self, entries, top_n=3):
        from managers.player_manager import slice_top_levels
        return slice_top_levels(entries, top_n)

    def test_empty_list(self):
        self.assertEqual(self._slice([]), [])

    def test_fewer_than_top_n_entries(self):
        entries = [("a", 5), ("b", 3)]
        self.assertEqual(self._slice(entries), [("a", 5), ("b", 3)])

    def test_exactly_top_n_entries_no_tie(self):
        entries = [("a", 5), ("b", 4), ("c", 3)]
        self.assertEqual(self._slice(entries), [("a", 5), ("b", 4), ("c", 3)])

    def test_fourth_entry_excluded_when_different_level(self):
        entries = [("a", 5), ("b", 4), ("c", 3), ("d", 2)]
        self.assertEqual(self._slice(entries), [("a", 5), ("b", 4), ("c", 3)])

    def test_tie_at_boundary_extends_result(self):
        # 3rd and 4th share same level → 4th is included
        entries = [("a", 5), ("b", 4), ("c", 3), ("d", 3)]
        self.assertEqual(self._slice(entries), [("a", 5), ("b", 4), ("c", 3), ("d", 3)])

    def test_no_tie_extension_when_boundary_unique(self):
        # multiple ties at top, but boundary (3rd entry) level is not shared by 4th
        entries = [("a", 5), ("b", 5), ("c", 5), ("d", 4), ("e", 3)]
        self.assertEqual(self._slice(entries), [("a", 5), ("b", 5), ("c", 5)])

    def test_top_n_1_tie_extends(self):
        entries = [("a", 5), ("b", 5), ("c", 4), ("d", 3)]
        result = self._slice(entries, top_n=1)
        self.assertEqual(result, [("a", 5), ("b", 5)])

    def test_all_same_level(self):
        entries = [("a", 3), ("b", 3), ("c", 3)]
        self.assertEqual(self._slice(entries), [("a", 3), ("b", 3), ("c", 3)])


class TestGetGearRankings(DatabaseTestCase):
    """get_gear_rankings queries all players and returns sorted per-type rankings."""

    async def _insert_player(self, db, user_id, gear_gathering=0, gear_building=0, gear_combat=0, gear_research=0):
        from core.utils import dt_str
        from datetime import datetime, timezone
        now = dt_str(datetime.now(timezone.utc))
        await db.execute(
            """INSERT OR IGNORE INTO players
               (user_id, created_at, updated_at, ap_full_time,
                gear_gathering, gear_building, gear_combat, gear_research)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (user_id, now, now, now, gear_gathering, gear_building, gear_combat, gear_research),
        )

    async def test_no_players_returns_empty_lists(self):
        from managers.player_manager import get_gear_rankings
        from database.schema import get_connection
        async with get_connection() as db:
            rankings = await get_gear_rankings(db)
        for gear_type in ("gathering", "building", "combat", "research"):
            self.assertEqual(rankings[gear_type], [])

    async def test_level_zero_filtered(self):
        from managers.player_manager import get_gear_rankings
        from database.schema import get_connection
        async with get_connection() as db:
            await self._insert_player(db, "u1", gear_gathering=0)
            await db.commit()
            rankings = await get_gear_rankings(db)
        self.assertEqual(rankings["gathering"], [])

    async def test_single_player_appears(self):
        from managers.player_manager import get_gear_rankings
        from database.schema import get_connection
        async with get_connection() as db:
            await self._insert_player(db, "u1", gear_gathering=5)
            await db.commit()
            rankings = await get_gear_rankings(db)
        self.assertEqual(rankings["gathering"], [("u1", 5)])

    async def test_sorted_level_desc_user_id_asc(self):
        from managers.player_manager import get_gear_rankings
        from database.schema import get_connection
        async with get_connection() as db:
            await self._insert_player(db, "z_user", gear_gathering=3)
            await self._insert_player(db, "a_user", gear_gathering=5)
            await self._insert_player(db, "m_user", gear_gathering=3)
            await db.commit()
            rankings = await get_gear_rankings(db)
        self.assertEqual(rankings["gathering"], [("a_user", 5), ("m_user", 3), ("z_user", 3)])

    async def test_all_gear_types_present(self):
        from managers.player_manager import get_gear_rankings
        from database.schema import get_connection
        async with get_connection() as db:
            await self._insert_player(db, "u1", gear_gathering=1, gear_building=2, gear_combat=3, gear_research=4)
            await db.commit()
            rankings = await get_gear_rankings(db)
        self.assertEqual(rankings["gathering"], [("u1", 1)])
        self.assertEqual(rankings["building"], [("u1", 2)])
        self.assertEqual(rankings["combat"], [("u1", 3)])
        self.assertEqual(rankings["research"], [("u1", 4)])


class AutoToolMainInterface(unittest.TestCase):
    def setUp(self):
        for k, v in ALL_TEST_ENV.items():
            os.environ[k] = v

    def _player(self):
        return {"_ap": 1, "action": "research", "gear_gathering": 1,
                "gear_building": 1, "gear_combat": 1, "gear_research": 1}

    def _all(self, rows):
        return [c for row in rows for c in row.children]

    def test_main_has_auto_tool_button(self):
        from cogs.ui_renderer import build_main_components
        rows = build_main_components(self._player(), {"research_lab": {"level": 3}})
        ids = [getattr(c, "custom_id", None) for c in self._all(rows)]
        self.assertIn("open_auto_tool", ids)

    def test_action_dropdown_excludes_active_auto_tools(self):
        from cogs.ui_renderer import build_main_components
        rows = build_main_components(
            self._player(), {"research_lab": {"level": 3}}, active_auto_tools={"gathering", "combat"}
        )
        select = next(c for c in self._all(rows) if getattr(c, "custom_id", None) == "action_select")
        values = {o.value for o in select.options}
        self.assertNotIn("gathering", values)
        self.assertNotIn("combat", values)
        self.assertIn("building", values)
        self.assertIn("research", values)


class AutoToolSubInterface(unittest.TestCase):
    def setUp(self):
        for k, v in ALL_TEST_ENV.items():
            os.environ[k] = v

    def _all(self, rows):
        return [c for row in rows for c in row.children]

    def test_embed_lists_running_tools_with_expiry_and_material_runway(self):
        from cogs.ui_renderer import build_auto_tool_embed
        rows = [{"tool_type": "gathering", "action_target": None, "expires_at": "2025-01-01T13:00:00+00:00"}]
        embed = build_auto_tool_embed(rows, 24, materials={"gathering": 3})
        self.assertIn("採集工具", embed.description)
        self.assertIn("<t:", embed.description)
        self.assertIn("素材可撐 3 小時", embed.description)

    def test_embed_when_no_running_tools(self):
        from cogs.ui_renderer import build_auto_tool_embed
        embed = build_auto_tool_embed([], 24)
        self.assertIn("沒有運行中", embed.description)

    def test_embed_shows_error_when_provided(self):
        from cogs.ui_renderer import build_auto_tool_embed
        embed = build_auto_tool_embed([], 24, error="⚠️ 操作失敗")
        self.assertIn("⚠️ 操作失敗", embed.description)

    def test_tool_dropdown_lists_idle_and_running(self):
        from cogs.ui_renderer import build_auto_tool_components
        rows = build_auto_tool_components(
            ["building", "combat"],
            [{"tool_type": "gathering", "action_target": None, "expires_at": "2025-01-01T13:00:00+00:00"}],
        )
        select = next(c for c in self._all(rows) if getattr(c, "custom_id", None) == "auto_tool_type_select")
        values = {o.value for o in select.options}
        self.assertEqual(values, {"gathering", "building", "combat"})

    def test_start_hours_dropdown_capped_at_max_add(self):
        from cogs.ui_renderer import build_auto_tool_components
        rows = build_auto_tool_components(
            ["gathering"], [], selected_tool="gathering", max_add=3
        )
        select = next(c for c in self._all(rows)
                      if getattr(c, "custom_id", "").startswith("auto_tool_add_select"))
        values = [o.value for o in select.options]
        self.assertEqual(values, ["1", "2", "3"])

    def test_running_tool_shows_add_and_subtract_selects(self):
        from cogs.ui_renderer import build_auto_tool_components
        rows = build_auto_tool_components(
            ["building", "combat"],
            [{"tool_type": "gathering", "action_target": None, "expires_at": "2025-01-01T13:00:00+00:00"}],
            selected_tool="gathering", max_add=23, max_subtract=2,
        )
        ids = [getattr(c, "custom_id", "") for c in self._all(rows)]
        self.assertTrue(any(i.startswith("auto_tool_add_select") for i in ids))
        sub = next(c for c in self._all(rows)
                   if getattr(c, "custom_id", "").startswith("auto_tool_sub_select"))
        values = [o.value for o in sub.options]
        self.assertEqual(values, ["-1", "-2"])
        # bottom subtract step is labelled as a stop
        self.assertIn("停止", sub.options[-1].label)

    def test_confirm_disabled_until_ready(self):
        from cogs.ui_renderer import build_auto_tool_components
        rows = build_auto_tool_components(["gathering"], [], selected_tool="gathering", max_add=24)
        confirm = next(c for c in self._all(rows)
                       if getattr(c, "custom_id", "").startswith("auto_tool_confirm"))
        self.assertTrue(confirm.disabled)  # no hours chosen yet

    def test_confirm_ready_encodes_start_hours(self):
        from cogs.ui_renderer import build_auto_tool_components
        rows = build_auto_tool_components(
            ["gathering"], [], selected_tool="gathering", selected_delta=2, max_add=24
        )
        confirm = next(c for c in self._all(rows)
                       if getattr(c, "custom_id", "").startswith("auto_tool_confirm"))
        self.assertFalse(confirm.disabled)
        self.assertEqual(confirm.custom_id, "auto_tool_confirm:gathering:2:none")

    def test_confirm_encodes_negative_delta_for_subtract(self):
        from cogs.ui_renderer import build_auto_tool_components
        rows = build_auto_tool_components(
            ["building", "combat"],
            [{"tool_type": "gathering", "action_target": None, "expires_at": "2025-01-01T13:00:00+00:00"}],
            selected_tool="gathering", selected_delta=-2, max_add=23, max_subtract=2,
        )
        confirm = next(c for c in self._all(rows)
                       if getattr(c, "custom_id", "").startswith("auto_tool_confirm"))
        self.assertFalse(confirm.disabled)
        self.assertEqual(confirm.custom_id, "auto_tool_confirm:gathering:-2:none")

    def test_building_requires_target_and_shows_target_dropdown(self):
        from cogs.ui_renderer import build_auto_tool_components
        rows = build_auto_tool_components(
            ["building"], [], selected_tool="building", selected_delta=1, max_add=24
        )
        ids = [getattr(c, "custom_id", "") for c in self._all(rows)]
        self.assertTrue(any(i.startswith("auto_tool_target_select") for i in ids))
        confirm = next(c for c in self._all(rows)
                       if getattr(c, "custom_id", "").startswith("auto_tool_confirm"))
        self.assertTrue(confirm.disabled)  # target not chosen

    def test_building_ready_with_target(self):
        from cogs.ui_renderer import build_auto_tool_components
        rows = build_auto_tool_components(
            ["building"], [], selected_tool="building", selected_target="workshop",
            selected_delta=1, max_add=24,
        )
        confirm = next(c for c in self._all(rows)
                       if getattr(c, "custom_id", "").startswith("auto_tool_confirm"))
        self.assertFalse(confirm.disabled)
        self.assertEqual(confirm.custom_id, "auto_tool_confirm:building:1:workshop")


class TestAutoToolConfirmHandler(DatabaseTestCase):
    """auto_tool_confirm routes signed delta to start / add_time / subtract_time."""

    USER = 55566677788

    def _make_inter(self, cid):
        inter = MagicMock()
        inter.guild_id = int(ALL_TEST_ENV["DISCORD_GUILD_ID"])
        inter.component.custom_id = cid
        inter.user.id = self.USER
        inter.user.display_name = "AutoUser"
        inter.response.defer = AsyncMock()
        inter.edit_original_response = AsyncMock()
        return inter

    async def _seed_player(self, **materials):
        from database.schema import get_connection
        now = datetime.now(timezone.utc).isoformat()
        async with get_connection() as db:
            await db.execute(
                "INSERT OR IGNORE INTO players (user_id, ap_full_time, created_at, updated_at) VALUES (?,?,?,?)",
                (str(self.USER), now, now, now),
            )
            for col, amt in materials.items():
                await db.execute(
                    f"UPDATE players SET {col}=? WHERE user_id=?", (amt, str(self.USER))
                )
            await db.commit()

    async def _active(self):
        row = await self.fetchone(
            "SELECT expires_at FROM player_auto_tools WHERE user_id=? AND tool_type='gathering'",
            (str(self.USER),),
        )
        return row

    async def test_confirm_starts_idle_tool_and_spends_one_material(self):
        from cogs.actions import ActionsCog
        await self._seed_player(materials_gathering=3)
        inter = self._make_inter("auto_tool_confirm:gathering:5:none")
        cog = ActionsCog(bot=MagicMock())
        await cog.on_button_click(inter)
        self.assertIsNotNone(await self._active())
        mat = await self.fetchone(
            "SELECT materials_gathering FROM players WHERE user_id=?", (str(self.USER),)
        )
        self.assertEqual(mat[0], 2)  # only 1 spent up front regardless of 5 hours

    async def test_confirm_positive_delta_adds_time_without_spending(self):
        from cogs.actions import ActionsCog
        await self._seed_player(materials_gathering=3)
        cog = ActionsCog(bot=MagicMock())
        await cog.on_button_click(self._make_inter("auto_tool_confirm:gathering:1:none"))
        before = (await self._active())[0]
        await cog.on_button_click(self._make_inter("auto_tool_confirm:gathering:2:none"))
        after = (await self._active())[0]
        self.assertGreater(after, before)  # extended
        mat = await self.fetchone(
            "SELECT materials_gathering FROM players WHERE user_id=?", (str(self.USER),)
        )
        self.assertEqual(mat[0], 2)  # add_time spent nothing beyond the initial start

    async def test_confirm_negative_delta_to_bottom_stops_tool(self):
        from cogs.actions import ActionsCog
        await self._seed_player(materials_gathering=3)
        cog = ActionsCog(bot=MagicMock())
        await cog.on_button_click(self._make_inter("auto_tool_confirm:gathering:1:none"))
        self.assertIsNotNone(await self._active())
        await cog.on_button_click(self._make_inter("auto_tool_confirm:gathering:-1:none"))
        self.assertIsNone(await self._active())  # subtract-to-bottom stopped it

    async def test_confirm_start_with_no_material_shows_error(self):
        from cogs.actions import ActionsCog
        await self._seed_player(materials_gathering=0)
        inter = self._make_inter("auto_tool_confirm:gathering:5:none")
        cog = ActionsCog(bot=MagicMock())
        await cog.on_button_click(inter)
        self.assertIsNone(await self._active())
        embed = inter.edit_original_response.call_args.kwargs["embed"]
        self.assertIn("操作失敗", embed.description)


if __name__ == "__main__":
    unittest.main()

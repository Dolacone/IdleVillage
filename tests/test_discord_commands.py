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

    def test_embed_gear_levels_shown(self):
        from cogs.ui_renderer import build_main_embed
        player = self._make_player()
        player["gear_building"] = 3
        embed = build_main_embed(self._make_stage_data(), {}, {}, [], player)
        self.assertIn("🏅 裝備：🌾 0 | 🔨 3 | ⚔️ 0 | 🔬 0", embed.description)
        self.assertIn("🎒 素材：🌾 3 | 🔨 2 | ⚔️ 1 | 🔬 0", embed.description)

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
        self.assertLess(embed.description.index("📊 效率"), embed.description.index("🏅 裝備"))


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

    def test_gear_upgrade_disabled_when_all_gear_at_cap(self):
        from cogs.ui_renderer import build_main_components

        buildings = {"research_lab": {"level": 2, "xp_progress": 0}}
        rows = build_main_components(self._make_player(ap=1, gear_level=2), buildings)
        gear_button = next(
            component
            for row in rows
            for component in row.children
            if getattr(component, "custom_id", None) == "open_gear_upgrade"
        )

        self.assertTrue(
            gear_button.disabled,
            "Gear upgrade button should be disabled when all gear is at research-lab cap",
        )

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

        self.assertEqual(first_row_ids, ["burst_execute", "open_gear_upgrade"])
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

    def _make_info(self, gear_level=2, pity=1, ap=3, materials=5):
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


class TestRendererGearComponents(unittest.TestCase):
    """build_gear_components shows documented gear option descriptions."""

    def setUp(self):
        for k, v in ALL_TEST_ENV.items():
            os.environ[k] = v

    def test_gear_options_show_level_transition_descriptions(self):
        from cogs.ui_renderer import build_gear_components

        player_gear = {"gathering": 1, "building": 0, "combat": 2, "research": 1}
        rows = build_gear_components("combat", True, player_gear, gear_cap=5)
        gear_select = rows[0].children[0]
        descriptions = {option.value: option.description for option in gear_select.options}

        self.assertEqual(descriptions["gathering"], "Lv1 → Lv2: 採集產出 +5% → +10%")
        self.assertEqual(descriptions["building"], "Lv0 → Lv1: 建設產出 +0% → +5%")
        self.assertEqual(descriptions["combat"], "Lv2 → Lv3: 戰鬥產出 +10% → +15%")

    def test_gear_options_show_cap_description(self):
        from cogs.ui_renderer import build_gear_components

        player_gear = {"gathering": 3, "building": 1, "combat": 0, "research": 2}
        rows = build_gear_components("gathering", False, player_gear, gear_cap=3)
        gear_select = rows[0].children[0]
        descriptions = {option.value: option.description for option in gear_select.options}

        self.assertEqual(descriptions["gathering"], "已達等級上限 Lv3")


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


if __name__ == "__main__":
    unittest.main()

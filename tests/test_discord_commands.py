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
        self.assertIn("🏅 工具：🌾 0 | 🔨 3 | ⚔️ 0 | 🔬 0", embed.description)
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
        self.assertLess(embed.description.index("📊 效率"), embed.description.index("🏅 工具"))


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
        self.assertIn("空槽", embed.description)

    def test_filled_slot_shows_affix_type_and_value(self):
        from cogs.ui_renderer import build_gear_embed
        affixes = [{"slot_index": 0, "affix_type": "efficiency", "value": 3}]
        embed = build_gear_embed(self._make_info(gear_level=5), "gathering", affixes=affixes, max_slots=1)
        self.assertIn("詞條槽（1/1）", embed.description)
        self.assertIn("效率 +3%", embed.description)

    def test_multiple_slots_mixed(self):
        from cogs.ui_renderer import build_gear_embed
        affixes = [{"slot_index": 0, "affix_type": "cycle_time_reduce", "value": 2}]
        embed = build_gear_embed(self._make_info(gear_level=10), "gathering", affixes=affixes, max_slots=2)
        self.assertIn("詞條槽（1/2）", embed.description)
        self.assertIn("週期縮短 +2%", embed.description)
        self.assertIn("空槽", embed.description)

    def test_upgrade_cost_reduce_slot_uses_negative_sign(self):
        from cogs.ui_renderer import build_gear_embed
        affixes = [{"slot_index": 0, "affix_type": "upgrade_cost_reduce", "value": 5}]
        embed = build_gear_embed(self._make_info(gear_level=5), "gathering", affixes=affixes, max_slots=1)
        self.assertIn("強化素材減免 -5%", embed.description)
        self.assertNotIn("+5%", embed.description)


class TestAffixComponents(unittest.TestCase):
    """Affix extract/clear buttons in gear components."""

    def setUp(self):
        for k, v in ALL_TEST_ENV.items():
            os.environ[k] = v

    def _player_gear(self, level=5):
        return {"gathering": level, "building": 0, "combat": 0, "research": 0}

    def test_no_slots_no_affix_row(self):
        from cogs.ui_renderer import build_gear_components
        rows = build_gear_components("gathering", "normal", True, self._player_gear(), gear_cap=10, max_slots=0)
        custom_ids = [c.custom_id for row in rows for c in row.children]
        self.assertFalse(any("extract_affix" in cid for cid in custom_ids))

    def test_extract_button_present_when_slots_unlocked(self):
        from cogs.ui_renderer import build_gear_components
        rows = build_gear_components("gathering", "normal", True, self._player_gear(), gear_cap=10, affixes=[], max_slots=1)
        custom_ids = [c.custom_id for row in rows for c in row.children]
        self.assertIn("extract_affix:gathering", custom_ids)

    def test_extract_disabled_when_full(self):
        from cogs.ui_renderer import build_gear_components
        affixes = [{"slot_index": 0, "affix_type": "efficiency", "value": 3}]
        rows = build_gear_components("gathering", "normal", True, self._player_gear(), gear_cap=10, affixes=affixes, max_slots=1)
        buttons = {c.custom_id: c for row in rows for c in row.children}
        self.assertTrue(buttons["extract_affix:gathering"].disabled)

    def test_extract_enabled_when_slot_available(self):
        from cogs.ui_renderer import build_gear_components
        rows = build_gear_components("gathering", "normal", True, self._player_gear(), gear_cap=10, affixes=[], max_slots=2)
        buttons = {c.custom_id: c for row in rows for c in row.children}
        self.assertFalse(buttons["extract_affix:gathering"].disabled)

    def test_clear_button_hidden_for_empty_slot(self):
        from cogs.ui_renderer import build_gear_components
        rows = build_gear_components("gathering", "normal", True, self._player_gear(), gear_cap=10, affixes=[], max_slots=1)
        custom_ids = [c.custom_id for row in rows for c in row.children]
        self.assertFalse(any("clear_affix" in cid for cid in custom_ids))

    def test_clear_button_present_for_occupied_slot(self):
        from cogs.ui_renderer import build_gear_components
        affixes = [{"slot_index": 0, "affix_type": "efficiency", "value": 3}]
        rows = build_gear_components("gathering", "normal", True, self._player_gear(), gear_cap=10, affixes=affixes, max_slots=1)
        custom_ids = [c.custom_id for row in rows for c in row.children]
        self.assertIn("clear_affix:gathering:0", custom_ids)


class TestAffixRouteRegistration(unittest.TestCase):
    """extract_affix and clear_affix are registered interaction routes."""

    def setUp(self):
        for k, v in ALL_TEST_ENV.items():
            os.environ[k] = v

    def test_extract_affix_is_own_button(self):
        from cogs.actions import _is_own_button
        self.assertTrue(_is_own_button("extract_affix:gathering"))

    def test_clear_affix_is_own_button(self):
        from cogs.actions import _is_own_button
        self.assertTrue(_is_own_button("clear_affix:gathering:0"))

    def test_invalid_gear_type_not_routed_extract(self):
        from cogs.actions import _is_own_button
        # _is_own_button only checks prefix, gear_type validation is in handler
        self.assertTrue(_is_own_button("extract_affix:invalid"))


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

    async def test_extract_affix_dispatches_affix_extracted_event(self):
        from cogs.actions import ActionsCog

        inter = self._make_inter("extract_affix:gathering")
        with (
            patch("cogs.actions.get_connection", return_value=self._make_db_cm()),
            patch("cogs.actions.player_manager.get_gear_level", new=AsyncMock(return_value=10)),
            patch(
                "cogs.actions.affix_manager.extract_affix",
                new=AsyncMock(return_value={"slot_index": 0, "affix_type": "efficiency", "value": 3}),
            ),
            patch("cogs.actions.notification.dispatch_events", new=AsyncMock()) as mock_dispatch,
            patch.object(ActionsCog, "_render_gear", new=AsyncMock()),
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

    async def test_extract_affix_no_dispatch_on_failure(self):
        from cogs.actions import ActionsCog

        inter = self._make_inter("extract_affix:gathering")
        with (
            patch("cogs.actions.get_connection", return_value=self._make_db_cm()),
            patch("cogs.actions.player_manager.get_gear_level", new=AsyncMock(return_value=10)),
            patch("cogs.actions.affix_manager.extract_affix", new=AsyncMock(side_effect=ValueError("full"))),
            patch("cogs.actions.notification.dispatch_events", new=AsyncMock()) as mock_dispatch,
            patch.object(ActionsCog, "_render_gear", new=AsyncMock()),
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


if __name__ == "__main__":
    unittest.main()

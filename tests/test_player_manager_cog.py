"""
tests/test_player_manager_cog.py — unit tests for player manager UI rendering functions
and PlayerManagerCog slash command / dropdown handler behaviour.

Covers:
  - build_manager_embed(): embed title, fields, and values
  - build_manager_components(): action row structure and custom_id format
  - PlayerManagerCog.manager(): /idlevillage-manager slash command (no sub-commands)
  - PlayerManagerCog.on_dropdown(): mgr_player_select handler
"""

import os
import sys
import unittest

# Support module must be loaded before any src imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from tests.support import ALL_TEST_ENV  # noqa: E402


class TestBuildManagerEmbed(unittest.TestCase):
    """build_manager_embed returns a correctly structured Embed."""

    def setUp(self):
        for k, v in ALL_TEST_ENV.items():
            os.environ[k] = v

    def _make_player_data(self):
        return {
            "gear_gathering": 1,
            "gear_building": 2,
            "gear_combat": 3,
            "gear_research": 4,
            "materials_gathering": 10,
            "materials_building": 20,
            "materials_combat": 30,
            "materials_research": 40,
            "materials_universal": 50,
            "pity_gathering": 0,
            "pity_building": 1,
            "pity_combat": 2,
            "pity_research": 3,
            "risky_failed_levels": 5,
        }

    def test_returns_embed_instance(self):
        import disnake
        from cogs.ui_renderer import build_manager_embed

        embed = build_manager_embed("TestUser", self._make_player_data())
        self.assertIsInstance(embed, disnake.Embed)

    def test_embed_title_contains_display_name(self):
        from cogs.ui_renderer import build_manager_embed

        embed = build_manager_embed("TestUser", self._make_player_data())
        self.assertIn("TestUser", embed.title)
        self.assertIn("玩家管理", embed.title)

    def test_embed_title_with_different_display_name(self):
        from cogs.ui_renderer import build_manager_embed

        embed = build_manager_embed("Alice", self._make_player_data())
        self.assertIn("Alice", embed.title)

    def test_embed_color_is_orange(self):
        import disnake
        from cogs.ui_renderer import build_manager_embed

        embed = build_manager_embed("TestUser", self._make_player_data())
        self.assertEqual(embed.color, disnake.Color.orange())

    def test_embed_has_four_fields(self):
        from cogs.ui_renderer import build_manager_embed

        embed = build_manager_embed("TestUser", self._make_player_data())
        self.assertEqual(len(embed.fields), 4)

    @staticmethod
    def _field_name(f) -> str:
        """Return field name regardless of whether field is a dict or EmbedProxy."""
        return f["name"] if isinstance(f, dict) else f.name

    @staticmethod
    def _field_value(f) -> str:
        """Return field value regardless of whether field is a dict or EmbedProxy."""
        return f["value"] if isinstance(f, dict) else f.value

    @staticmethod
    def _field_inline(f) -> bool:
        """Return field inline flag regardless of whether field is a dict or EmbedProxy."""
        return f["inline"] if isinstance(f, dict) else f.inline

    def test_gear_field_contains_all_gear_values(self):
        from cogs.ui_renderer import build_manager_embed

        player_data = self._make_player_data()
        embed = build_manager_embed("TestUser", player_data)

        gear_field = next(f for f in embed.fields if "工具等級" in self._field_name(f))
        value = self._field_value(gear_field)
        self.assertIn("採集 1", value)
        self.assertIn("建設 2", value)
        self.assertIn("戰鬥 3", value)
        self.assertIn("研究 4", value)

    def test_gear_field_is_not_inline(self):
        from cogs.ui_renderer import build_manager_embed

        embed = build_manager_embed("TestUser", self._make_player_data())
        gear_field = next(f for f in embed.fields if "工具等級" in self._field_name(f))
        self.assertFalse(self._field_inline(gear_field))

    def test_materials_field_contains_all_values(self):
        from cogs.ui_renderer import build_manager_embed

        player_data = self._make_player_data()
        embed = build_manager_embed("TestUser", player_data)

        mat_field = next(f for f in embed.fields if "素材" in self._field_name(f))
        value = self._field_value(mat_field)
        self.assertIn("採集 10", value)
        self.assertIn("建設 20", value)
        self.assertIn("戰鬥 30", value)
        self.assertIn("研究 40", value)
        self.assertIn("萬能 50", value)

    def test_materials_field_is_not_inline(self):
        from cogs.ui_renderer import build_manager_embed

        embed = build_manager_embed("TestUser", self._make_player_data())
        mat_field = next(f for f in embed.fields if "素材" in self._field_name(f))
        self.assertFalse(self._field_inline(mat_field))

    def test_pity_field_contains_all_values(self):
        from cogs.ui_renderer import build_manager_embed

        player_data = self._make_player_data()
        embed = build_manager_embed("TestUser", player_data)

        pity_field = next(f for f in embed.fields if "保底" in self._field_name(f))
        value = self._field_value(pity_field)
        self.assertIn("採集 0", value)
        self.assertIn("建設 1", value)
        self.assertIn("戰鬥 2", value)
        self.assertIn("研究 3", value)

    def test_pity_field_is_not_inline(self):
        from cogs.ui_renderer import build_manager_embed

        embed = build_manager_embed("TestUser", self._make_player_data())
        pity_field = next(f for f in embed.fields if "保底" in self._field_name(f))
        self.assertFalse(self._field_inline(pity_field))

    def test_risky_field_contains_value(self):
        from cogs.ui_renderer import build_manager_embed

        player_data = self._make_player_data()
        embed = build_manager_embed("TestUser", player_data)

        risky_field = next(f for f in embed.fields if "鐵齒" in self._field_name(f))
        self.assertIn("5", self._field_value(risky_field))

    def test_risky_field_is_not_inline(self):
        from cogs.ui_renderer import build_manager_embed

        embed = build_manager_embed("TestUser", self._make_player_data())
        risky_field = next(f for f in embed.fields if "鐵齒" in self._field_name(f))
        self.assertFalse(self._field_inline(risky_field))

    def test_missing_player_data_fields_default_to_zero(self):
        from cogs.ui_renderer import build_manager_embed

        embed = build_manager_embed("TestUser", {})
        gear_field = next(f for f in embed.fields if "工具等級" in self._field_name(f))
        value = self._field_value(gear_field)
        self.assertIn("採集 0", value)
        self.assertIn("建設 0", value)
        self.assertIn("戰鬥 0", value)
        self.assertIn("研究 0", value)

        risky_field = next(f for f in embed.fields if "鐵齒" in self._field_name(f))
        self.assertIn("0", self._field_value(risky_field))


class TestBuildManagerComponents(unittest.TestCase):
    """build_manager_components returns a correctly structured component list."""

    def setUp(self):
        for k, v in ALL_TEST_ENV.items():
            os.environ[k] = v

    def test_returns_list(self):
        from cogs.ui_renderer import build_manager_components

        result = build_manager_components("123456789")
        self.assertIsInstance(result, list)

    def test_returns_one_action_row(self):
        import disnake
        from cogs.ui_renderer import build_manager_components

        result = build_manager_components("123456789")
        self.assertEqual(len(result), 1)
        self.assertIsInstance(result[0], disnake.ui.ActionRow)

    def test_action_row_has_four_buttons(self):
        from cogs.ui_renderer import build_manager_components

        result = build_manager_components("123456789")
        row = result[0]
        self.assertEqual(len(row.children), 4)

    def test_all_buttons_are_secondary_style(self):
        import disnake
        from cogs.ui_renderer import build_manager_components

        result = build_manager_components("123456789")
        for button in result[0].children:
            self.assertEqual(
                button.style,
                disnake.ButtonStyle.secondary,
                f"Button '{button.label}' should be secondary style",
            )

    def test_gear_button_custom_id_contains_user_id(self):
        from cogs.ui_renderer import build_manager_components

        uid = "111222333"
        result = build_manager_components(uid)
        custom_ids = [btn.custom_id for btn in result[0].children]
        self.assertIn(f"mgr_edit_gear:{uid}", custom_ids)

    def test_material_button_custom_id_contains_user_id(self):
        from cogs.ui_renderer import build_manager_components

        uid = "111222333"
        result = build_manager_components(uid)
        custom_ids = [btn.custom_id for btn in result[0].children]
        self.assertIn(f"mgr_edit_material:{uid}", custom_ids)

    def test_pity_button_custom_id_contains_user_id(self):
        from cogs.ui_renderer import build_manager_components

        uid = "111222333"
        result = build_manager_components(uid)
        custom_ids = [btn.custom_id for btn in result[0].children]
        self.assertIn(f"mgr_edit_pity:{uid}", custom_ids)

    def test_risky_button_custom_id_contains_user_id(self):
        from cogs.ui_renderer import build_manager_components

        uid = "111222333"
        result = build_manager_components(uid)
        custom_ids = [btn.custom_id for btn in result[0].children]
        self.assertIn(f"mgr_edit_risky:{uid}", custom_ids)

    def test_all_four_custom_id_prefixes_present(self):
        from cogs.ui_renderer import build_manager_components

        uid = "999888777"
        result = build_manager_components(uid)
        custom_ids = {btn.custom_id for btn in result[0].children}
        expected = {
            f"mgr_edit_gear:{uid}",
            f"mgr_edit_material:{uid}",
            f"mgr_edit_pity:{uid}",
            f"mgr_edit_risky:{uid}",
        }
        self.assertEqual(custom_ids, expected)

    def test_different_user_ids_produce_different_custom_ids(self):
        from cogs.ui_renderer import build_manager_components

        result_a = build_manager_components("user_a")
        result_b = build_manager_components("user_b")

        ids_a = {btn.custom_id for btn in result_a[0].children}
        ids_b = {btn.custom_id for btn in result_b[0].children}
        self.assertEqual(ids_a & ids_b, set(), "Different user IDs should produce disjoint custom_id sets")


class TestBuildManagerEmbedImport(unittest.TestCase):
    """Smoke test: build_manager_embed and build_manager_components can be imported."""

    def test_can_import_build_manager_embed(self):
        from cogs.ui_renderer import build_manager_embed  # noqa: F401
        self.assertTrue(callable(build_manager_embed))

    def test_can_import_build_manager_components(self):
        from cogs.ui_renderer import build_manager_components  # noqa: F401
        self.assertTrue(callable(build_manager_components))


class TestPlayerManagerCogSubCommandsRemoved(unittest.TestCase):
    """Verify that the five old sub-commands no longer exist on PlayerManagerCog."""

    def setUp(self):
        for k, v in ALL_TEST_ENV.items():
            os.environ[k] = v

    def test_no_player_view_attribute(self):
        from cogs.player_manager_cog import PlayerManagerCog
        self.assertFalse(hasattr(PlayerManagerCog, "player_view"))

    def test_no_player_gear_attribute(self):
        from cogs.player_manager_cog import PlayerManagerCog
        self.assertFalse(hasattr(PlayerManagerCog, "player_gear"))

    def test_no_player_material_attribute(self):
        from cogs.player_manager_cog import PlayerManagerCog
        self.assertFalse(hasattr(PlayerManagerCog, "player_material"))

    def test_no_player_pity_attribute(self):
        from cogs.player_manager_cog import PlayerManagerCog
        self.assertFalse(hasattr(PlayerManagerCog, "player_pity"))

    def test_no_player_risky_attribute(self):
        from cogs.player_manager_cog import PlayerManagerCog
        self.assertFalse(hasattr(PlayerManagerCog, "player_risky"))


class TestPlayerManagerCogSlashCommand(unittest.IsolatedAsyncioTestCase):
    """/idlevillage-manager slash command sends ephemeral UserSelect."""

    def setUp(self):
        for k, v in ALL_TEST_ENV.items():
            os.environ[k] = v

    def _make_cog(self):
        import unittest.mock as mock
        from cogs.player_manager_cog import PlayerManagerCog
        bot = mock.MagicMock()
        return PlayerManagerCog(bot)

    def _make_inter(self, *, guild_id=None, user_id=None, is_admin=True):
        import unittest.mock as mock
        guild_id = guild_id or ALL_TEST_ENV["DISCORD_GUILD_ID"]
        user_id = user_id or ALL_TEST_ENV["ADMIN_IDS"]
        inter = mock.AsyncMock()
        inter.guild_id = int(guild_id)
        inter.user.id = int(user_id)
        inter.response.defer = mock.AsyncMock()
        inter.response.send_message = mock.AsyncMock()
        inter.edit_original_response = mock.AsyncMock()
        return inter

    async def _call_manager(self, cog, inter):
        """Call the manager callback directly, bypassing disnake's command wrapper."""
        from cogs.player_manager_cog import PlayerManagerCog
        await PlayerManagerCog.manager.callback(cog, inter)

    async def test_manager_command_exists_and_is_callable(self):
        cog = self._make_cog()
        self.assertTrue(callable(cog.manager))

    async def test_manager_wrong_guild_sends_guild_error(self):
        cog = self._make_cog()
        inter = self._make_inter(guild_id="999999999999999999")
        await self._call_manager(cog, inter)
        inter.response.send_message.assert_awaited_once()
        args, kwargs = inter.response.send_message.call_args
        self.assertTrue(kwargs.get("ephemeral", False))
        self.assertIn("伺服器", args[0])

    async def test_manager_non_admin_sends_admin_error(self):
        cog = self._make_cog()
        inter = self._make_inter(user_id="999999999999999999")
        await self._call_manager(cog, inter)
        inter.response.send_message.assert_awaited_once()
        args, kwargs = inter.response.send_message.call_args
        self.assertTrue(kwargs.get("ephemeral", False))
        self.assertIn("管理員", args[0])

    async def test_manager_defers_ephemeral_on_success(self):
        cog = self._make_cog()
        inter = self._make_inter()
        await self._call_manager(cog, inter)
        inter.response.defer.assert_awaited_once_with(ephemeral=True)

    async def test_manager_sends_user_select_component(self):
        import disnake
        cog = self._make_cog()
        inter = self._make_inter()
        await self._call_manager(cog, inter)
        inter.edit_original_response.assert_awaited_once()
        _, kwargs = inter.edit_original_response.call_args
        components = kwargs.get("components", [])
        self.assertTrue(len(components) > 0, "Should have at least one component row")
        row = components[0]
        self.assertIsInstance(row, disnake.ui.ActionRow)
        self.assertEqual(len(row.children), 1)
        user_select = row.children[0]
        self.assertEqual(user_select.custom_id, "mgr_player_select")
        self.assertIsInstance(user_select, disnake.ui.UserSelect)

    async def test_manager_content_is_player_select_prompt(self):
        cog = self._make_cog()
        inter = self._make_inter()
        await self._call_manager(cog, inter)
        _, kwargs = inter.edit_original_response.call_args
        self.assertIn("選擇", kwargs.get("content", ""))


class TestPlayerManagerCogOnDropdown(unittest.IsolatedAsyncioTestCase):
    """mgr_player_select dropdown handler."""

    def setUp(self):
        for k, v in ALL_TEST_ENV.items():
            os.environ[k] = v

    def _make_cog(self):
        import unittest.mock as mock
        from cogs.player_manager_cog import PlayerManagerCog
        bot = mock.MagicMock()
        return PlayerManagerCog(bot)

    def _make_inter(self, *, guild_id=None, user_id=None, custom_id="mgr_player_select", values=None):
        import unittest.mock as mock
        guild_id = guild_id or ALL_TEST_ENV["DISCORD_GUILD_ID"]
        user_id = user_id or ALL_TEST_ENV["ADMIN_IDS"]
        inter = mock.AsyncMock()
        inter.guild_id = int(guild_id)
        inter.user.id = int(user_id)
        inter.data = mock.MagicMock()
        inter.data.custom_id = custom_id
        inter.values = values or ["123456789"]
        inter.guild = mock.MagicMock()
        inter.guild.get_member.return_value = None
        inter.response.defer = mock.AsyncMock()
        inter.response.send_message = mock.AsyncMock()
        inter.edit_original_response = mock.AsyncMock()
        return inter

    async def test_ignores_non_mgr_player_select_custom_id(self):
        cog = self._make_cog()
        inter = self._make_inter(custom_id="other_dropdown")
        await cog.on_dropdown(inter)
        inter.response.defer.assert_not_awaited()
        inter.edit_original_response.assert_not_awaited()

    async def test_wrong_guild_sends_guild_error(self):
        cog = self._make_cog()
        inter = self._make_inter(guild_id="999999999999999999")
        await cog.on_dropdown(inter)
        inter.response.send_message.assert_awaited_once()
        args, kwargs = inter.response.send_message.call_args
        self.assertIn("伺服器", args[0])

    async def test_non_admin_sends_admin_error(self):
        cog = self._make_cog()
        inter = self._make_inter(user_id="999999999999999999")
        await cog.on_dropdown(inter)
        inter.response.send_message.assert_awaited_once()
        args, kwargs = inter.response.send_message.call_args
        self.assertIn("管理員", args[0])

    async def test_player_not_found_returns_not_joined_message(self):
        import unittest.mock as mock
        from tests.support import DatabaseTestCase

        # Use a real DB so the SELECT returns None
        class _DBTest(DatabaseTestCase):
            pass

        tc = _DBTest()
        await tc.asyncSetUp()
        try:
            cog = self._make_cog()
            inter = self._make_inter(values=["nonexistent_user_999"])
            await cog.on_dropdown(inter)
            inter.edit_original_response.assert_awaited_once()
            _, kwargs = inter.edit_original_response.call_args
            content = kwargs.get("content", "")
            self.assertIn("尚未加入遊戲", content)
        finally:
            await tc.asyncTearDown()

    async def test_player_found_calls_edit_with_embed_and_components(self):
        import disnake
        import unittest.mock as mock
        from tests.support import DatabaseTestCase
        from database.schema import get_connection

        tc = DatabaseTestCase()
        await tc.asyncSetUp()
        try:
            # Insert a player row
            target_uid = "777888999"
            ts = "2026-01-01T00:00:00+00:00"
            async with get_connection() as db:
                await db.execute(
                    "INSERT INTO players (user_id, created_at, updated_at, ap_full_time, "
                    "gear_gathering, gear_building, gear_combat, gear_research, "
                    "materials_gathering, materials_building, materials_combat, materials_research, "
                    "pity_gathering, pity_building, pity_combat, pity_research, risky_failed_levels) "
                    "VALUES (?, ?, ?, ?, 1, 2, 3, 4, 10, 20, 30, 40, 0, 1, 2, 3, 5)",
                    (target_uid, ts, ts, ts),
                )
                await db.commit()

            cog = self._make_cog()
            inter = self._make_inter(values=[target_uid])
            await cog.on_dropdown(inter)

            inter.edit_original_response.assert_awaited_once()
            _, kwargs = inter.edit_original_response.call_args
            embed = kwargs.get("embed")
            components = kwargs.get("components")
            self.assertIsNotNone(embed)
            self.assertIsNotNone(components)
            self.assertIsInstance(embed, disnake.Embed)
            self.assertIsInstance(components, list)
            self.assertTrue(len(components) > 0)

            # Verify embed fields contain the actual DB values (1/2/3/4 gear, 10/20/30/40 mat, etc.)
            def get_field_value(fields, name_fragment):
                for f in fields:
                    fname = f["name"] if isinstance(f, dict) else f.name
                    if name_fragment in fname:
                        return f["value"] if isinstance(f, dict) else f.value
                return None

            gear_val = get_field_value(embed.fields, "工具等級")
            self.assertIsNotNone(gear_val)
            for expected in ["採集 1", "建設 2", "戰鬥 3", "研究 4"]:
                self.assertIn(expected, gear_val)

            mat_val = get_field_value(embed.fields, "素材")
            self.assertIsNotNone(mat_val)
            for expected in ["採集 10", "建設 20", "戰鬥 30", "研究 40", "萬能 0"]:
                self.assertIn(expected, mat_val)

            risky_val = get_field_value(embed.fields, "鐵齒")
            self.assertIsNotNone(risky_val)
            self.assertIn("5", risky_val)

            # Verify components use the correct target_user_id
            all_custom_ids = [btn.custom_id for btn in components[0].children]
            for cid in all_custom_ids:
                self.assertIn(target_uid, cid)
        finally:
            await tc.asyncTearDown()

    async def test_player_found_embed_has_correct_title(self):
        import unittest.mock as mock
        from tests.support import DatabaseTestCase
        from database.schema import get_connection

        tc = DatabaseTestCase()
        await tc.asyncSetUp()
        try:
            target_uid = "555444333"
            ts = "2026-01-01T00:00:00+00:00"
            async with get_connection() as db:
                await db.execute(
                    "INSERT INTO players (user_id, created_at, updated_at, ap_full_time) "
                    "VALUES (?, ?, ?, ?)",
                    (target_uid, ts, ts, ts),
                )
                await db.commit()

            cog = self._make_cog()
            inter = self._make_inter(values=[target_uid])
            # Simulate guild member lookup returning a member with a display_name
            mock_member = mock.MagicMock()
            mock_member.display_name = "TestPlayer"
            inter.guild.get_member.return_value = mock_member

            await cog.on_dropdown(inter)

            _, kwargs = inter.edit_original_response.call_args
            embed = kwargs.get("embed")
            self.assertIn("TestPlayer", embed.title)
            self.assertIn("玩家管理", embed.title)
        finally:
            await tc.asyncTearDown()

    async def test_player_found_components_contain_user_id(self):
        import unittest.mock as mock
        from tests.support import DatabaseTestCase
        from database.schema import get_connection

        tc = DatabaseTestCase()
        await tc.asyncSetUp()
        try:
            target_uid = "111333555"
            ts = "2026-01-01T00:00:00+00:00"
            async with get_connection() as db:
                await db.execute(
                    "INSERT INTO players (user_id, created_at, updated_at, ap_full_time) "
                    "VALUES (?, ?, ?, ?)",
                    (target_uid, ts, ts, ts),
                )
                await db.commit()

            cog = self._make_cog()
            inter = self._make_inter(values=[target_uid])
            await cog.on_dropdown(inter)

            _, kwargs = inter.edit_original_response.call_args
            components = kwargs.get("components", [])
            all_custom_ids = [btn.custom_id for btn in components[0].children]
            for cid in all_custom_ids:
                self.assertIn(target_uid, cid)
        finally:
            await tc.asyncTearDown()


class TestPlayerManagerCogOnButtonClick(unittest.IsolatedAsyncioTestCase):
    """on_button_click handler sends the correct Modal for each mgr_edit_* button."""

    def setUp(self):
        for k, v in ALL_TEST_ENV.items():
            os.environ[k] = v

    def _make_cog(self):
        import unittest.mock as mock
        from cogs.player_manager_cog import PlayerManagerCog
        bot = mock.MagicMock()
        return PlayerManagerCog(bot)

    def _make_inter(self, *, guild_id=None, user_id=None, custom_id="mgr_edit_gear:123"):
        import unittest.mock as mock
        guild_id = guild_id or ALL_TEST_ENV["DISCORD_GUILD_ID"]
        user_id = user_id or ALL_TEST_ENV["ADMIN_IDS"]
        inter = mock.AsyncMock()
        inter.guild_id = int(guild_id)
        inter.user.id = int(user_id)
        inter.data = mock.MagicMock()
        inter.data.custom_id = custom_id
        inter.response.send_message = mock.AsyncMock()
        inter.response.send_modal = mock.AsyncMock()
        return inter

    async def test_ignores_non_mgr_edit_custom_id(self):
        cog = self._make_cog()
        inter = self._make_inter(custom_id="some_other_button")
        await cog.on_button_click(inter)
        inter.response.send_modal.assert_not_awaited()
        inter.response.send_message.assert_not_awaited()

    async def test_wrong_guild_sends_error(self):
        cog = self._make_cog()
        inter = self._make_inter(guild_id="999999999999999999", custom_id="mgr_edit_gear:123")
        await cog.on_button_click(inter)
        inter.response.send_message.assert_awaited_once()
        args, kwargs = inter.response.send_message.call_args
        self.assertIn("伺服器", args[0])

    async def test_non_admin_sends_error(self):
        cog = self._make_cog()
        inter = self._make_inter(user_id="999999999999999999", custom_id="mgr_edit_gear:123")
        await cog.on_button_click(inter)
        inter.response.send_message.assert_awaited_once()
        args, kwargs = inter.response.send_message.call_args
        self.assertIn("管理員", args[0])

    @staticmethod
    def _extract_field_ids(modal_components):
        """Extract TextInput custom_ids from modal components.

        In real disnake, TextInputs inside a Modal are wrapped in ActionRows.
        Handle both: components being ActionRows (with .children) or raw TextInputs.
        """
        ids = []
        for component in modal_components:
            if hasattr(component, "children"):
                # ActionRow wrapping TextInput(s)
                for child in component.children:
                    if hasattr(child, "custom_id"):
                        ids.append(child.custom_id)
            elif hasattr(component, "custom_id"):
                ids.append(component.custom_id)
        return ids

    async def test_gear_button_sends_modal_with_correct_custom_id(self):
        import disnake
        cog = self._make_cog()
        uid = "123456789"
        inter = self._make_inter(custom_id=f"mgr_edit_gear:{uid}")
        await cog.on_button_click(inter)
        inter.response.send_modal.assert_awaited_once()
        modal = inter.response.send_modal.call_args[0][0]
        self.assertEqual(modal.custom_id, f"mgr_modal_gear:{uid}")
        self.assertEqual(modal.title, "編輯工具等級")
        field_ids = self._extract_field_ids(modal.components)
        self.assertIn("gear_gathering", field_ids)
        self.assertIn("gear_building", field_ids)
        self.assertIn("gear_combat", field_ids)
        self.assertIn("gear_research", field_ids)

    async def test_material_button_sends_modal_with_five_fields(self):
        cog = self._make_cog()
        uid = "123456789"
        inter = self._make_inter(custom_id=f"mgr_edit_material:{uid}")
        await cog.on_button_click(inter)
        inter.response.send_modal.assert_awaited_once()
        modal = inter.response.send_modal.call_args[0][0]
        self.assertEqual(modal.custom_id, f"mgr_modal_material:{uid}")
        self.assertEqual(modal.title, "編輯素材數量")
        field_ids = self._extract_field_ids(modal.components)
        self.assertIn("mat_gathering", field_ids)
        self.assertIn("mat_building", field_ids)
        self.assertIn("mat_combat", field_ids)
        self.assertIn("mat_research", field_ids)
        self.assertIn("mat_universal", field_ids)

    async def test_pity_button_sends_modal_with_four_fields(self):
        cog = self._make_cog()
        uid = "123456789"
        inter = self._make_inter(custom_id=f"mgr_edit_pity:{uid}")
        await cog.on_button_click(inter)
        inter.response.send_modal.assert_awaited_once()
        modal = inter.response.send_modal.call_args[0][0]
        self.assertEqual(modal.custom_id, f"mgr_modal_pity:{uid}")
        self.assertEqual(modal.title, "編輯保底計數")
        field_ids = self._extract_field_ids(modal.components)
        self.assertIn("pity_gathering", field_ids)
        self.assertIn("pity_building", field_ids)
        self.assertIn("pity_combat", field_ids)
        self.assertIn("pity_research", field_ids)

    async def test_risky_button_sends_modal_with_single_field(self):
        cog = self._make_cog()
        uid = "123456789"
        inter = self._make_inter(custom_id=f"mgr_edit_risky:{uid}")
        await cog.on_button_click(inter)
        inter.response.send_modal.assert_awaited_once()
        modal = inter.response.send_modal.call_args[0][0]
        self.assertEqual(modal.custom_id, f"mgr_modal_risky:{uid}")
        self.assertEqual(modal.title, "編輯鐵齒失敗累積")
        field_ids = self._extract_field_ids(modal.components)
        self.assertEqual(len(field_ids), 1)
        self.assertIn("risky_failed_levels", field_ids)


class TestPlayerManagerCogOnModalSubmit(unittest.IsolatedAsyncioTestCase):
    """on_modal_submit handler validates inputs, writes DB, and refreshes panel."""

    def setUp(self):
        for k, v in ALL_TEST_ENV.items():
            os.environ[k] = v

    def _make_cog(self):
        import unittest.mock as mock
        from cogs.player_manager_cog import PlayerManagerCog
        bot = mock.MagicMock()
        return PlayerManagerCog(bot)

    def _make_inter(self, *, guild_id=None, user_id=None, custom_id, text_values):
        import unittest.mock as mock
        guild_id = guild_id or ALL_TEST_ENV["DISCORD_GUILD_ID"]
        user_id = user_id or ALL_TEST_ENV["ADMIN_IDS"]
        inter = mock.AsyncMock()
        inter.guild_id = int(guild_id)
        inter.user.id = int(user_id)
        inter.custom_id = custom_id
        inter.text_values = text_values
        inter.guild = mock.MagicMock()
        inter.guild.get_member.return_value = None
        inter.response.defer = mock.AsyncMock()
        inter.response.send_message = mock.AsyncMock()
        inter.edit_original_response = mock.AsyncMock()
        return inter

    async def test_ignores_non_mgr_modal_custom_id(self):
        cog = self._make_cog()
        inter = self._make_inter(custom_id="other_modal", text_values={})
        await cog.on_modal_submit(inter)
        inter.response.defer.assert_not_awaited()
        inter.edit_original_response.assert_not_awaited()

    async def test_modal_submit_defers_ephemeral(self):
        """on_modal_submit must call defer(ephemeral=True) to keep the response ephemeral."""
        from tests.support import DatabaseTestCase
        from database.schema import get_connection

        tc = DatabaseTestCase()
        await tc.asyncSetUp()
        try:
            target_uid = "999111222"
            ts = "2026-01-01T00:00:00+00:00"
            async with get_connection() as db:
                await db.execute(
                    "INSERT INTO players (user_id, created_at, updated_at, ap_full_time) "
                    "VALUES (?, ?, ?, ?)",
                    (target_uid, ts, ts, ts),
                )
                await db.commit()

            cog = self._make_cog()
            inter = self._make_inter(
                custom_id=f"mgr_modal_gear:{target_uid}",
                text_values={
                    "gear_gathering": "1",
                    "gear_building": "1",
                    "gear_combat": "1",
                    "gear_research": "1",
                },
            )
            await cog.on_modal_submit(inter)
            inter.response.defer.assert_awaited_once_with(ephemeral=True)
        finally:
            await tc.asyncTearDown()

    async def test_wrong_guild_sends_error(self):
        cog = self._make_cog()
        inter = self._make_inter(
            guild_id="999999999999999999",
            custom_id="mgr_modal_gear:123",
            text_values={},
        )
        await cog.on_modal_submit(inter)
        inter.response.send_message.assert_awaited_once()
        args, kwargs = inter.response.send_message.call_args
        self.assertIn("伺服器", args[0])

    async def test_non_admin_sends_error(self):
        cog = self._make_cog()
        inter = self._make_inter(
            user_id="999999999999999999",
            custom_id="mgr_modal_gear:123",
            text_values={},
        )
        await cog.on_modal_submit(inter)
        inter.response.send_message.assert_awaited_once()
        args, kwargs = inter.response.send_message.call_args
        self.assertIn("管理員", args[0])

    async def test_invalid_non_integer_input_returns_error(self):
        cog = self._make_cog()
        inter = self._make_inter(
            custom_id="mgr_modal_gear:123",
            text_values={
                "gear_gathering": "abc",
                "gear_building": "2",
                "gear_combat": "3",
                "gear_research": "4",
            },
        )
        await cog.on_modal_submit(inter)
        inter.edit_original_response.assert_awaited_once()
        args, kwargs = inter.edit_original_response.call_args
        content = kwargs.get("content", "")
        self.assertIn("錯誤", content)

    async def test_negative_integer_input_returns_error(self):
        cog = self._make_cog()
        inter = self._make_inter(
            custom_id="mgr_modal_gear:123",
            text_values={
                "gear_gathering": "-1",
                "gear_building": "2",
                "gear_combat": "3",
                "gear_research": "4",
            },
        )
        await cog.on_modal_submit(inter)
        inter.edit_original_response.assert_awaited_once()
        _, kwargs = inter.edit_original_response.call_args
        content = kwargs.get("content", "")
        self.assertIn("錯誤", content)

    async def test_gear_modal_writes_db_and_refreshes_panel(self):
        import disnake
        from tests.support import DatabaseTestCase
        from database.schema import get_connection

        tc = DatabaseTestCase()
        await tc.asyncSetUp()
        try:
            target_uid = "888777666"
            ts = "2026-01-01T00:00:00+00:00"
            async with get_connection() as db:
                await db.execute(
                    "INSERT INTO players (user_id, created_at, updated_at, ap_full_time) "
                    "VALUES (?, ?, ?, ?)",
                    (target_uid, ts, ts, ts),
                )
                await db.commit()

            cog = self._make_cog()
            inter = self._make_inter(
                custom_id=f"mgr_modal_gear:{target_uid}",
                text_values={
                    "gear_gathering": "5",
                    "gear_building": "6",
                    "gear_combat": "7",
                    "gear_research": "8",
                },
            )
            await cog.on_modal_submit(inter)

            # Verify DB was updated
            async with get_connection() as db:
                async with db.execute(
                    "SELECT gear_gathering, gear_building, gear_combat, gear_research FROM players WHERE user_id=?",
                    (target_uid,),
                ) as cur:
                    row = await cur.fetchone()
            self.assertEqual(row, (5, 6, 7, 8))

            # Verify panel was refreshed
            inter.edit_original_response.assert_awaited()
            _, kwargs = inter.edit_original_response.call_args
            self.assertIsNotNone(kwargs.get("embed"))
            self.assertIsInstance(kwargs.get("embed"), disnake.Embed)
            self.assertIsNotNone(kwargs.get("components"))
        finally:
            await tc.asyncTearDown()

    async def test_material_modal_writes_db_and_refreshes_panel(self):
        import disnake
        from tests.support import DatabaseTestCase
        from database.schema import get_connection

        tc = DatabaseTestCase()
        await tc.asyncSetUp()
        try:
            target_uid = "111222333"
            ts = "2026-01-01T00:00:00+00:00"
            async with get_connection() as db:
                await db.execute(
                    "INSERT INTO players (user_id, created_at, updated_at, ap_full_time) "
                    "VALUES (?, ?, ?, ?)",
                    (target_uid, ts, ts, ts),
                )
                await db.commit()

            cog = self._make_cog()
            inter = self._make_inter(
                custom_id=f"mgr_modal_material:{target_uid}",
                text_values={
                    "mat_gathering": "100",
                    "mat_building": "200",
                    "mat_combat": "300",
                    "mat_research": "400",
                    "mat_universal": "500",
                },
            )
            await cog.on_modal_submit(inter)

            async with get_connection() as db:
                async with db.execute(
                    "SELECT materials_gathering, materials_building, materials_combat, materials_research, "
                    "materials_universal "
                    "FROM players WHERE user_id=?",
                    (target_uid,),
                ) as cur:
                    row = await cur.fetchone()
            self.assertEqual(row, (100, 200, 300, 400, 500))

            _, kwargs = inter.edit_original_response.call_args
            self.assertIsInstance(kwargs.get("embed"), disnake.Embed)
        finally:
            await tc.asyncTearDown()

    async def test_pity_modal_writes_db_and_refreshes_panel(self):
        import disnake
        from tests.support import DatabaseTestCase
        from database.schema import get_connection

        tc = DatabaseTestCase()
        await tc.asyncSetUp()
        try:
            target_uid = "444555666"
            ts = "2026-01-01T00:00:00+00:00"
            async with get_connection() as db:
                await db.execute(
                    "INSERT INTO players (user_id, created_at, updated_at, ap_full_time) "
                    "VALUES (?, ?, ?, ?)",
                    (target_uid, ts, ts, ts),
                )
                await db.commit()

            cog = self._make_cog()
            inter = self._make_inter(
                custom_id=f"mgr_modal_pity:{target_uid}",
                text_values={
                    "pity_gathering": "3",
                    "pity_building": "4",
                    "pity_combat": "5",
                    "pity_research": "6",
                },
            )
            await cog.on_modal_submit(inter)

            async with get_connection() as db:
                async with db.execute(
                    "SELECT pity_gathering, pity_building, pity_combat, pity_research "
                    "FROM players WHERE user_id=?",
                    (target_uid,),
                ) as cur:
                    row = await cur.fetchone()
            self.assertEqual(row, (3, 4, 5, 6))

            _, kwargs = inter.edit_original_response.call_args
            self.assertIsInstance(kwargs.get("embed"), disnake.Embed)
        finally:
            await tc.asyncTearDown()

    async def test_risky_modal_writes_db_and_refreshes_panel(self):
        import disnake
        from tests.support import DatabaseTestCase
        from database.schema import get_connection

        tc = DatabaseTestCase()
        await tc.asyncSetUp()
        try:
            target_uid = "777666555"
            ts = "2026-01-01T00:00:00+00:00"
            async with get_connection() as db:
                await db.execute(
                    "INSERT INTO players (user_id, created_at, updated_at, ap_full_time) "
                    "VALUES (?, ?, ?, ?)",
                    (target_uid, ts, ts, ts),
                )
                await db.commit()

            cog = self._make_cog()
            inter = self._make_inter(
                custom_id=f"mgr_modal_risky:{target_uid}",
                text_values={"risky_failed_levels": "12"},
            )
            await cog.on_modal_submit(inter)

            async with get_connection() as db:
                async with db.execute(
                    "SELECT risky_failed_levels FROM players WHERE user_id=?",
                    (target_uid,),
                ) as cur:
                    row = await cur.fetchone()
            self.assertEqual(row[0], 12)

            _, kwargs = inter.edit_original_response.call_args
            self.assertIsInstance(kwargs.get("embed"), disnake.Embed)
        finally:
            await tc.asyncTearDown()

    async def test_modal_submit_embed_shows_updated_values(self):
        from tests.support import DatabaseTestCase
        from database.schema import get_connection

        tc = DatabaseTestCase()
        await tc.asyncSetUp()
        try:
            target_uid = "123123123"
            ts = "2026-01-01T00:00:00+00:00"
            async with get_connection() as db:
                await db.execute(
                    "INSERT INTO players (user_id, created_at, updated_at, ap_full_time) "
                    "VALUES (?, ?, ?, ?)",
                    (target_uid, ts, ts, ts),
                )
                await db.commit()

            cog = self._make_cog()
            inter = self._make_inter(
                custom_id=f"mgr_modal_gear:{target_uid}",
                text_values={
                    "gear_gathering": "9",
                    "gear_building": "10",
                    "gear_combat": "11",
                    "gear_research": "12",
                },
            )
            await cog.on_modal_submit(inter)

            _, kwargs = inter.edit_original_response.call_args
            embed = kwargs.get("embed")

            def get_field_value(fields, name_fragment):
                for f in fields:
                    fname = f["name"] if isinstance(f, dict) else f.name
                    if name_fragment in fname:
                        return f["value"] if isinstance(f, dict) else f.value
                return None

            gear_val = get_field_value(embed.fields, "工具等級")
            self.assertIn("採集 9", gear_val)
            self.assertIn("建設 10", gear_val)
            self.assertIn("戰鬥 11", gear_val)
            self.assertIn("研究 12", gear_val)
        finally:
            await tc.asyncTearDown()


if __name__ == "__main__":
    unittest.main()

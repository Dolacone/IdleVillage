"""
tests/test_player_manager_cog.py — unit tests for player manager UI rendering functions.

Covers:
  - build_manager_embed(): embed title, fields, and values
  - build_manager_components(): action row structure and custom_id format
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


if __name__ == "__main__":
    unittest.main()

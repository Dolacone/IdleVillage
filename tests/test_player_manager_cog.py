"""
tests/test_player_manager_cog.py — tests for PlayerManagerCog (/idlevillage-manager).

Covers: guild check, admin check, player-view, player-gear, player-material,
        player-pity, player-risky.
"""

import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

# Support must be imported before any src imports (sets up sys.path + disnake stub)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from tests.support import ALL_TEST_ENV, DatabaseTestCase
from database import schema


NOW = datetime(2026, 5, 15, 0, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

async def _insert_player(db, user_id: str, **kwargs) -> None:
    """Insert a players row for testing.

    Defaults: all stats 0, ap_full_time = now + AP_CAP * AP_RECOVERY_MINUTES.
    """
    from core.config import get_env_int
    from core.utils import dt_str

    ap_cap = get_env_int("AP_CAP")
    recovery_mins = get_env_int("AP_RECOVERY_MINUTES")
    ap_full_time = NOW + timedelta(minutes=ap_cap * recovery_mins)

    gear_gathering = kwargs.get("gear_gathering", 0)
    gear_building = kwargs.get("gear_building", 0)
    gear_combat = kwargs.get("gear_combat", 0)
    gear_research = kwargs.get("gear_research", 0)
    materials_gathering = kwargs.get("materials_gathering", 0)
    materials_building = kwargs.get("materials_building", 0)
    materials_combat = kwargs.get("materials_combat", 0)
    materials_research = kwargs.get("materials_research", 0)
    pity_gathering = kwargs.get("pity_gathering", 0)
    pity_building = kwargs.get("pity_building", 0)
    pity_combat = kwargs.get("pity_combat", 0)
    pity_research = kwargs.get("pity_research", 0)
    risky_failed_levels = kwargs.get("risky_failed_levels", 0)
    now_str = dt_str(NOW)
    aft_str = kwargs.get("ap_full_time", dt_str(ap_full_time))

    await db.execute(
        """INSERT INTO players
           (user_id,
            gear_gathering, gear_building, gear_combat, gear_research,
            materials_gathering, materials_building, materials_combat, materials_research,
            pity_gathering, pity_building, pity_combat, pity_research,
            risky_failed_levels,
            ap_full_time, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            user_id,
            gear_gathering, gear_building, gear_combat, gear_research,
            materials_gathering, materials_building, materials_combat, materials_research,
            pity_gathering, pity_building, pity_combat, pity_research,
            risky_failed_levels,
            aft_str, now_str, now_str,
        ),
    )
    await db.commit()


def _make_inter(user_id: int = None, guild_id: str = None):
    """Build a mock ApplicationCommandInteraction."""
    inter = MagicMock()
    inter.guild_id = guild_id or ALL_TEST_ENV["DISCORD_GUILD_ID"]
    inter.user = MagicMock()
    inter.user.id = user_id if user_id is not None else int(ALL_TEST_ENV["ADMIN_IDS"])
    inter.response.send_message = AsyncMock()
    inter.response.defer = AsyncMock()
    inter.edit_original_response = AsyncMock()
    return inter


def _make_user(user_id: int = 123456789, display_name: str = "TestUser"):
    """Build a mock disnake.Member."""
    mock_user = MagicMock()
    mock_user.id = user_id
    mock_user.mention = f"<@{user_id}>"
    mock_user.display_name = display_name
    return mock_user


# ---------------------------------------------------------------------------
# TestGuildAndAdminChecks — pure logic, no DB
# ---------------------------------------------------------------------------

class TestGuildAndAdminChecks(unittest.TestCase):
    def setUp(self):
        for k, v in ALL_TEST_ENV.items():
            os.environ[k] = v

    def _get_cog(self):
        from cogs.player_manager_cog import PlayerManagerCog
        return PlayerManagerCog(MagicMock())

    def test_wrong_guild_rejected(self):
        cog = self._get_cog()
        inter = _make_inter(guild_id="999999999999999999")
        self.assertFalse(cog._check_guild(inter))

    def test_correct_guild_accepted(self):
        cog = self._get_cog()
        inter = _make_inter(guild_id=ALL_TEST_ENV["DISCORD_GUILD_ID"])
        self.assertTrue(cog._check_guild(inter))

    def test_non_admin_rejected(self):
        cog = self._get_cog()
        inter = _make_inter(user_id=999999999999)
        self.assertFalse(cog._check_admin(inter))

    def test_admin_accepted(self):
        cog = self._get_cog()
        inter = _make_inter(user_id=int(ALL_TEST_ENV["ADMIN_IDS"]))
        self.assertTrue(cog._check_admin(inter))


# ---------------------------------------------------------------------------
# TestPlayerView
# ---------------------------------------------------------------------------

class TestPlayerView(DatabaseTestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()

    def _get_cog(self):
        from cogs.player_manager_cog import PlayerManagerCog
        return PlayerManagerCog(MagicMock())

    async def test_player_not_found(self):
        from cogs.player_manager_cog import PlayerManagerCog
        cog = self._get_cog()
        inter = _make_inter()
        mock_user = _make_user(user_id=99999999)

        await PlayerManagerCog.player_view.callback(cog, inter, user=mock_user)

        inter.response.defer.assert_awaited_once()
        call_kwargs = inter.edit_original_response.call_args
        content = call_kwargs.kwargs.get("content", "")
        self.assertIn("尚未加入遊戲", content)

    async def test_player_view_returns_embed(self):
        from cogs.player_manager_cog import PlayerManagerCog
        cog = self._get_cog()
        inter = _make_inter()
        mock_user = _make_user(user_id=111222333)

        async with schema.get_connection() as db:
            await _insert_player(db, str(mock_user.id))

        await PlayerManagerCog.player_view.callback(cog, inter, user=mock_user)

        inter.response.defer.assert_awaited_once()
        inter.edit_original_response.assert_awaited_once()
        call_kwargs = inter.edit_original_response.call_args
        embed = call_kwargs.kwargs.get("embed")
        self.assertIsNotNone(embed, "player-view should respond with an embed when player exists")


# ---------------------------------------------------------------------------
# TestPlayerGear
# ---------------------------------------------------------------------------

class TestPlayerGear(DatabaseTestCase):
    def _get_cog(self):
        from cogs.player_manager_cog import PlayerManagerCog
        return PlayerManagerCog(MagicMock())

    async def test_set_gear_level(self):
        from cogs.player_manager_cog import PlayerManagerCog
        cog = self._get_cog()
        inter = _make_inter()
        mock_user = _make_user(user_id=200000001)

        async with schema.get_connection() as db:
            await _insert_player(db, str(mock_user.id), gear_gathering=2)

        await PlayerManagerCog.player_gear.callback(cog, inter, user=mock_user, gear_type="gathering", level=5)

        inter.edit_original_response.assert_awaited_once()
        # Verify DB was updated
        row = await self.fetchone(
            "SELECT gear_gathering FROM players WHERE user_id=?",
            (str(mock_user.id),),
        )
        self.assertEqual(row[0], 5)
        # Confirm old→new is mentioned in the response
        content = inter.edit_original_response.call_args.kwargs.get("content", "")
        self.assertIn("2", content)
        self.assertIn("5", content)

    async def test_player_not_found(self):
        from cogs.player_manager_cog import PlayerManagerCog
        cog = self._get_cog()
        inter = _make_inter()
        mock_user = _make_user(user_id=200000002)

        await PlayerManagerCog.player_gear.callback(cog, inter, user=mock_user, gear_type="gathering", level=3)

        inter.response.defer.assert_awaited_once()
        content = inter.edit_original_response.call_args.kwargs.get("content", "")
        self.assertIn("尚未加入遊戲", content)

    async def test_negative_value_rejected(self):
        from cogs.player_manager_cog import PlayerManagerCog
        cog = self._get_cog()
        inter = _make_inter()
        mock_user = _make_user(user_id=200000003)

        await PlayerManagerCog.player_gear.callback(cog, inter, user=mock_user, gear_type="gathering", level=-1)

        # Negative value should call send_message, NOT defer
        inter.response.send_message.assert_awaited_once()
        inter.response.defer.assert_not_awaited()


# ---------------------------------------------------------------------------
# TestPlayerMaterial
# ---------------------------------------------------------------------------

class TestPlayerMaterial(DatabaseTestCase):
    def _get_cog(self):
        from cogs.player_manager_cog import PlayerManagerCog
        return PlayerManagerCog(MagicMock())

    async def test_set_material(self):
        from cogs.player_manager_cog import PlayerManagerCog
        cog = self._get_cog()
        inter = _make_inter()
        mock_user = _make_user(user_id=300000001)

        async with schema.get_connection() as db:
            await _insert_player(db, str(mock_user.id), materials_building=3)

        await PlayerManagerCog.player_material.callback(cog, inter, user=mock_user, gear_type="building", amount=10)

        inter.edit_original_response.assert_awaited_once()
        row = await self.fetchone(
            "SELECT materials_building FROM players WHERE user_id=?",
            (str(mock_user.id),),
        )
        self.assertEqual(row[0], 10)
        content = inter.edit_original_response.call_args.kwargs.get("content", "")
        self.assertIn("3", content)
        self.assertIn("10", content)

    async def test_player_not_found(self):
        from cogs.player_manager_cog import PlayerManagerCog
        cog = self._get_cog()
        inter = _make_inter()
        mock_user = _make_user(user_id=300000002)

        await PlayerManagerCog.player_material.callback(cog, inter, user=mock_user, gear_type="building", amount=5)

        inter.response.defer.assert_awaited_once()
        content = inter.edit_original_response.call_args.kwargs.get("content", "")
        self.assertIn("尚未加入遊戲", content)


# ---------------------------------------------------------------------------
# TestPlayerPity
# ---------------------------------------------------------------------------

class TestPlayerPity(DatabaseTestCase):
    def _get_cog(self):
        from cogs.player_manager_cog import PlayerManagerCog
        return PlayerManagerCog(MagicMock())

    async def test_set_pity(self):
        from cogs.player_manager_cog import PlayerManagerCog
        cog = self._get_cog()
        inter = _make_inter()
        mock_user = _make_user(user_id=400000001)

        async with schema.get_connection() as db:
            await _insert_player(db, str(mock_user.id), pity_combat=1)

        await PlayerManagerCog.player_pity.callback(cog, inter, user=mock_user, gear_type="combat", count=7)

        inter.edit_original_response.assert_awaited_once()
        row = await self.fetchone(
            "SELECT pity_combat FROM players WHERE user_id=?",
            (str(mock_user.id),),
        )
        self.assertEqual(row[0], 7)
        content = inter.edit_original_response.call_args.kwargs.get("content", "")
        self.assertIn("1", content)
        self.assertIn("7", content)

    async def test_player_not_found(self):
        from cogs.player_manager_cog import PlayerManagerCog
        cog = self._get_cog()
        inter = _make_inter()
        mock_user = _make_user(user_id=400000002)

        await PlayerManagerCog.player_pity.callback(cog, inter, user=mock_user, gear_type="combat", count=3)

        inter.response.defer.assert_awaited_once()
        content = inter.edit_original_response.call_args.kwargs.get("content", "")
        self.assertIn("尚未加入遊戲", content)


# ---------------------------------------------------------------------------
# TestPlayerRisky
# ---------------------------------------------------------------------------

class TestPlayerRisky(DatabaseTestCase):
    def _get_cog(self):
        from cogs.player_manager_cog import PlayerManagerCog
        return PlayerManagerCog(MagicMock())

    async def test_set_risky(self):
        from cogs.player_manager_cog import PlayerManagerCog
        cog = self._get_cog()
        inter = _make_inter()
        mock_user = _make_user(user_id=500000001)

        async with schema.get_connection() as db:
            await _insert_player(db, str(mock_user.id), risky_failed_levels=4)

        await PlayerManagerCog.player_risky.callback(cog, inter, user=mock_user, value=9)

        inter.edit_original_response.assert_awaited_once()
        row = await self.fetchone(
            "SELECT risky_failed_levels FROM players WHERE user_id=?",
            (str(mock_user.id),),
        )
        self.assertEqual(row[0], 9)
        content = inter.edit_original_response.call_args.kwargs.get("content", "")
        self.assertIn("4", content)
        self.assertIn("9", content)

    async def test_player_not_found(self):
        from cogs.player_manager_cog import PlayerManagerCog
        cog = self._get_cog()
        inter = _make_inter()
        mock_user = _make_user(user_id=500000002)

        await PlayerManagerCog.player_risky.callback(cog, inter, user=mock_user, value=5)

        inter.response.defer.assert_awaited_once()
        content = inter.edit_original_response.call_args.kwargs.get("content", "")
        self.assertIn("尚未加入遊戲", content)


if __name__ == "__main__":
    unittest.main()

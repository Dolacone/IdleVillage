"""
Tests for managers.gear_manager — gear upgrade attempts, success rate, and pity system.
Mechanics reference: docs/managers/gear-manager.md
"""

import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from tests.support import ALL_TEST_ENV, DatabaseTestCase
from database import schema
from managers import gear_manager, building_manager, player_manager


NOW = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
USER = "user_gear_001"


async def _insert_player(db, user_id: str, gear_type: str, gear_level: int = 0,
                          materials: int = 0, pity: int = 0,
                          risky_failed_levels: int = 0,
                          universal_materials: int = 0) -> None:
    """Helper: insert a player row with specific gear state."""
    from core.utils import dt_str
    from core.formula import ACTION_GEAR_COL, ACTION_MATERIAL_COL

    gear_col = ACTION_GEAR_COL[gear_type]
    mat_col = ACTION_MATERIAL_COL[gear_type]
    now_str = dt_str(NOW)

    await db.execute(
        f"""INSERT INTO players
            (user_id, {gear_col}, {mat_col}, pity_{gear_type},
             risky_failed_levels, materials_universal,
             ap_full_time, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (user_id, gear_level, materials, pity, risky_failed_levels, universal_materials,
         now_str, now_str, now_str),
    )
    await db.commit()


async def _set_research_lab_level(db, level: int) -> None:
    """Helper: set the research_lab building level."""
    from core.utils import dt_str
    await db.execute(
        "UPDATE buildings SET level=? WHERE building_type='research_lab'",
        (level,),
    )
    await db.commit()


class TestComputeRate(unittest.TestCase):
    """_compute_rate formula tests — pure function, no DB needed."""

    def setUp(self):
        self._orig = {k: os.environ.get(k) for k in ALL_TEST_ENV}
        for k, v in ALL_TEST_ENV.items():
            os.environ[k] = v

    def tearDown(self):
        for k, v in self._orig.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_level_0_no_pity_is_full_rate(self):
        rate = gear_manager._compute_rate(0, 0)
        self.assertAlmostEqual(rate, 1.0)

    def test_rate_decreases_with_level(self):
        # At level 5: base = max(0.10, 1.0 - 5 * 0.10) = 0.50 < 1.0
        rate_l0 = gear_manager._compute_rate(0, 0)
        rate_l5 = gear_manager._compute_rate(5, 0)
        self.assertLess(rate_l5, rate_l0)

    def test_rate_floored_at_min_success_rate(self):
        # At very high level the rate should not drop below GEAR_MIN_SUCCESS_RATE (0.10)
        rate = gear_manager._compute_rate(999, 0)
        self.assertAlmostEqual(rate, 0.10)

    def test_pity_raises_rate(self):
        # Use level 9 where base_rate = 0.10; pity should raise it
        base = gear_manager._compute_rate(9, 0)
        with_pity = gear_manager._compute_rate(9, 4)
        self.assertGreater(with_pity, base)

    def test_rate_capped_at_1(self):
        # Very high pity must not exceed 1.0
        rate = gear_manager._compute_rate(0, 9999)
        self.assertAlmostEqual(rate, 1.0)

    def test_level_5_rate_formula(self):
        # base = max(0.10, 1.0 - 5 * 0.10) = max(0.10, 0.50) = 0.50
        rate = gear_manager._compute_rate(5, 0)
        self.assertAlmostEqual(rate, 0.50)

    def test_level_6_rate_formula_uses_decimal_intent(self):
        rate = gear_manager._compute_rate(6, 0)
        self.assertEqual(rate, 0.40)

    def test_level_9_rate_formula(self):
        # base = max(0.10, 1.0 - 9 * 0.10) = max(0.10, 0.10) = 0.10
        rate = gear_manager._compute_rate(9, 0)
        self.assertAlmostEqual(rate, 0.10)

    def test_pity_bonus_applied(self):
        # base = 0.10 (level 9), pity = 2 → 0.10 + 2 * 0.05 = 0.20
        rate = gear_manager._compute_rate(9, 2)
        self.assertAlmostEqual(rate, 0.20)


class TestGetUpgradeInfo(DatabaseTestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        async with schema.get_connection() as db:
            await _insert_player(db, USER, "gathering", gear_level=0, materials=5, pity=0)
            await _set_research_lab_level(db, 3)

    async def test_returns_correct_fields(self):
        async with schema.get_connection() as db:
            info = await gear_manager.get_upgrade_info(db, USER, "gathering", NOW)
        self.assertIn("gear_level", info)
        self.assertIn("target_level", info)
        self.assertIn("material_cost", info)
        self.assertIn("rate", info)
        self.assertIn("pity", info)
        self.assertIn("ap", info)
        self.assertIn("can_attempt", info)
        self.assertIn("gear_cap", info)

    async def test_can_attempt_true_when_all_preconditions_met(self):
        async with schema.get_connection() as db:
            info = await gear_manager.get_upgrade_info(db, USER, "gathering", NOW)
        self.assertTrue(info["can_attempt"])

    async def test_can_attempt_false_when_at_cap(self):
        async with schema.get_connection() as db:
            await db.execute(
                "UPDATE players SET gear_gathering=3 WHERE user_id=?", (USER,)
            )
            await db.commit()
            info = await gear_manager.get_upgrade_info(db, USER, "gathering", NOW)
        self.assertFalse(info["can_attempt"])

    async def test_material_cost_equals_target_level(self):
        async with schema.get_connection() as db:
            info = await gear_manager.get_upgrade_info(db, USER, "gathering", NOW)
        self.assertEqual(info["material_cost"], info["target_level"])

    async def test_buffer_mode_material_cost_is_half(self):
        async with schema.get_connection() as db:
            info = await gear_manager.get_upgrade_info(db, USER, "gathering", NOW, mode="buffer")
        import math
        self.assertEqual(info["material_cost"], math.ceil(info["target_level"] / 2))
        self.assertEqual(info["mode"], "buffer")

    async def test_risky_mode_material_cost_is_one(self):
        async with schema.get_connection() as db:
            info = await gear_manager.get_upgrade_info(db, USER, "gathering", NOW, mode="risky")
        self.assertEqual(info["material_cost"], 1)
        self.assertEqual(info["mode"], "risky")

    async def test_invalid_mode_raises(self):
        async with schema.get_connection() as db:
            with self.assertRaises(ValueError):
                await gear_manager.get_upgrade_info(db, USER, "gathering", NOW, mode="invalid")

    async def test_gear_cap_matches_research_lab_level(self):
        async with schema.get_connection() as db:
            info = await gear_manager.get_upgrade_info(db, USER, "gathering", NOW)
        self.assertEqual(info["gear_cap"], 3)


class TestAttemptUpgrade(DatabaseTestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        async with schema.get_connection() as db:
            # gear_level=0 → rate=1.0; use level=5 for failure tests (rate=0.50)
            await _insert_player(db, USER, "gathering", gear_level=0, materials=10, pity=0)
            await _set_research_lab_level(db, 10)

    async def test_success_increases_gear_level(self):
        with patch("managers.gear_manager.random.random", return_value=0.0):
            async with schema.get_connection() as db:
                result = await gear_manager.attempt_upgrade(db, USER, "gathering", NOW)
                await db.commit()
        self.assertTrue(result["success"])
        self.assertEqual(result["new_level"], 1)

    async def test_success_resets_pity_to_zero(self):
        async with schema.get_connection() as db:
            await db.execute(
                "UPDATE players SET pity_gathering=3 WHERE user_id=?", (USER,)
            )
            await db.commit()
        with patch("managers.gear_manager.random.random", return_value=0.0):
            async with schema.get_connection() as db:
                await gear_manager.attempt_upgrade(db, USER, "gathering", NOW)
                await db.commit()
        row = await self.fetchone(
            "SELECT pity_gathering FROM players WHERE user_id=?", (USER,)
        )
        self.assertEqual(row[0], 0)

    async def test_failure_does_not_change_gear_level(self):
        # Set gear_level=5 so rate=0.50; mock 0.9999 → failure
        async with schema.get_connection() as db:
            await db.execute(
                "UPDATE players SET gear_gathering=5, materials_gathering=10 WHERE user_id=?",
                (USER,),
            )
            await db.commit()
        with patch("managers.gear_manager.random.random", return_value=0.9999):
            async with schema.get_connection() as db:
                result = await gear_manager.attempt_upgrade(db, USER, "gathering", NOW)
                await db.commit()
        self.assertFalse(result["success"])
        self.assertEqual(result["new_level"], 5)

    async def test_failure_increments_pity(self):
        async with schema.get_connection() as db:
            await db.execute(
                "UPDATE players SET gear_gathering=5, materials_gathering=10 WHERE user_id=?",
                (USER,),
            )
            await db.commit()
        with patch("managers.gear_manager.random.random", return_value=0.9999):
            async with schema.get_connection() as db:
                await gear_manager.attempt_upgrade(db, USER, "gathering", NOW)
                await db.commit()
        row = await self.fetchone(
            "SELECT pity_gathering FROM players WHERE user_id=?", (USER,)
        )
        self.assertEqual(row[0], 1)

    async def test_ap_deducted_on_success(self):
        with patch("managers.gear_manager.random.random", return_value=0.0):
            async with schema.get_connection() as db:
                before_ap = await player_manager.get_ap(db, USER, NOW)
                await gear_manager.attempt_upgrade(db, USER, "gathering", NOW)
                await db.commit()
                after_ap = await player_manager.get_ap(db, USER, NOW)
        self.assertEqual(after_ap, before_ap - 1)

    async def test_ap_deducted_on_failure(self):
        async with schema.get_connection() as db:
            await db.execute(
                "UPDATE players SET gear_gathering=5, materials_gathering=10 WHERE user_id=?",
                (USER,),
            )
            await db.commit()
        with patch("managers.gear_manager.random.random", return_value=0.9999):
            async with schema.get_connection() as db:
                before_ap = await player_manager.get_ap(db, USER, NOW)
                await gear_manager.attempt_upgrade(db, USER, "gathering", NOW)
                await db.commit()
                after_ap = await player_manager.get_ap(db, USER, NOW)
        self.assertEqual(after_ap, before_ap - 1)

    async def test_materials_deducted_on_success(self):
        with patch("managers.gear_manager.random.random", return_value=0.0):
            async with schema.get_connection() as db:
                await gear_manager.attempt_upgrade(db, USER, "gathering", NOW)
                await db.commit()
        # material_cost = target_level = 1; started with 10
        row = await self.fetchone(
            "SELECT materials_gathering FROM players WHERE user_id=?", (USER,)
        )
        self.assertEqual(row[0], 9)

    async def test_materials_deducted_on_failure(self):
        async with schema.get_connection() as db:
            await db.execute(
                "UPDATE players SET gear_gathering=5, materials_gathering=10 WHERE user_id=?",
                (USER,),
            )
            await db.commit()
        with patch("managers.gear_manager.random.random", return_value=0.9999):
            async with schema.get_connection() as db:
                await gear_manager.attempt_upgrade(db, USER, "gathering", NOW)
                await db.commit()
        # material_cost = target_level = 6; started with 10 → 4 remaining
        row = await self.fetchone(
            "SELECT materials_gathering FROM players WHERE user_id=?", (USER,)
        )
        self.assertEqual(row[0], 4)

    async def test_raises_when_gear_at_cap(self):
        async with schema.get_connection() as db:
            await db.execute(
                "UPDATE players SET gear_gathering=10 WHERE user_id=?", (USER,)
            )
            await db.commit()
        async with schema.get_connection() as db:
            with self.assertRaises(ValueError):
                await gear_manager.attempt_upgrade(db, USER, "gathering", NOW)

    async def test_raises_when_insufficient_ap(self):
        from core.utils import dt_str
        future = dt_str(NOW + timedelta(hours=100))
        async with schema.get_connection() as db:
            await db.execute(
                "UPDATE players SET ap_full_time=? WHERE user_id=?", (future, USER)
            )
            await db.commit()
        async with schema.get_connection() as db:
            with self.assertRaises(ValueError):
                await gear_manager.attempt_upgrade(db, USER, "gathering", NOW)

    async def test_raises_when_insufficient_materials(self):
        async with schema.get_connection() as db:
            await db.execute(
                "UPDATE players SET materials_gathering=0 WHERE user_id=?", (USER,)
            )
            await db.commit()
        async with schema.get_connection() as db:
            with self.assertRaises(ValueError):
                await gear_manager.attempt_upgrade(db, USER, "gathering", NOW)

    async def test_returned_rate_matches_compute_rate(self):
        with patch("managers.gear_manager.random.random", return_value=0.0):
            async with schema.get_connection() as db:
                result = await gear_manager.attempt_upgrade(db, USER, "gathering", NOW)
                await db.commit()
        expected_rate = gear_manager._compute_rate(0, 0)
        self.assertAlmostEqual(result["rate"], expected_rate)

    async def test_success_result_includes_pity_before(self):
        async with schema.get_connection() as db:
            await db.execute(
                "UPDATE players SET pity_gathering=3 WHERE user_id=?", (USER,)
            )
            await db.commit()
        with patch("managers.gear_manager.random.random", return_value=0.0):
            async with schema.get_connection() as db:
                result = await gear_manager.attempt_upgrade(db, USER, "gathering", NOW)
                await db.commit()
        self.assertTrue(result["success"])
        self.assertEqual(result["pity_before"], 3)
        self.assertEqual(result["pity_after"], 0)

    async def test_failure_result_includes_pity_before(self):
        async with schema.get_connection() as db:
            await db.execute(
                "UPDATE players SET gear_gathering=5, materials_gathering=10, pity_gathering=2 WHERE user_id=?",
                (USER,),
            )
            await db.commit()
        with patch("managers.gear_manager.random.random", return_value=0.9999):
            async with schema.get_connection() as db:
                result = await gear_manager.attempt_upgrade(db, USER, "gathering", NOW)
                await db.commit()
        self.assertFalse(result["success"])
        self.assertEqual(result["pity_before"], 2)
        self.assertEqual(result["pity_after"], 3)

    async def test_result_includes_target_level(self):
        with patch("managers.gear_manager.random.random", return_value=0.0):
            async with schema.get_connection() as db:
                result = await gear_manager.attempt_upgrade(db, USER, "gathering", NOW)
                await db.commit()
        self.assertEqual(result["target_level"], result["current_level"] + 1)

    async def test_all_gear_types_accepted(self):
        for gear_type in ("gathering", "building", "combat", "research"):
            async with schema.get_connection() as db:
                uid = f"user_{gear_type}"
                await _insert_player(db, uid, gear_type, gear_level=0, materials=10, pity=0)
                await db.commit()
            with patch("managers.gear_manager.random.random", return_value=0.0):
                async with schema.get_connection() as db:
                    result = await gear_manager.attempt_upgrade(db, uid, gear_type, NOW)
                    await db.commit()
            self.assertTrue(result["success"], f"Expected success for gear_type={gear_type}")

    async def test_invalid_mode_raises(self):
        async with schema.get_connection() as db:
            with self.assertRaises(ValueError):
                await gear_manager.attempt_upgrade(db, USER, "gathering", NOW, mode="invalid")


class TestBufferMode(DatabaseTestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        async with schema.get_connection() as db:
            await _insert_player(db, USER, "gathering", gear_level=2, materials=10, pity=1)
            await _set_research_lab_level(db, 10)

    async def test_buffer_increments_pity(self):
        async with schema.get_connection() as db:
            result = await gear_manager.attempt_upgrade(db, USER, "gathering", NOW, mode="buffer")
            await db.commit()
        self.assertEqual(result["pity_before"], 1)
        self.assertEqual(result["pity_after"], 2)
        row = await self.fetchone(
            "SELECT pity_gathering FROM players WHERE user_id=?", (USER,)
        )
        self.assertEqual(row[0], 2)

    async def test_buffer_does_not_change_gear_level(self):
        async with schema.get_connection() as db:
            result = await gear_manager.attempt_upgrade(db, USER, "gathering", NOW, mode="buffer")
            await db.commit()
        self.assertEqual(result["new_level"], 2)
        self.assertFalse(result["success"])

    async def test_buffer_deducts_half_materials(self):
        # gear_level=2 → target_level=3 → buffer cost = ceil(3/2) = 2
        async with schema.get_connection() as db:
            await gear_manager.attempt_upgrade(db, USER, "gathering", NOW, mode="buffer")
            await db.commit()
        row = await self.fetchone(
            "SELECT materials_gathering FROM players WHERE user_id=?", (USER,)
        )
        self.assertEqual(row[0], 8)  # 10 - 2

    async def test_buffer_deducts_ap(self):
        async with schema.get_connection() as db:
            before_ap = await player_manager.get_ap(db, USER, NOW)
            await gear_manager.attempt_upgrade(db, USER, "gathering", NOW, mode="buffer")
            await db.commit()
            after_ap = await player_manager.get_ap(db, USER, NOW)
        self.assertEqual(after_ap, before_ap - 1)

    async def test_buffer_result_has_mode_field(self):
        async with schema.get_connection() as db:
            result = await gear_manager.attempt_upgrade(db, USER, "gathering", NOW, mode="buffer")
            await db.commit()
        self.assertEqual(result["mode"], "buffer")

    async def test_buffer_minimum_cost_is_one(self):
        # gear_level=0 → target_level=1 → ceil(1/2) = 1
        async with schema.get_connection() as db:
            await _insert_player(db, "user_min", "gathering", gear_level=0, materials=5, pity=0)
            await db.commit()
        async with schema.get_connection() as db:
            result = await gear_manager.attempt_upgrade(db, "user_min", "gathering", NOW, mode="buffer")
            await db.commit()
        row = await self.fetchone(
            "SELECT materials_gathering FROM players WHERE user_id=?", ("user_min",)
        )
        self.assertEqual(row[0], 4)  # 5 - 1


class TestRiskyMode(DatabaseTestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        async with schema.get_connection() as db:
            await _insert_player(db, USER, "gathering", gear_level=5, materials=10, pity=3)
            await _set_research_lab_level(db, 10)

    async def test_risky_success_increases_gear_level_by_one(self):
        with patch("managers.gear_manager.random.random", return_value=0.0), \
             patch("managers.gear_manager.random.choices", return_value=[1]):
            async with schema.get_connection() as db:
                result = await gear_manager.attempt_upgrade(db, USER, "gathering", NOW, mode="risky")
                await db.commit()
        self.assertTrue(result["success"])
        self.assertEqual(result["level_gain"], 1)
        self.assertEqual(result["new_level"], 6)

    async def test_risky_success_level_gain_two(self):
        with patch("managers.gear_manager.random.random", return_value=0.0), \
             patch("managers.gear_manager.random.choices", return_value=[2]):
            async with schema.get_connection() as db:
                result = await gear_manager.attempt_upgrade(db, USER, "gathering", NOW, mode="risky")
                await db.commit()
        self.assertTrue(result["success"])
        self.assertEqual(result["level_gain"], 2)
        self.assertEqual(result["new_level"], 7)

    async def test_risky_success_level_gain_three(self):
        with patch("managers.gear_manager.random.random", return_value=0.0), \
             patch("managers.gear_manager.random.choices", return_value=[3]):
            async with schema.get_connection() as db:
                result = await gear_manager.attempt_upgrade(db, USER, "gathering", NOW, mode="risky")
                await db.commit()
        self.assertTrue(result["success"])
        self.assertEqual(result["level_gain"], 3)
        self.assertEqual(result["new_level"], 8)

    async def test_risky_success_resets_pity(self):
        with patch("managers.gear_manager.random.random", return_value=0.0), \
             patch("managers.gear_manager.random.choices", return_value=[1]):
            async with schema.get_connection() as db:
                await gear_manager.attempt_upgrade(db, USER, "gathering", NOW, mode="risky")
                await db.commit()
        row = await self.fetchone(
            "SELECT pity_gathering FROM players WHERE user_id=?", (USER,)
        )
        self.assertEqual(row[0], 0)

    async def test_risky_failure_resets_pity_to_zero(self):
        with patch("managers.gear_manager.random.random", return_value=0.9999):
            async with schema.get_connection() as db:
                result = await gear_manager.attempt_upgrade(db, USER, "gathering", NOW, mode="risky")
                await db.commit()
        self.assertFalse(result["success"])
        self.assertEqual(result["pity_after"], 0)
        row = await self.fetchone(
            "SELECT pity_gathering FROM players WHERE user_id=?", (USER,)
        )
        self.assertEqual(row[0], 0)

    async def test_risky_failure_resets_gear_level_to_zero(self):
        with patch("managers.gear_manager.random.random", return_value=0.9999):
            async with schema.get_connection() as db:
                result = await gear_manager.attempt_upgrade(db, USER, "gathering", NOW, mode="risky")
                await db.commit()
        self.assertEqual(result["new_level"], 0)
        row = await self.fetchone(
            "SELECT gear_gathering FROM players WHERE user_id=?", (USER,)
        )
        self.assertEqual(row[0], 0)

    async def test_risky_deducts_one_material(self):
        with patch("managers.gear_manager.random.random", return_value=0.9999):
            async with schema.get_connection() as db:
                await gear_manager.attempt_upgrade(db, USER, "gathering", NOW, mode="risky")
                await db.commit()
        row = await self.fetchone(
            "SELECT materials_gathering FROM players WHERE user_id=?", (USER,)
        )
        self.assertEqual(row[0], 9)  # 10 - 1

    async def test_risky_deducts_ap(self):
        with patch("managers.gear_manager.random.random", return_value=0.0):
            async with schema.get_connection() as db:
                before_ap = await player_manager.get_ap(db, USER, NOW)
                await gear_manager.attempt_upgrade(db, USER, "gathering", NOW, mode="risky")
                await db.commit()
                after_ap = await player_manager.get_ap(db, USER, NOW)
        self.assertEqual(after_ap, before_ap - 1)

    async def test_risky_result_has_mode_field(self):
        with patch("managers.gear_manager.random.random", return_value=0.0):
            async with schema.get_connection() as db:
                result = await gear_manager.attempt_upgrade(db, USER, "gathering", NOW, mode="risky")
                await db.commit()
        self.assertEqual(result["mode"], "risky")

    async def test_risky_raises_when_no_materials(self):
        async with schema.get_connection() as db:
            await db.execute(
                "UPDATE players SET materials_gathering=0 WHERE user_id=?", (USER,)
            )
            await db.commit()
        async with schema.get_connection() as db:
            with self.assertRaises(ValueError):
                await gear_manager.attempt_upgrade(db, USER, "gathering", NOW, mode="risky")


class TestRiskyModeEnhancements(DatabaseTestCase):
    """Tests for risky_failed_levels accumulation and success rate bonus."""

    async def asyncSetUp(self):
        await super().asyncSetUp()
        async with schema.get_connection() as db:
            await _insert_player(db, USER, "gathering", gear_level=5, materials=20, pity=0,
                                  risky_failed_levels=0)
            await _set_research_lab_level(db, 20)

    # -------------------------------------------------------------------------
    # risky_failed_levels accumulation
    # -------------------------------------------------------------------------

    async def test_risky_failure_accumulates_risky_failed_levels(self):
        """On risky failure, risky_failed_levels += current_level (before the attempt)."""
        # gear_level=5; after failure → risky_failed_levels should be 5
        with patch("managers.gear_manager.random.random", return_value=0.9999):
            async with schema.get_connection() as db:
                await gear_manager.attempt_upgrade(db, USER, "gathering", NOW, mode="risky")
                await db.commit()
        row = await self.fetchone(
            "SELECT risky_failed_levels FROM players WHERE user_id=?", (USER,)
        )
        self.assertEqual(row[0], 5)

    async def test_risky_failed_levels_accumulates_across_multiple_failures(self):
        """Two failures at different levels should sum correctly."""
        # First failure at level 5 → risky_failed_levels = 5; gear resets to 0
        # Can't do second failure at different level without success in between,
        # so verify the first failure and ensure the value persists.
        async with schema.get_connection() as db:
            await db.execute(
                "UPDATE players SET risky_failed_levels=10 WHERE user_id=?", (USER,)
            )
            await db.commit()
        with patch("managers.gear_manager.random.random", return_value=0.9999):
            async with schema.get_connection() as db:
                await gear_manager.attempt_upgrade(db, USER, "gathering", NOW, mode="risky")
                await db.commit()
        row = await self.fetchone(
            "SELECT risky_failed_levels FROM players WHERE user_id=?", (USER,)
        )
        # started at 10, gear_level=5 at time of attempt → 10 + 5 = 15
        self.assertEqual(row[0], 15)

    async def test_risky_success_does_not_change_risky_failed_levels(self):
        """A successful risky upgrade must NOT modify risky_failed_levels."""
        async with schema.get_connection() as db:
            await db.execute(
                "UPDATE players SET risky_failed_levels=7 WHERE user_id=?", (USER,)
            )
            await db.commit()
        with patch("managers.gear_manager.random.random", return_value=0.0):
            async with schema.get_connection() as db:
                await gear_manager.attempt_upgrade(db, USER, "gathering", NOW, mode="risky")
                await db.commit()
        row = await self.fetchone(
            "SELECT risky_failed_levels FROM players WHERE user_id=?", (USER,)
        )
        self.assertEqual(row[0], 7)

    # -------------------------------------------------------------------------
    # risky_failed_levels contributes to final_rate in risky mode only
    # -------------------------------------------------------------------------

    def test_compute_rate_risky_includes_failed_levels_bonus(self):
        """risky_failed_levels × 0.0001 added to rate in risky mode."""
        rate_without = gear_manager._compute_rate(5, 0, risky_failed_levels=0, mode="risky")
        rate_with = gear_manager._compute_rate(5, 0, risky_failed_levels=1000, mode="risky")
        # 1000 × 0.0001 = 0.10 bonus
        self.assertAlmostEqual(rate_with - rate_without, 0.10, places=9)

    def test_compute_rate_normal_includes_failed_levels_bonus(self):
        """risky_failed_levels × 0.0001 added to rate in normal mode."""
        rate_without = gear_manager._compute_rate(5, 0, risky_failed_levels=0, mode="normal")
        rate_with = gear_manager._compute_rate(5, 0, risky_failed_levels=1000, mode="normal")
        # 1000 × 0.0001 = 0.10 bonus
        self.assertAlmostEqual(rate_with - rate_without, 0.10, places=9)

    def test_compute_rate_buffer_ignores_failed_levels(self):
        """risky_failed_levels must NOT affect rate in buffer mode."""
        rate_without = gear_manager._compute_rate(5, 0, risky_failed_levels=0, mode="buffer")
        rate_with = gear_manager._compute_rate(5, 0, risky_failed_levels=1000, mode="buffer")
        self.assertAlmostEqual(rate_without, rate_with)

    async def test_get_upgrade_info_normal_rate_includes_failed_levels(self):
        """get_upgrade_info() rate for normal mode also reflects risky_failed_levels."""
        async with schema.get_connection() as db:
            await db.execute(
                "UPDATE players SET risky_failed_levels=1000 WHERE user_id=?", (USER,)
            )
            await db.commit()
        async with schema.get_connection() as db:
            info_with = await gear_manager.get_upgrade_info(db, USER, "gathering", NOW, mode="normal")
        async with schema.get_connection() as db:
            await db.execute(
                "UPDATE players SET risky_failed_levels=0 WHERE user_id=?", (USER,)
            )
            await db.commit()
        async with schema.get_connection() as db:
            info_without = await gear_manager.get_upgrade_info(db, USER, "gathering", NOW, mode="normal")
        # 1000 × 0.0001 = 0.10 bonus
        self.assertAlmostEqual(info_with["rate"] - info_without["rate"], 0.10, places=9)

    # -------------------------------------------------------------------------
    # Risky success: level_gain is 1/2/3 (50/35/15%), regardless of pity state
    # -------------------------------------------------------------------------

    async def test_risky_success_pity_zero_level_gain_1(self):
        """pity=0: level_gain follows random.choices result."""
        with patch("managers.gear_manager.random.random", return_value=0.0), \
             patch("managers.gear_manager.random.choices", return_value=[1]):
            async with schema.get_connection() as db:
                result = await gear_manager.attempt_upgrade(db, USER, "gathering", NOW, mode="risky")
                await db.commit()
        self.assertTrue(result["success"])
        self.assertEqual(result["level_gain"], 1)
        self.assertEqual(result["new_level"], 6)

    async def test_risky_success_pity_positive_level_gain_follows_random(self):
        """pity>0: level_gain still follows random.choices, not forced to 1."""
        async with schema.get_connection() as db:
            await db.execute(
                "UPDATE players SET pity_gathering=2 WHERE user_id=?", (USER,)
            )
            await db.commit()
        with patch("managers.gear_manager.random.random", return_value=0.0), \
             patch("managers.gear_manager.random.choices", return_value=[2]):
            async with schema.get_connection() as db:
                result = await gear_manager.attempt_upgrade(db, USER, "gathering", NOW, mode="risky")
                await db.commit()
        self.assertTrue(result["success"])
        self.assertEqual(result["level_gain"], 2)
        self.assertEqual(result["new_level"], 7)

    # -------------------------------------------------------------------------
    # get_upgrade_info() returns risky_failed_levels and risky_bonus_pct
    # -------------------------------------------------------------------------

    async def test_get_upgrade_info_risky_returns_risky_fields(self):
        """get_upgrade_info() in risky mode returns risky_failed_levels and risky_bonus_pct."""
        async with schema.get_connection() as db:
            await db.execute(
                "UPDATE players SET risky_failed_levels=200 WHERE user_id=?", (USER,)
            )
            await db.commit()
        async with schema.get_connection() as db:
            info = await gear_manager.get_upgrade_info(db, USER, "gathering", NOW, mode="risky")
        self.assertIn("risky_failed_levels", info)
        self.assertIn("risky_bonus_pct", info)
        self.assertEqual(info["risky_failed_levels"], 200)
        self.assertAlmostEqual(info["risky_bonus_pct"], 2.0)

    async def test_get_upgrade_info_normal_returns_risky_fields(self):
        """get_upgrade_info() in normal mode returns risky_failed_levels and risky_bonus_pct."""
        async with schema.get_connection() as db:
            await db.execute(
                "UPDATE players SET risky_failed_levels=200 WHERE user_id=?", (USER,)
            )
            await db.commit()
        async with schema.get_connection() as db:
            info = await gear_manager.get_upgrade_info(db, USER, "gathering", NOW, mode="normal")
        self.assertIn("risky_failed_levels", info)
        self.assertIn("risky_bonus_pct", info)
        self.assertEqual(info["risky_failed_levels"], 200)
        self.assertAlmostEqual(info["risky_bonus_pct"], 2.0)

    async def test_get_upgrade_info_buffer_does_not_return_risky_fields(self):
        """get_upgrade_info() in buffer mode must NOT include risky-specific fields."""
        async with schema.get_connection() as db:
            info = await gear_manager.get_upgrade_info(db, USER, "gathering", NOW, mode="buffer")
        self.assertNotIn("risky_failed_levels", info)
        self.assertNotIn("risky_bonus_pct", info)

    async def test_get_upgrade_info_risky_bonus_pct_rounded_to_2_decimals(self):
        """risky_bonus_pct is rounded to 2 decimal places."""
        async with schema.get_connection() as db:
            await db.execute(
                "UPDATE players SET risky_failed_levels=333 WHERE user_id=?", (USER,)
            )
            await db.commit()
        async with schema.get_connection() as db:
            info = await gear_manager.get_upgrade_info(db, USER, "gathering", NOW, mode="risky")
        # 333 × 0.01 = 3.33
        self.assertEqual(info["risky_bonus_pct"], 3.33)

    # -------------------------------------------------------------------------
    # attempt_upgrade() returns level_gain
    # -------------------------------------------------------------------------

    async def test_attempt_upgrade_returns_level_gain_on_success(self):
        """attempt_upgrade() result dict includes level_gain from random.choices on risky success."""
        with patch("managers.gear_manager.random.random", return_value=0.0), \
             patch("managers.gear_manager.random.choices", return_value=[2]):
            async with schema.get_connection() as db:
                result = await gear_manager.attempt_upgrade(db, USER, "gathering", NOW, mode="risky")
                await db.commit()
        self.assertIn("level_gain", result)
        self.assertEqual(result["level_gain"], 2)

    async def test_attempt_upgrade_returns_level_gain_zero_on_failure(self):
        """attempt_upgrade() result dict includes level_gain=0 on failure."""
        with patch("managers.gear_manager.random.random", return_value=0.9999):
            async with schema.get_connection() as db:
                result = await gear_manager.attempt_upgrade(db, USER, "gathering", NOW, mode="risky")
                await db.commit()
        self.assertIn("level_gain", result)
        self.assertEqual(result["level_gain"], 0)

    async def test_attempt_upgrade_normal_returns_level_gain_one_on_success(self):
        """attempt_upgrade() in normal mode returns level_gain=1 on success."""
        with patch("managers.gear_manager.random.random", return_value=0.0):
            async with schema.get_connection() as db:
                result = await gear_manager.attempt_upgrade(db, USER, "gathering", NOW)
                await db.commit()
        self.assertIn("level_gain", result)
        self.assertEqual(result["level_gain"], 1)

    async def test_attempt_upgrade_normal_rate_reflects_risky_failed_levels(self):
        """attempt_upgrade() in normal mode: returned rate includes risky_failed_levels bonus."""
        async with schema.get_connection() as db:
            await db.execute(
                "UPDATE players SET risky_failed_levels=1000 WHERE user_id=?", (USER,)
            )
            await db.commit()
        with patch("managers.gear_manager.random.random", return_value=0.0):
            async with schema.get_connection() as db:
                result = await gear_manager.attempt_upgrade(db, USER, "gathering", NOW)
                await db.commit()
        # gear_level=5 base=0.50; +1000×0.0001=0.10 → 0.60
        expected_rate = gear_manager._compute_rate(5, 0, risky_failed_levels=1000, mode="normal")
        self.assertAlmostEqual(result["rate"], expected_rate)


class TestAffixIntegration(DatabaseTestCase):
    """gear_manager correctly applies affix bonuses during upgrade."""

    async def asyncSetUp(self):
        await super().asyncSetUp()
        async with schema.get_connection() as db:
            await _insert_player(db, USER, "gathering", gear_level=5, materials=20)
            await db.execute("UPDATE buildings SET level=10 WHERE building_type='research_lab'")
            await db.execute(
                "UPDATE players SET ap_full_time=? WHERE user_id=?",
                (NOW.isoformat(), USER),
            )
            await db.commit()

    async def _insert_affix(self, db, affix_type, value, slot_index=0):
        await db.execute(
            "INSERT INTO gear_affixes (user_id, gear_type, slot_index, affix_type, value) VALUES (?,?,?,?,?)",
            (USER, "gathering", slot_index, affix_type, value),
        )

    async def test_upgrade_cost_reduce_lowers_material_cost(self):
        """upgrade_cost_reduce affix reduces material cost (floor, min 1)."""
        async with schema.get_connection() as db:
            await self._insert_affix(db, "upgrade_cost_reduce", 50)
            await db.commit()
        info = None
        async with schema.get_connection() as db:
            info = await gear_manager.get_upgrade_info(db, USER, "gathering", NOW, "normal")
        # target_level=6, base_cost=6, -50% = 3
        self.assertEqual(info["material_cost"], 3)

    async def test_upgrade_success_affix_adds_to_rate(self):
        """upgrade_success affix increases the displayed and actual success rate."""
        async with schema.get_connection() as db:
            await self._insert_affix(db, "upgrade_success", 5)
            await db.commit()
        async with schema.get_connection() as db:
            info = await gear_manager.get_upgrade_info(db, USER, "gathering", NOW, "normal")
        base_rate = gear_manager._compute_rate(5, 0, 0, mode="normal")
        self.assertAlmostEqual(info["rate"], min(1.0, base_rate + 0.05))

    async def test_ap_refund_triggered_on_success(self):
        """upgrade_ap_refund affix refunds 1 AP when triggered."""
        async with schema.get_connection() as db:
            await self._insert_affix(db, "upgrade_ap_refund", 100)
            await db.commit()
        with patch("managers.gear_manager.random.random", return_value=0.0):
            async with schema.get_connection() as db:
                result = await gear_manager.attempt_upgrade(db, USER, "gathering", NOW)
                await db.commit()
        self.assertTrue(result["success"])
        self.assertTrue(result["ap_refunded"])

    async def test_material_refund_triggered_on_success(self):
        """upgrade_material_refund affix refunds spent materials when triggered."""
        async with schema.get_connection() as db:
            await self._insert_affix(db, "upgrade_material_refund", 100)
            await db.commit()
        with patch("managers.gear_manager.random.random", return_value=0.0):
            async with schema.get_connection() as db:
                result = await gear_manager.attempt_upgrade(db, USER, "gathering", NOW)
                await db.commit()
                mats = await player_manager.get_material(db, USER, "gathering")
        self.assertTrue(result["material_refunded"])
        # target_level=6 → cost=6, refunded → net = 20 - 6 + 6 = 20
        self.assertEqual(mats, 20)

    async def test_risky_failure_clears_all_affixes(self):
        """risky failure clears all affixes for that tool."""
        async with schema.get_connection() as db:
            await self._insert_affix(db, "efficiency", 3, slot_index=0)
            await db.commit()
        with patch("managers.gear_manager.random.random", return_value=1.0):
            async with schema.get_connection() as db:
                await gear_manager.attempt_upgrade(db, USER, "gathering", NOW, mode="risky")
                await db.commit()
        from managers import affix_manager
        async with schema.get_connection() as db:
            affixes = await affix_manager.get_affixes(db, USER, "gathering")
        self.assertEqual(affixes, [])

    async def test_refund_not_triggered_on_failure(self):
        """AP and material refund affixes do not trigger on failure."""
        async with schema.get_connection() as db:
            await self._insert_affix(db, "upgrade_ap_refund", 100, slot_index=0)
            await self._insert_affix(db, "upgrade_material_refund", 100, slot_index=1)
            await db.commit()
        with patch("managers.gear_manager.random.random", return_value=1.0):
            async with schema.get_connection() as db:
                result = await gear_manager.attempt_upgrade(db, USER, "gathering", NOW, mode="normal")
                await db.commit()
        self.assertFalse(result["success"])
        self.assertFalse(result["ap_refunded"])
        self.assertFalse(result["material_refunded"])


class TestSacrificeMaterial(DatabaseTestCase):
    """Tests for gear_manager.sacrifice_material()."""

    async def asyncSetUp(self):
        await super().asyncSetUp()
        async with schema.get_connection() as db:
            await _insert_player(db, USER, "gathering", gear_level=3, materials=10, risky_failed_levels=0)
            await _set_research_lab_level(db, 10)

    async def test_sacrifice_deducts_materials_and_increments_risky_failed_levels(self):
        """Sacrificing N materials deducts them and adds N to risky_failed_levels."""
        async with schema.get_connection() as db:
            result = await gear_manager.sacrifice_material(db, USER, "gathering", 5, NOW)
            await db.commit()
        self.assertEqual(result["type"], "sacrifice")
        self.assertEqual(result["sacrificed"], 5)
        self.assertEqual(result["risky_failed_levels_after"], 5)
        row = await self.fetchone(
            "SELECT materials_gathering, risky_failed_levels FROM players WHERE user_id=?", (USER,)
        )
        self.assertEqual(row[0], 5)
        self.assertEqual(row[1], 5)

    async def test_sacrifice_raises_on_insufficient_materials(self):
        """ValueError when requested amount exceeds holdings."""
        async with schema.get_connection() as db:
            with self.assertRaises(ValueError):
                await gear_manager.sacrifice_material(db, USER, "gathering", 99, NOW)

    async def test_sacrifice_does_not_consume_ap(self):
        """AP must not change after sacrifice."""
        ap_before_row = await self.fetchone(
            "SELECT ap_full_time FROM players WHERE user_id=?", (USER,)
        )
        async with schema.get_connection() as db:
            await gear_manager.sacrifice_material(db, USER, "gathering", 3, NOW)
            await db.commit()
        ap_after_row = await self.fetchone(
            "SELECT ap_full_time FROM players WHERE user_id=?", (USER,)
        )
        self.assertEqual(ap_before_row[0], ap_after_row[0])


class TestUniversalMaterial(DatabaseTestCase):
    """Tests for player_manager's universal material accessors."""

    async def asyncSetUp(self):
        await super().asyncSetUp()
        async with schema.get_connection() as db:
            await _insert_player(db, USER, "gathering", universal_materials=10)

    async def test_get_universal_material_returns_current_balance(self):
        async with schema.get_connection() as db:
            value = await player_manager.get_universal_material(db, USER)
        self.assertEqual(value, 10)

    async def test_add_universal_material_increments_balance(self):
        async with schema.get_connection() as db:
            await player_manager.add_universal_material(db, USER, 5, NOW)
            await db.commit()
            value = await player_manager.get_universal_material(db, USER)
        self.assertEqual(value, 15)

    async def test_spend_universal_material_succeeds_and_deducts(self):
        async with schema.get_connection() as db:
            ok = await player_manager.spend_universal_material(db, USER, 4, NOW)
            await db.commit()
            value = await player_manager.get_universal_material(db, USER)
        self.assertTrue(ok)
        self.assertEqual(value, 6)

    async def test_spend_universal_material_fails_when_insufficient(self):
        async with schema.get_connection() as db:
            ok = await player_manager.spend_universal_material(db, USER, 99, NOW)
            await db.commit()
            value = await player_manager.get_universal_material(db, USER)
        self.assertFalse(ok)
        self.assertEqual(value, 10)

    async def test_set_universal_material_sets_absolute_value(self):
        async with schema.get_connection() as db:
            await player_manager.set_universal_material(db, USER, 42, NOW)
            await db.commit()
            value = await player_manager.get_universal_material(db, USER)
        self.assertEqual(value, 42)


if __name__ == "__main__":
    unittest.main()

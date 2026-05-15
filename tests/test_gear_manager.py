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
                          risky_failed_levels: int = 0) -> None:
    """Helper: insert a player row with specific gear state."""
    from core.utils import dt_str
    from core.formula import ACTION_GEAR_COL, ACTION_MATERIAL_COL

    gear_col = ACTION_GEAR_COL[gear_type]
    mat_col = ACTION_MATERIAL_COL[gear_type]
    now_str = dt_str(NOW)

    await db.execute(
        f"""INSERT INTO players
            (user_id, {gear_col}, {mat_col}, pity_{gear_type},
             risky_failed_levels,
             ap_full_time, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (user_id, gear_level, materials, pity, risky_failed_levels,
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

    async def test_risky_success_increases_gear_level(self):
        # level_gain is always 1 on risky success
        with patch("managers.gear_manager.random.random", return_value=0.0):
            async with schema.get_connection() as db:
                result = await gear_manager.attempt_upgrade(db, USER, "gathering", NOW, mode="risky")
                await db.commit()
        self.assertTrue(result["success"])
        self.assertEqual(result["level_gain"], 1)
        self.assertEqual(result["new_level"], 6)

    async def test_risky_success_resets_pity(self):
        with patch("managers.gear_manager.random.random", return_value=0.0):
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

    def test_compute_rate_normal_ignores_failed_levels(self):
        """risky_failed_levels must NOT affect rate in normal mode."""
        rate_without = gear_manager._compute_rate(5, 0, risky_failed_levels=0, mode="normal")
        rate_with = gear_manager._compute_rate(5, 0, risky_failed_levels=1000, mode="normal")
        self.assertAlmostEqual(rate_without, rate_with)

    def test_compute_rate_buffer_ignores_failed_levels(self):
        """risky_failed_levels must NOT affect rate in buffer mode."""
        rate_without = gear_manager._compute_rate(5, 0, risky_failed_levels=0, mode="buffer")
        rate_with = gear_manager._compute_rate(5, 0, risky_failed_levels=1000, mode="buffer")
        self.assertAlmostEqual(rate_without, rate_with)

    async def test_get_upgrade_info_risky_rate_includes_failed_levels(self):
        """get_upgrade_info() rate for risky mode reflects risky_failed_levels."""
        async with schema.get_connection() as db:
            await db.execute(
                "UPDATE players SET risky_failed_levels=1000 WHERE user_id=?", (USER,)
            )
            await db.commit()
        async with schema.get_connection() as db:
            info_risky = await gear_manager.get_upgrade_info(db, USER, "gathering", NOW, mode="risky")
            info_normal = await gear_manager.get_upgrade_info(db, USER, "gathering", NOW, mode="normal")
        # risky rate should be higher due to the 1000 × 0.0001 = 0.10 bonus
        self.assertGreater(info_risky["rate"], info_normal["rate"])

    # -------------------------------------------------------------------------
    # Risky success: level_gain is always 1, regardless of pity state
    # -------------------------------------------------------------------------

    async def test_risky_success_pity_zero_level_gain_1(self):
        """pity=0: level_gain is always +1."""
        with patch("managers.gear_manager.random.random", return_value=0.0):
            async with schema.get_connection() as db:
                result = await gear_manager.attempt_upgrade(db, USER, "gathering", NOW, mode="risky")
                await db.commit()
        self.assertTrue(result["success"])
        self.assertEqual(result["level_gain"], 1)
        self.assertEqual(result["new_level"], 6)

    async def test_risky_success_pity_positive_level_gain_always_1(self):
        """pity>0: level_gain is always +1."""
        async with schema.get_connection() as db:
            await db.execute(
                "UPDATE players SET pity_gathering=2 WHERE user_id=?", (USER,)
            )
            await db.commit()
        with patch("managers.gear_manager.random.random", return_value=0.0):
            async with schema.get_connection() as db:
                result = await gear_manager.attempt_upgrade(db, USER, "gathering", NOW, mode="risky")
                await db.commit()
        self.assertTrue(result["success"])
        self.assertEqual(result["level_gain"], 1)
        self.assertEqual(result["new_level"], 6)

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

    async def test_get_upgrade_info_normal_does_not_return_risky_fields(self):
        """get_upgrade_info() in normal mode must NOT include risky-specific fields."""
        async with schema.get_connection() as db:
            info = await gear_manager.get_upgrade_info(db, USER, "gathering", NOW, mode="normal")
        self.assertNotIn("risky_failed_levels", info)
        self.assertNotIn("risky_bonus_pct", info)

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
        """attempt_upgrade() result dict includes level_gain=1 on risky success."""
        with patch("managers.gear_manager.random.random", return_value=0.0):
            async with schema.get_connection() as db:
                result = await gear_manager.attempt_upgrade(db, USER, "gathering", NOW, mode="risky")
                await db.commit()
        self.assertIn("level_gain", result)
        self.assertEqual(result["level_gain"], 1)

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


if __name__ == "__main__":
    unittest.main()

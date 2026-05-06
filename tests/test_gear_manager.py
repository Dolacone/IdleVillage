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
                          materials: int = 0, pity: int = 0) -> None:
    """Helper: insert a player row with specific gear state."""
    from core.utils import dt_str
    from core.formula import ACTION_GEAR_COL, ACTION_MATERIAL_COL

    gear_col = ACTION_GEAR_COL[gear_type]
    mat_col = ACTION_MATERIAL_COL[gear_type]
    now_str = dt_str(NOW)

    await db.execute(
        f"""INSERT INTO players
            (user_id, {gear_col}, {mat_col}, pity_{gear_type},
             ap_full_time, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (user_id, gear_level, materials, pity, now_str, now_str, now_str),
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


if __name__ == "__main__":
    unittest.main()

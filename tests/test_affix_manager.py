"""
Tests for managers.affix_manager — affix slot management, extraction, and bonuses.
Mechanics reference: docs/managers/affix-manager.md
"""

import os
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from tests.support import ALL_TEST_ENV, DatabaseTestCase
from database import schema
from managers import affix_manager, player_manager
from core.utils import dt_str

NOW = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
USER = "user_affix_001"
GEAR = "gathering"


async def _insert_player(db, user_id: str, gear_type: str = GEAR, materials: int = 10, gear_level: int = 10) -> None:
    from core.formula import ACTION_GEAR_COL, ACTION_MATERIAL_COL
    gear_col = ACTION_GEAR_COL[gear_type]
    mat_col = ACTION_MATERIAL_COL[gear_type]
    now_str = dt_str(NOW)
    await db.execute(
        "INSERT OR IGNORE INTO players (user_id, ap_full_time, created_at, updated_at) VALUES (?, ?, ?, ?)",
        (user_id, now_str, now_str, now_str),
    )
    await db.execute(
        f"UPDATE players SET {gear_col}=?, {mat_col}=?, updated_at=? WHERE user_id=?",
        (gear_level, materials, now_str, user_id),
    )
    await db.commit()


class TestSlotCount(unittest.TestCase):
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

    def test_zero_slots_at_level_zero(self):
        self.assertEqual(affix_manager.slot_count(0), 0)

    def test_zero_slots_below_interval(self):
        self.assertEqual(affix_manager.slot_count(4), 0)

    def test_one_slot_at_interval(self):
        self.assertEqual(affix_manager.slot_count(5), 1)

    def test_two_slots_at_2x_interval(self):
        self.assertEqual(affix_manager.slot_count(10), 2)

    def test_slots_floor_not_ceil(self):
        self.assertEqual(affix_manager.slot_count(9), 1)


class TestExtractAffix(DatabaseTestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        async with schema.get_connection() as db:
            await _insert_player(db, USER, gear_level=10, materials=10)

    async def test_extract_fills_slot_zero(self):
        async with schema.get_connection() as db:
            with patch("random.choice", return_value="efficiency"), \
                 patch("random.randint", return_value=3):
                result = await affix_manager.extract_affix(db, USER, GEAR, 10, NOW)
            await db.commit()
        self.assertEqual(result["slot_index"], 0)
        self.assertEqual(result["affix_type"], "efficiency")
        self.assertEqual(result["value"], 3)

    async def test_extract_consumes_material(self):
        async with schema.get_connection() as db:
            await affix_manager.extract_affix(db, USER, GEAR, 10, NOW)
            await db.commit()
            mats = await player_manager.get_material(db, USER, GEAR)
        cost = int(os.environ["AFFIX_EXTRACT_COST"])
        self.assertEqual(mats, 10 - cost)

    async def test_extract_second_fills_slot_one(self):
        async with schema.get_connection() as db:
            await affix_manager.extract_affix(db, USER, GEAR, 10, NOW)
            result2 = await affix_manager.extract_affix(db, USER, GEAR, 10, NOW)
            await db.commit()
        self.assertEqual(result2["slot_index"], 1)

    async def test_extract_raises_when_no_slots_unlocked(self):
        async with schema.get_connection() as db:
            await _insert_player(db, "u2", gear_level=0, materials=10)
            with self.assertRaises(ValueError, msg="no slots unlocked"):
                await affix_manager.extract_affix(db, "u2", GEAR, 0, NOW)

    async def test_extract_raises_when_all_slots_full(self):
        async with schema.get_connection() as db:
            await _insert_player(db, "u3", gear_level=5, materials=20)
            await affix_manager.extract_affix(db, "u3", GEAR, 5, NOW)
            await db.commit()
            with self.assertRaises(ValueError, msg="slots full"):
                await affix_manager.extract_affix(db, "u3", GEAR, 5, NOW)

    async def test_extract_raises_on_insufficient_materials(self):
        async with schema.get_connection() as db:
            await _insert_player(db, "u4", gear_level=10, materials=0)
            with self.assertRaises(ValueError):
                await affix_manager.extract_affix(db, "u4", GEAR, 10, NOW)

    async def test_extract_raises_on_invalid_gear_type(self):
        async with schema.get_connection() as db:
            with self.assertRaises(ValueError):
                await affix_manager.extract_affix(db, USER, "invalid", 10, NOW)

    async def test_extract_own_type_sufficient_ignores_universal(self):
        cost = int(os.environ["AFFIX_EXTRACT_COST"])
        async with schema.get_connection() as db:
            await player_manager.set_universal_material(db, USER, 5, NOW)
            await db.commit()
            await affix_manager.extract_affix(db, USER, GEAR, 10, NOW)
            await db.commit()
            mats = await player_manager.get_material(db, USER, GEAR)
            universal = await player_manager.get_universal_material(db, USER)
        self.assertEqual(mats, 10 - cost)
        self.assertEqual(universal, 5)

    async def test_extract_uses_universal_for_shortfall(self):
        cost = int(os.environ["AFFIX_EXTRACT_COST"])
        async with schema.get_connection() as db:
            await _insert_player(db, "u_uni", gear_level=10, materials=0)
            await player_manager.set_universal_material(db, "u_uni", cost, NOW)
            await db.commit()
            result = await affix_manager.extract_affix(db, "u_uni", GEAR, 10, NOW)
            await db.commit()
            mats = await player_manager.get_material(db, "u_uni", GEAR)
            universal = await player_manager.get_universal_material(db, "u_uni")
        self.assertEqual(result["slot_index"], 0)
        self.assertEqual(mats, 0)
        self.assertEqual(universal, 0)

    async def test_extract_mixes_own_type_then_universal(self):
        # Force cost=2 so own-type (1) and universal must split; would fail if the
        # deduction were universal-first (universal would drop by 2, mats stay at 1).
        with patch.dict(os.environ, {"AFFIX_EXTRACT_COST": "2"}):
            async with schema.get_connection() as db:
                await _insert_player(db, "u_mix", gear_level=10, materials=1)
                await player_manager.set_universal_material(db, "u_mix", 5, NOW)
                await db.commit()
                await affix_manager.extract_affix(db, "u_mix", GEAR, 10, NOW)
                await db.commit()
                mats = await player_manager.get_material(db, "u_mix", GEAR)
                universal = await player_manager.get_universal_material(db, "u_mix")
        self.assertEqual(mats, 0)
        self.assertEqual(universal, 4)

    async def test_extract_raises_when_combined_insufficient_and_no_spend(self):
        cost = int(os.environ["AFFIX_EXTRACT_COST"])
        async with schema.get_connection() as db:
            await _insert_player(db, "u_short", gear_level=10, materials=cost - 1 if cost > 0 else 0)
            await player_manager.set_universal_material(db, "u_short", 0, NOW)
            await db.commit()
            with self.assertRaises(ValueError):
                await affix_manager.extract_affix(db, "u_short", GEAR, 10, NOW)
            await db.commit()
            mats = await player_manager.get_material(db, "u_short", GEAR)
            universal = await player_manager.get_universal_material(db, "u_short")
            affixes = await affix_manager.get_affixes(db, "u_short", GEAR)
        self.assertEqual(mats, cost - 1 if cost > 0 else 0)
        self.assertEqual(universal, 0)
        self.assertEqual(affixes, [])


class TestAutoExtractAffix(DatabaseTestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        async with schema.get_connection() as db:
            await _insert_player(db, USER, gear_level=10, materials=10_000)

    async def _balances(self, user_id=USER):
        async with schema.get_connection() as db:
            return (
                await player_manager.get_material(db, user_id, GEAR),
                await player_manager.get_universal_material(db, user_id),
            )

    async def test_tool_source_spends_only_tool_material_and_counts_success_attempt(self):
        async with schema.get_connection() as db:
            await player_manager.set_universal_material(db, USER, 25, NOW)
            await db.commit()
            with patch("random.choice", side_effect=["material_drop", "efficiency"]), \
                 patch("random.randint", side_effect=[5, 3]):
                result = await affix_manager.auto_extract_affix(
                    db, USER, GEAR, 10, NOW, target_affix_type="efficiency", min_value=3
                )
            await db.commit()
        self.assertEqual(result, {
            "affix": {"slot_index": 0, "affix_type": "efficiency", "value": 3},
            "attempts": 2, "material_spent": 2, "material_source": "tool",
        })
        self.assertEqual(await self._balances(), (9_998, 25))

    async def test_universal_source_spends_five_per_attempt_and_preserves_remainder(self):
        async with schema.get_connection() as db:
            await player_manager.set_material(db, USER, GEAR, 20, NOW)
            await player_manager.set_universal_material(db, USER, 17, NOW)
            await db.commit()
            with patch("random.choice", return_value="efficiency"), patch("random.randint", return_value=1):
                result = await affix_manager.auto_extract_affix(
                    db, USER, GEAR, 10, NOW, min_value=2, material_source="universal"
                )
            await db.commit()
        self.assertEqual(result["attempts"], 3)
        self.assertEqual(result["material_spent"], 15)
        self.assertIsNone(result["affix"])
        self.assertEqual(await self._balances(), (20, 2))

    async def test_any_type_still_requires_threshold(self):
        async with schema.get_connection() as db:
            with patch("random.choice", side_effect=["efficiency", "cycle_time_reduce"]), \
                 patch("random.randint", side_effect=[2, 4]):
                result = await affix_manager.auto_extract_affix(db, USER, GEAR, 10, NOW, min_value=4)
            await db.commit()
        self.assertEqual(result["attempts"], 2)
        self.assertEqual(result["affix"]["affix_type"], "cycle_time_reduce")
        self.assertEqual(result["affix"]["value"], 4)

    async def test_target_type_and_threshold_both_must_match(self):
        async with schema.get_connection() as db:
            with patch("random.choice", side_effect=["material_drop", "efficiency", "efficiency"]), \
                 patch("random.randint", side_effect=[5, 2, 4]):
                result = await affix_manager.auto_extract_affix(
                    db, USER, GEAR, 10, NOW, target_affix_type="efficiency", min_value=4
                )
            await db.commit()
        self.assertEqual(result["attempts"], 3)
        self.assertEqual(result["affix"]["value"], 4)

    async def test_failure_keeps_slot_empty_and_preserves_existing_affixes(self):
        async with schema.get_connection() as db:
            await db.execute(
                "INSERT INTO gear_affixes (user_id, gear_type, slot_index, affix_type, value) VALUES (?,?,?,?,?)",
                (USER, GEAR, 1, "efficiency", 2),
            )
            await db.commit()
            with patch("random.choice", return_value="material_drop"), patch("random.randint", return_value=1):
                result = await affix_manager.auto_extract_affix(
                    db, USER, GEAR, 10, NOW, target_affix_type="efficiency"
                )
            await db.commit()
            affixes = await affix_manager.get_affixes(db, USER, GEAR)
        self.assertIsNone(result["affix"])
        self.assertEqual(affixes, [{"slot_index": 1, "affix_type": "efficiency", "value": 2}])

    async def test_success_fills_first_hole_only(self):
        async with schema.get_connection() as db:
            await db.execute(
                "INSERT INTO gear_affixes (user_id, gear_type, slot_index, affix_type, value) VALUES (?,?,?,?,?)",
                (USER, GEAR, 1, "efficiency", 2),
            )
            await db.commit()
            with patch("random.choice", return_value="cycle_time_reduce"), patch("random.randint", return_value=5):
                result = await affix_manager.auto_extract_affix(db, USER, GEAR, 10, NOW)
            await db.commit()
        self.assertEqual(result["affix"], {"slot_index": 0, "affix_type": "cycle_time_reduce", "value": 5})

    async def test_invalid_arguments_do_not_spend(self):
        cases = [
            {"gear_type": "bad"}, {"target_affix_type": "bad"}, {"min_value": 0},
            {"min_value": 6}, {"min_value": True}, {"material_source": "mixed"},
        ]
        for kwargs in cases:
            async with schema.get_connection() as db:
                gear_type = kwargs.pop("gear_type", GEAR)
                with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                    await affix_manager.auto_extract_affix(db, USER, gear_type, 10, NOW, **kwargs)
                await db.commit()
                self.assertEqual(await player_manager.get_material(db, USER, GEAR), 10_000)

    async def test_full_slots_and_no_unlocked_slot_reject_without_spending(self):
        async with schema.get_connection() as db:
            await _insert_player(db, "auto_full", gear_level=5, materials=100)
            await affix_manager.extract_affix(db, "auto_full", GEAR, 5, NOW)
            await db.commit()
            with self.assertRaises(ValueError):
                await affix_manager.auto_extract_affix(db, "auto_full", GEAR, 5, NOW)
            await db.rollback()
            self.assertEqual(await player_manager.get_material(db, "auto_full", GEAR), 100 - int(os.environ["AFFIX_EXTRACT_COST"]))
            with self.assertRaises(ValueError):
                await affix_manager.auto_extract_affix(db, USER, GEAR, 0, NOW)
            await db.rollback()
        self.assertEqual(await self._balances(), (10_000, 0))

    async def test_selected_balance_exhaustion_rejects_without_spending_other_source(self):
        async with schema.get_connection() as db:
            await player_manager.set_material(db, USER, GEAR, 0, NOW)
            await player_manager.set_universal_material(db, USER, 4, NOW)
            await db.commit()
            with self.assertRaises(ValueError):
                await affix_manager.auto_extract_affix(db, USER, GEAR, 10, NOW, material_source="universal")
            await db.rollback()
        self.assertEqual(await self._balances(), (0, 4))

    async def test_material_added_during_sampling_is_outside_budget_snapshot(self):
        async with schema.get_connection() as db:
            await player_manager.set_material(db, USER, GEAR, 150, NOW)
            await db.commit()
            first_yield = True

            async def add_material(_):
                nonlocal first_yield
                if first_yield:
                    first_yield = False
                    async with schema.get_connection() as other:
                        await player_manager.set_material(other, USER, GEAR, 200, NOW)
                        await other.commit()

            with patch("asyncio.sleep", side_effect=add_material) as sleeper, \
                 patch("random.choice", return_value="material_drop"), patch("random.randint", return_value=1):
                result = await affix_manager.auto_extract_affix(
                    db, USER, GEAR, 10, NOW, target_affix_type="efficiency"
                )
            await db.commit()
        self.assertEqual(sleeper.call_count, 1)
        self.assertEqual(result["attempts"], 150)
        self.assertEqual(await self._balances(), (50, 0))

    async def test_material_reduced_during_sampling_truncates_attempts(self):
        async with schema.get_connection() as db:
            await player_manager.set_material(db, USER, GEAR, 150, NOW)
            await db.commit()
            did_reduce = False

            async def reduce_material(_):
                nonlocal did_reduce
                if not did_reduce:
                    did_reduce = True
                    async with schema.get_connection() as other:
                        await player_manager.set_material(other, USER, GEAR, 30, NOW)
                        await other.commit()

            with patch("asyncio.sleep", side_effect=reduce_material), \
                 patch("random.choice", return_value="material_drop"), patch("random.randint", return_value=1):
                result = await affix_manager.auto_extract_affix(
                    db, USER, GEAR, 10, NOW, target_affix_type="efficiency"
                )
            await db.commit()
        self.assertEqual(result["attempts"], 30)
        self.assertEqual(result["material_spent"], 30)
        self.assertIsNone(result["affix"])
        self.assertEqual(await self._balances(), (0, 0))

    async def test_match_past_reduced_budget_is_discarded(self):
        async with schema.get_connection() as db:
            await player_manager.set_material(db, USER, GEAR, 150, NOW)
            await db.commit()
            did_reduce = False

            async def reduce_material(_):
                nonlocal did_reduce
                if not did_reduce:
                    did_reduce = True
                    async with schema.get_connection() as other:
                        await player_manager.set_material(other, USER, GEAR, 30, NOW)
                        await other.commit()

            with patch("asyncio.sleep", side_effect=reduce_material), \
                 patch("random.choice", side_effect=["material_drop"] * 100 + ["efficiency"]), \
                 patch("random.randint", side_effect=[1] * 100 + [5]):
                result = await affix_manager.auto_extract_affix(
                    db, USER, GEAR, 10, NOW, target_affix_type="efficiency"
                )
            await db.commit()
        self.assertEqual(result["attempts"], 30)
        self.assertIsNone(result["affix"])

    async def test_latest_full_slots_reject_and_caller_rolls_back(self):
        async with schema.get_connection() as db:
            await player_manager.set_material(db, USER, GEAR, 150, NOW)
            await db.commit()
            did_fill = False

            async def fill_slots(_):
                nonlocal did_fill
                if not did_fill:
                    did_fill = True
                    async with schema.get_connection() as other:
                        await other.executemany(
                            "INSERT INTO gear_affixes (user_id, gear_type, slot_index, affix_type, value) VALUES (?,?,?,?,?)",
                            [(USER, GEAR, i, "efficiency", i + 1) for i in range(2)],
                        )
                        await other.commit()

            with patch("asyncio.sleep", side_effect=fill_slots), \
                 patch("random.choice", return_value="material_drop"), patch("random.randint", return_value=1):
                with self.assertRaises(ValueError):
                    await affix_manager.auto_extract_affix(
                        db, USER, GEAR, 10, NOW, target_affix_type="efficiency"
                    )
            await db.rollback()
        self.assertEqual(await self._balances(), (150, 0))


class TestClearAffix(DatabaseTestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        async with schema.get_connection() as db:
            await _insert_player(db, USER, gear_level=10, materials=20)
            await affix_manager.extract_affix(db, USER, GEAR, 10, NOW)
            await db.commit()

    async def test_clear_removes_affix(self):
        async with schema.get_connection() as db:
            await affix_manager.clear_affix(db, USER, GEAR, 0, 10, NOW)
            await db.commit()
            affixes = await affix_manager.get_affixes(db, USER, GEAR)
        self.assertEqual(affixes, [])

    async def test_clear_consumes_material(self):
        before_mats = 20 - int(os.environ["AFFIX_EXTRACT_COST"])
        async with schema.get_connection() as db:
            await affix_manager.clear_affix(db, USER, GEAR, 0, 10, NOW)
            await db.commit()
            mats = await player_manager.get_material(db, USER, GEAR)
        cost = int(os.environ["AFFIX_CLEAR_COST"])
        self.assertEqual(mats, before_mats - cost)

    async def test_clear_raises_on_empty_slot(self):
        async with schema.get_connection() as db:
            with self.assertRaises(ValueError, msg="slot already empty"):
                await affix_manager.clear_affix(db, USER, GEAR, 1, 10, NOW)

    async def test_clear_raises_on_out_of_range_slot(self):
        async with schema.get_connection() as db:
            with self.assertRaises(ValueError, msg="slot out of range"):
                await affix_manager.clear_affix(db, USER, GEAR, 99, 10, NOW)

    async def test_clear_raises_on_invalid_gear_type(self):
        async with schema.get_connection() as db:
            with self.assertRaises(ValueError):
                await affix_manager.clear_affix(db, USER, "bad", 0, 10, NOW)

    async def _setup_player_with_affix(self, db, user_id, materials):
        await _insert_player(db, user_id, gear_level=10, materials=materials + int(os.environ["AFFIX_EXTRACT_COST"]))
        await affix_manager.extract_affix(db, user_id, GEAR, 10, NOW)
        await db.commit()

    async def test_clear_own_type_sufficient_ignores_universal(self):
        cost = int(os.environ["AFFIX_CLEAR_COST"])
        async with schema.get_connection() as db:
            await self._setup_player_with_affix(db, "c_own", materials=cost)
            await player_manager.set_universal_material(db, "c_own", 5, NOW)
            await db.commit()
            await affix_manager.clear_affix(db, "c_own", GEAR, 0, 10, NOW)
            await db.commit()
            mats = await player_manager.get_material(db, "c_own", GEAR)
            universal = await player_manager.get_universal_material(db, "c_own")
        self.assertEqual(mats, 0)
        self.assertEqual(universal, 5)

    async def test_clear_uses_universal_for_shortfall(self):
        cost = int(os.environ["AFFIX_CLEAR_COST"])
        async with schema.get_connection() as db:
            await self._setup_player_with_affix(db, "c_uni", materials=0)
            await player_manager.set_universal_material(db, "c_uni", cost, NOW)
            await db.commit()
            await affix_manager.clear_affix(db, "c_uni", GEAR, 0, 10, NOW)
            await db.commit()
            mats = await player_manager.get_material(db, "c_uni", GEAR)
            universal = await player_manager.get_universal_material(db, "c_uni")
            affixes = await affix_manager.get_affixes(db, "c_uni", GEAR)
        self.assertEqual(mats, 0)
        self.assertEqual(universal, 0)
        self.assertEqual(affixes, [])

    async def test_clear_mixes_own_type_then_universal(self):
        cost = int(os.environ["AFFIX_CLEAR_COST"])
        if cost < 2:
            self.skipTest("AFFIX_CLEAR_COST too low to split across sources")
        async with schema.get_connection() as db:
            await self._setup_player_with_affix(db, "c_mix", materials=1)
            await player_manager.set_universal_material(db, "c_mix", cost, NOW)
            await db.commit()
            await affix_manager.clear_affix(db, "c_mix", GEAR, 0, 10, NOW)
            await db.commit()
            mats = await player_manager.get_material(db, "c_mix", GEAR)
            universal = await player_manager.get_universal_material(db, "c_mix")
        self.assertEqual(mats, 0)
        # own-type had 1, so shortfall = cost - 1 drawn from universal (started at cost)
        self.assertEqual(universal, cost - (cost - 1))

    async def test_clear_raises_when_combined_insufficient_and_no_spend(self):
        cost = int(os.environ["AFFIX_CLEAR_COST"])
        async with schema.get_connection() as db:
            await self._setup_player_with_affix(db, "c_short", materials=1)
            await player_manager.set_universal_material(db, "c_short", 0, NOW)
            await db.commit()
            with self.assertRaises(ValueError):
                await affix_manager.clear_affix(db, "c_short", GEAR, 0, 10, NOW)
            await db.commit()
            mats = await player_manager.get_material(db, "c_short", GEAR)
            universal = await player_manager.get_universal_material(db, "c_short")
            affixes = await affix_manager.get_affixes(db, "c_short", GEAR)
        self.assertEqual(mats, 1)
        self.assertEqual(universal, 0)
        self.assertEqual(len(affixes), 1)


class TestClearAllAffixes(DatabaseTestCase):
    async def test_clear_all_removes_all_affixes(self):
        async with schema.get_connection() as db:
            await _insert_player(db, USER, gear_level=10, materials=10)
            await affix_manager.extract_affix(db, USER, GEAR, 10, NOW)
            await affix_manager.extract_affix(db, USER, GEAR, 10, NOW)
            await db.commit()
            await affix_manager.clear_all_affixes(db, USER, GEAR, NOW)
            await db.commit()
            affixes = await affix_manager.get_affixes(db, USER, GEAR)
        self.assertEqual(affixes, [])

    async def test_clear_all_no_cost(self):
        async with schema.get_connection() as db:
            await _insert_player(db, USER, gear_level=10, materials=2)
            await affix_manager.extract_affix(db, USER, GEAR, 10, NOW)
            await db.commit()
            await affix_manager.clear_all_affixes(db, USER, GEAR, NOW)
            await db.commit()
            mats = await player_manager.get_material(db, USER, GEAR)
        self.assertEqual(mats, 2 - int(os.environ["AFFIX_EXTRACT_COST"]))

    async def test_clear_all_only_affects_given_gear_type(self):
        async with schema.get_connection() as db:
            await _insert_player(db, USER, gear_level=10, materials=10)
            await _insert_player(db, USER, gear_type="combat", gear_level=10, materials=10)
            await affix_manager.extract_affix(db, USER, GEAR, 10, NOW)
            await affix_manager.extract_affix(db, USER, "combat", 10, NOW)
            await db.commit()
            await affix_manager.clear_all_affixes(db, USER, GEAR, NOW)
            await db.commit()
            combat_affixes = await affix_manager.get_affixes(db, USER, "combat")
        self.assertEqual(len(combat_affixes), 1)


class TestGetAffixBonuses(DatabaseTestCase):
    async def test_bonuses_zero_when_no_affixes(self):
        async with schema.get_connection() as db:
            await _insert_player(db, USER, gear_level=10, materials=0)
            bonuses = await affix_manager.get_affix_bonuses(db, USER, GEAR)
        for t in affix_manager.AFFIX_TYPES:
            self.assertEqual(bonuses[t], 0)

    async def test_bonuses_accumulate_same_type(self):
        async with schema.get_connection() as db:
            await _insert_player(db, USER, gear_level=10, materials=10)
            with patch("random.choice", return_value="efficiency"), \
                 patch("random.randint", return_value=2):
                await affix_manager.extract_affix(db, USER, GEAR, 10, NOW)
            with patch("random.choice", return_value="efficiency"), \
                 patch("random.randint", return_value=3):
                await affix_manager.extract_affix(db, USER, GEAR, 10, NOW)
            await db.commit()
            bonuses = await affix_manager.get_affix_bonuses(db, USER, GEAR)
        self.assertEqual(bonuses["efficiency"], 5)

    async def test_bonuses_per_gear_type_isolated(self):
        async with schema.get_connection() as db:
            await _insert_player(db, USER, gear_level=10, materials=10)
            with patch("random.choice", return_value="efficiency"), \
                 patch("random.randint", return_value=4):
                await affix_manager.extract_affix(db, USER, GEAR, 10, NOW)
            await db.commit()
            combat_bonuses = await affix_manager.get_affix_bonuses(db, USER, "combat")
        self.assertEqual(combat_bonuses["efficiency"], 0)

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

"""
Tests for src/core/formula.py — output calculation and action configs.
"""

import math
import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from support import ALL_TEST_ENV, DatabaseTestCase
from core.formula import (
    ACTION_FACILITY_BUILDING,
    ACTION_GEAR_COL,
    ACTION_MATERIAL_COL,
    VALID_ACTIONS,
    action_costs,
    compute_output,
)


class ActionCostsTest(unittest.TestCase):
    def setUp(self):
        for k, v in ALL_TEST_ENV.items():
            os.environ[k] = v

    def tearDown(self):
        for k in ALL_TEST_ENV:
            os.environ.pop(k, None)

    def test_gathering_costs_only_food(self):
        costs = action_costs("gathering")
        self.assertIn("food", costs)
        self.assertNotIn("wood", costs)
        self.assertNotIn("knowledge", costs)

    def test_building_costs_food_and_wood(self):
        costs = action_costs("building")
        self.assertIn("food", costs)
        self.assertIn("wood", costs)
        self.assertNotIn("knowledge", costs)

    def test_combat_costs_food_and_wood(self):
        costs = action_costs("combat")
        self.assertIn("food", costs)
        self.assertIn("wood", costs)
        self.assertNotIn("knowledge", costs)

    def test_research_costs_food_and_knowledge(self):
        costs = action_costs("research")
        self.assertIn("food", costs)
        self.assertIn("knowledge", costs)
        self.assertNotIn("wood", costs)

    def test_food_cost_matches_env(self):
        costs = action_costs("gathering")
        self.assertEqual(costs["food"], int(ALL_TEST_ENV["FOOD_COST"]))


class ComputeOutputTest(DatabaseTestCase):
    TEST_USER = "output_test_user"

    async def _insert_player(self, **overrides):
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        ap_full = now
        fields = {
            "user_id": self.TEST_USER,
            "created_at": now,
            "updated_at": now,
            "action": None,
            "action_target": None,
            "completion_time": None,
            "last_update_time": None,
            "ap_full_time": ap_full,
            "gear_gathering": 0,
            "gear_building": 0,
            "gear_combat": 0,
            "gear_research": 0,
        }
        fields.update(overrides)
        from database import schema
        async with schema.get_connection() as db:
            await db.execute(
                """INSERT OR REPLACE INTO players
                   (user_id, created_at, updated_at, action, action_target,
                    completion_time, last_update_time, ap_full_time,
                    gear_gathering, gear_building, gear_combat, gear_research,
                    materials_gathering, materials_building, materials_combat, materials_research,
                    pity_gathering, pity_building, pity_combat, pity_research)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,0,0,0,0,0,0,0,0)""",
                (
                    fields["user_id"], fields["created_at"], fields["updated_at"],
                    fields["action"], fields["action_target"], fields["completion_time"],
                    fields["last_update_time"], fields["ap_full_time"],
                    fields["gear_gathering"], fields["gear_building"],
                    fields["gear_combat"], fields["gear_research"],
                ),
            )
            await db.commit()

    async def test_base_output_no_bonuses(self):
        """With no stages cleared, no gear, no building levels: output == BASE_OUTPUT."""
        await self._insert_player()
        from database import schema
        async with schema.get_connection() as db:
            result = await compute_output(db, self.TEST_USER, "gathering")
        self.assertEqual(result, int(ALL_TEST_ENV["BASE_OUTPUT"]))

    async def test_gear_bonus_increases_output(self):
        """gear_gathering=1 increases gathering output by GEAR_BONUS_PER_LEVEL × BASE_OUTPUT."""
        await self._insert_player(gear_gathering=1)
        from database import schema
        base = int(ALL_TEST_ENV["BASE_OUTPUT"])
        gear_bonus = float(ALL_TEST_ENV["GEAR_BONUS_PER_LEVEL"])
        expected = math.floor(base * (1 + gear_bonus))
        async with schema.get_connection() as db:
            result = await compute_output(db, self.TEST_USER, "gathering")
        self.assertEqual(result, expected)

    async def test_gear_bonus_is_action_specific(self):
        """gear_gathering does not affect combat output."""
        await self._insert_player(gear_gathering=5)
        from database import schema
        base = int(ALL_TEST_ENV["BASE_OUTPUT"])
        async with schema.get_connection() as db:
            result = await compute_output(db, self.TEST_USER, "combat")
        self.assertEqual(result, base)

    async def test_facility_bonus_increases_output(self):
        """Upgrading the gathering_field increases gathering output."""
        await self._insert_player()
        from database import schema
        async with schema.get_connection() as db:
            await db.execute(
                "UPDATE buildings SET level=2 WHERE building_type='gathering_field'"
            )
            await db.commit()
        base = int(ALL_TEST_ENV["BASE_OUTPUT"])
        fac_bonus = float(ALL_TEST_ENV["FACILITY_BONUS_PER_LEVEL"])
        expected = math.floor(base * (1 + 2 * fac_bonus))
        async with schema.get_connection() as db:
            result = await compute_output(db, self.TEST_USER, "gathering")
        self.assertEqual(result, expected)

    async def test_stage_bonus_increases_output(self):
        """stages_cleared=5 increases output by 5 × STAGE_BONUS_PER_CLEAR × BASE_OUTPUT."""
        await self._insert_player()
        from database import schema
        async with schema.get_connection() as db:
            await db.execute("UPDATE stage_state SET stages_cleared=5 WHERE id=1")
            await db.commit()
        base = int(ALL_TEST_ENV["BASE_OUTPUT"])
        stage_bonus = float(ALL_TEST_ENV["STAGE_BONUS_PER_CLEAR"])
        expected = math.floor(base * (1 + 5 * stage_bonus))
        async with schema.get_connection() as db:
            result = await compute_output(db, self.TEST_USER, "gathering")
        self.assertEqual(result, expected)

    async def test_output_is_floored(self):
        """Output is floor(BASE_OUTPUT × (1 + bonuses)) — not rounded."""
        await self._insert_player(gear_gathering=1)
        os.environ["BASE_OUTPUT"] = "7"
        os.environ["GEAR_BONUS_PER_LEVEL"] = "0.1"
        expected = math.floor(7 * 1.1)  # = 7, not 8
        from database import schema
        async with schema.get_connection() as db:
            result = await compute_output(db, self.TEST_USER, "gathering")
        self.assertEqual(result, expected)


class ActionConfigMapsTest(unittest.TestCase):
    def test_all_valid_actions_have_gear_col(self):
        for action in VALID_ACTIONS:
            self.assertIn(action, ACTION_GEAR_COL)

    def test_all_valid_actions_have_material_col(self):
        for action in VALID_ACTIONS:
            self.assertIn(action, ACTION_MATERIAL_COL)

    def test_all_valid_actions_have_facility(self):
        for action in VALID_ACTIONS:
            self.assertIn(action, ACTION_FACILITY_BUILDING)

    def test_research_facility_is_research_lab(self):
        self.assertEqual(ACTION_FACILITY_BUILDING["research"], "research_lab")


if __name__ == "__main__":
    unittest.main()

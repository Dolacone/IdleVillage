"""
Tests for src/core/settlement.py — complete cycle, partial cycle, and burst.
"""

import math
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from support import ALL_TEST_ENV, DatabaseTestCase
from database import schema
from core.settlement import (
    change_action,
    settle_burst,
    settle_complete_cycles,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


class SettlementTestBase(DatabaseTestCase):
    """Helper base: insert a test player with a given action and timestamps."""

    TEST_USER = "test_player"

    async def _insert_player(
        self,
        action=None,
        action_target=None,
        completion_time=None,
        last_update_time=None,
        ap_full_time=None,
        gear_gathering=0,
        gear_building=0,
        gear_combat=0,
        gear_research=0,
    ):
        now_str = _now().isoformat()
        if ap_full_time is None:
            ap_full_time = _now().isoformat()
        if isinstance(ap_full_time, datetime):
            ap_full_time = ap_full_time.isoformat()
        if isinstance(completion_time, datetime):
            completion_time = completion_time.isoformat()
        if isinstance(last_update_time, datetime):
            last_update_time = last_update_time.isoformat()

        async with schema.get_connection() as db:
            await db.execute(
                """INSERT OR REPLACE INTO players
                   (user_id, created_at, updated_at, action, action_target,
                    completion_time, last_update_time, ap_full_time,
                    materials_gathering, materials_building, materials_combat, materials_research,
                    gear_gathering, gear_building, gear_combat, gear_research,
                    pity_gathering, pity_building, pity_combat, pity_research)
                   VALUES (?,?,?,?,?,?,?,?,0,0,0,0,?,?,?,?,0,0,0,0)""",
                (
                    self.TEST_USER, now_str, now_str,
                    action, action_target, completion_time, last_update_time,
                    ap_full_time,
                    gear_gathering, gear_building, gear_combat, gear_research,
                ),
            )
            await db.commit()

    async def _set_resource(self, resource_type: str, amount: int):
        async with schema.get_connection() as db:
            await db.execute(
                "UPDATE village_resources SET amount=? WHERE resource_type=?",
                (amount, resource_type),
            )
            await db.commit()

    async def _get_resource(self, resource_type: str) -> int:
        row = await self.fetchone(
            "SELECT amount FROM village_resources WHERE resource_type=?", (resource_type,)
        )
        return row[0] if row else 0

    async def _get_player(self) -> dict:
        async with schema.get_connection() as db:
            async with db.execute(
                "SELECT * FROM players WHERE user_id=?", (self.TEST_USER,)
            ) as cur:
                row = await cur.fetchone()
                cols = [d[0] for d in cur.description]
                return dict(zip(cols, row))

    async def _get_building(self, building_type: str) -> dict:
        row = await self.fetchone(
            "SELECT level, xp_progress FROM buildings WHERE building_type=?",
            (building_type,),
        )
        return {"level": row[0], "xp_progress": row[1]}

    async def _get_stage_state(self) -> dict:
        async with schema.get_connection() as db:
            async with db.execute("SELECT * FROM stage_state WHERE id=1") as cur:
                row = await cur.fetchone()
                cols = [d[0] for d in cur.description]
                return dict(zip(cols, row))


# ---------------------------------------------------------------------------
# Complete cycle tests
# ---------------------------------------------------------------------------

class CompleteCycleTest(SettlementTestBase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        # Give village enough resources for all tests
        await self._set_resource("food", 10000)
        await self._set_resource("wood", 10000)
        await self._set_resource("knowledge", 10000)

    async def test_gathering_adds_food_and_wood(self):
        """Gathering distributes settlement_output to both food and wood."""
        cycle_end = _now() - timedelta(minutes=1)
        await self._insert_player(
            action="gathering",
            completion_time=cycle_end,
            last_update_time=cycle_end - timedelta(minutes=10),
        )
        food_before = await self._get_resource("food")
        wood_before = await self._get_resource("wood")

        await settle_complete_cycles(self.TEST_USER, _now())

        food_after = await self._get_resource("food")
        wood_after = await self._get_resource("wood")
        base = int(ALL_TEST_ENV["BASE_OUTPUT"])
        # Food cost deducted then settlement_output added; net = settlement_output - food_cost
        self.assertGreater(food_after, food_before - int(ALL_TEST_ENV["FOOD_COST"]))
        self.assertGreater(wood_after, wood_before)

    async def test_combat_adds_knowledge(self):
        """Combat distributes settlement_output to knowledge."""
        cycle_end = _now() - timedelta(minutes=1)
        await self._insert_player(
            action="combat",
            completion_time=cycle_end,
            last_update_time=cycle_end - timedelta(minutes=10),
        )
        knowledge_before = await self._get_resource("knowledge")
        await settle_complete_cycles(self.TEST_USER, _now())
        knowledge_after = await self._get_resource("knowledge")
        # After deducting food + wood costs and adding output: net change depends on costs
        base = int(ALL_TEST_ENV["BASE_OUTPUT"])
        expected_net = base - int(ALL_TEST_ENV["FOOD_COST"]) - int(ALL_TEST_ENV["WOOD_COST"]) + base
        # At minimum, knowledge increased by settlement_output
        self.assertGreater(knowledge_after, knowledge_before)

    async def test_building_adds_xp_to_target(self):
        """Building distributes settlement_output as XP to the specified building."""
        cycle_end = _now() - timedelta(minutes=1)
        await self._insert_player(
            action="building",
            action_target="gathering_field",
            completion_time=cycle_end,
            last_update_time=cycle_end - timedelta(minutes=10),
        )
        bld_before = await self._get_building("gathering_field")
        await settle_complete_cycles(self.TEST_USER, _now())
        bld_after = await self._get_building("gathering_field")
        self.assertGreater(bld_after["xp_progress"], bld_before["xp_progress"])

    async def test_research_adds_xp_to_research_lab(self):
        """Research always goes to research_lab, no action_target needed."""
        cycle_end = _now() - timedelta(minutes=1)
        await self._insert_player(
            action="research",
            completion_time=cycle_end,
            last_update_time=cycle_end - timedelta(minutes=10),
        )
        bld_before = await self._get_building("research_lab")
        await settle_complete_cycles(self.TEST_USER, _now())
        bld_after = await self._get_building("research_lab")
        self.assertGreater(bld_after["xp_progress"], bld_before["xp_progress"])

    async def test_last_update_time_set_to_cycle_end(self):
        """After settlement, last_update_time equals cycle_end_time."""
        cycle_end = _now() - timedelta(minutes=1)
        await self._insert_player(
            action="gathering",
            completion_time=cycle_end,
            last_update_time=cycle_end - timedelta(minutes=10),
        )
        await settle_complete_cycles(self.TEST_USER, _now())
        player = await self._get_player()
        lut = _utc(datetime.fromisoformat(player["last_update_time"]))
        self.assertAlmostEqual(lut.timestamp(), cycle_end.timestamp(), delta=1)

    async def test_completion_time_advances_by_one_cycle(self):
        """After one settled cycle, completion_time = old + ACTION_CYCLE_MINUTES."""
        cycle_mins = int(ALL_TEST_ENV["ACTION_CYCLE_MINUTES"])
        cycle_end = _now() - timedelta(minutes=1)
        await self._insert_player(
            action="gathering",
            completion_time=cycle_end,
            last_update_time=cycle_end - timedelta(minutes=cycle_mins),
        )
        await settle_complete_cycles(self.TEST_USER, _now())
        player = await self._get_player()
        new_ct = _utc(datetime.fromisoformat(player["completion_time"]))
        expected = cycle_end + timedelta(minutes=cycle_mins)
        self.assertAlmostEqual(new_ct.timestamp(), expected.timestamp(), delta=1)

    async def test_no_action_player_is_skipped(self):
        """Player with no action is silently skipped."""
        await self._insert_player(action=None)
        food_before = await self._get_resource("food")
        await settle_complete_cycles(self.TEST_USER, _now())
        food_after = await self._get_resource("food")
        self.assertEqual(food_before, food_after)

    async def test_future_completion_time_not_settled(self):
        """Player whose completion_time is in the future is not settled."""
        future = _now() + timedelta(minutes=5)
        await self._insert_player(
            action="gathering",
            completion_time=future,
            last_update_time=_now() - timedelta(minutes=5),
        )
        food_before = await self._get_resource("food")
        await settle_complete_cycles(self.TEST_USER, _now())
        food_after = await self._get_resource("food")
        self.assertEqual(food_before, food_after)


class ShortagePenaltyTest(SettlementTestBase):
    async def test_shortage_halves_settlement_output(self):
        """When food is below cost, settlement_output = floor(output × 0.5)."""
        await self._set_resource("food", 0)  # shortage
        await self._set_resource("wood", 10000)
        await self._set_resource("knowledge", 10000)

        cycle_end = _now() - timedelta(minutes=1)
        await self._insert_player(
            action="gathering",
            completion_time=cycle_end,
            last_update_time=cycle_end - timedelta(minutes=10),
        )
        wood_before = await self._get_resource("wood")
        await settle_complete_cycles(self.TEST_USER, _now())
        wood_after = await self._get_resource("wood")
        base = int(ALL_TEST_ENV["BASE_OUTPUT"])
        penalized = math.floor(base * 0.5)
        self.assertEqual(wood_after - wood_before, penalized)

    async def test_shortage_does_not_affect_stage_progress(self):
        """Stage progress uses pre-penalty output regardless of shortage."""
        await self._set_resource("food", 0)
        await self._set_resource("wood", 10000)
        await self._set_resource("knowledge", 10000)

        cycle_end = _now() - timedelta(minutes=1)
        await self._insert_player(
            action="gathering",
            completion_time=cycle_end,
            last_update_time=cycle_end - timedelta(minutes=10),
        )
        stage_before = await self._get_stage_state()
        await settle_complete_cycles(self.TEST_USER, _now())
        stage_after = await self._get_stage_state()

        base = int(ALL_TEST_ENV["BASE_OUTPUT"])
        progress_added = stage_after["current_stage_progress"] - stage_before["current_stage_progress"]
        self.assertEqual(progress_added, base)

    async def test_shortage_single_flag_regardless_of_multiple_missing(self):
        """Multiple resources missing still applies only one ×0.5 penalty."""
        await self._set_resource("food", 0)
        await self._set_resource("wood", 0)
        await self._set_resource("knowledge", 10000)

        cycle_end = _now() - timedelta(minutes=1)
        await self._insert_player(
            action="combat",
            completion_time=cycle_end,
            last_update_time=cycle_end - timedelta(minutes=10),
        )
        knowledge_before = await self._get_resource("knowledge")
        await settle_complete_cycles(self.TEST_USER, _now())
        knowledge_after = await self._get_resource("knowledge")

        base = int(ALL_TEST_ENV["BASE_OUTPUT"])
        penalized = math.floor(base * 0.5)
        self.assertEqual(knowledge_after - knowledge_before, penalized)


class CatchUpTest(SettlementTestBase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        await self._set_resource("food", 10000)
        await self._set_resource("wood", 10000)
        await self._set_resource("knowledge", 10000)

    async def test_multiple_overdue_cycles_are_settled(self):
        """Three overdue cycles produce three times the per-cycle output."""
        cycle_mins = int(ALL_TEST_ENV["ACTION_CYCLE_MINUTES"])
        start = _now() - timedelta(minutes=cycle_mins * 3 + 1)
        await self._insert_player(
            action="gathering",
            completion_time=start + timedelta(minutes=cycle_mins),
            last_update_time=start,
        )
        wood_before = await self._get_resource("wood")
        await settle_complete_cycles(self.TEST_USER, _now())
        wood_after = await self._get_resource("wood")
        base = int(ALL_TEST_ENV["BASE_OUTPUT"])
        food_cost = int(ALL_TEST_ENV["FOOD_COST"])
        # Each cycle: +base wood, -food_cost food
        self.assertEqual(wood_after - wood_before, base * 3)

    async def test_max_cycles_per_settlement_limit(self):
        """Catch-up stops at MAX_CYCLES_PER_SETTLEMENT even if more are overdue."""
        max_cycles = int(ALL_TEST_ENV["MAX_CYCLES_PER_SETTLEMENT"])
        cycle_mins = int(ALL_TEST_ENV["ACTION_CYCLE_MINUTES"])
        # Overdue by 2 × max_cycles periods
        start = _now() - timedelta(minutes=cycle_mins * (max_cycles * 2 + 1))
        await self._insert_player(
            action="gathering",
            completion_time=start + timedelta(minutes=cycle_mins),
            last_update_time=start,
        )
        wood_before = await self._get_resource("wood")
        await settle_complete_cycles(self.TEST_USER, _now())
        wood_after = await self._get_resource("wood")
        base = int(ALL_TEST_ENV["BASE_OUTPUT"])
        # Should have settled exactly max_cycles cycles
        self.assertEqual(wood_after - wood_before, base * max_cycles)


# ---------------------------------------------------------------------------
# Stage progress tests
# ---------------------------------------------------------------------------

class StageProgressTest(SettlementTestBase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        await self._set_resource("food", 10000)
        await self._set_resource("wood", 10000)
        await self._set_resource("knowledge", 10000)

    async def test_matching_action_adds_progress(self):
        """gathering action adds progress on gathering stage."""
        stage_before = await self._get_stage_state()
        self.assertEqual(stage_before["current_stage_type"], "gathering")

        cycle_end = _now() - timedelta(minutes=1)
        await self._insert_player(
            action="gathering",
            completion_time=cycle_end,
            last_update_time=cycle_end - timedelta(minutes=10),
        )
        await settle_complete_cycles(self.TEST_USER, _now())
        stage_after = await self._get_stage_state()
        self.assertGreater(
            stage_after["current_stage_progress"], stage_before["current_stage_progress"]
        )

    async def test_non_matching_action_no_progress(self):
        """combat action does NOT add progress on gathering stage."""
        stage_before = await self._get_stage_state()
        self.assertEqual(stage_before["current_stage_type"], "gathering")

        cycle_end = _now() - timedelta(minutes=1)
        await self._insert_player(
            action="combat",
            completion_time=cycle_end,
            last_update_time=cycle_end - timedelta(minutes=10),
        )
        await settle_complete_cycles(self.TEST_USER, _now())
        stage_after = await self._get_stage_state()
        self.assertEqual(
            stage_after["current_stage_progress"], stage_before["current_stage_progress"]
        )

    async def test_upgrade_stage_accepts_all_actions(self):
        """Upgrade stage (index 4) accepts any action type."""
        async with schema.get_connection() as db:
            from datetime import timezone
            now_str = datetime.now(timezone.utc).isoformat()
            await db.execute(
                """UPDATE stage_state SET
                   current_stage_index=4, current_stage_type='upgrade',
                   current_stage_progress=0, current_stage_target=99999,
                   updated_at=?
                   WHERE id=1""",
                (now_str,),
            )
            await db.commit()

        cycle_end = _now() - timedelta(minutes=1)
        await self._insert_player(
            action="combat",
            completion_time=cycle_end,
            last_update_time=cycle_end - timedelta(minutes=10),
        )
        stage_before = await self._get_stage_state()
        await settle_complete_cycles(self.TEST_USER, _now())
        stage_after = await self._get_stage_state()
        self.assertGreater(
            stage_after["current_stage_progress"], stage_before["current_stage_progress"]
        )

    async def test_stage_clear_increments_stages_cleared(self):
        """When progress reaches target, stages_cleared increments."""
        base = int(ALL_TEST_ENV["BASE_OUTPUT"])
        # Set target just below one output so the next cycle clears it
        async with schema.get_connection() as db:
            from datetime import timezone
            now_str = datetime.now(timezone.utc).isoformat()
            await db.execute(
                "UPDATE stage_state SET current_stage_target=?, current_stage_progress=0, updated_at=? WHERE id=1",
                (base, now_str),
            )
            await db.commit()

        cycle_end = _now() - timedelta(minutes=1)
        await self._insert_player(
            action="gathering",
            completion_time=cycle_end,
            last_update_time=cycle_end - timedelta(minutes=10),
        )
        stage_before = await self._get_stage_state()
        await settle_complete_cycles(self.TEST_USER, _now())
        stage_after = await self._get_stage_state()
        self.assertEqual(stage_after["stages_cleared"], stage_before["stages_cleared"] + 1)
        self.assertEqual(stage_after["current_stage_progress"], 0)

    async def test_upgrade_stage_clear_triggers_building_upgrades(self):
        """Clearing upgrade stage (index 4) runs checkAllUpgrades."""
        # Set up: stage at index 4 (upgrade), target=BASE_OUTPUT so one cycle clears it
        base = int(ALL_TEST_ENV["BASE_OUTPUT"])
        async with schema.get_connection() as db:
            from datetime import timezone
            now_str = datetime.now(timezone.utc).isoformat()
            await db.execute(
                """UPDATE stage_state SET
                   stages_cleared=4, current_stage_index=4, current_stage_type='upgrade',
                   current_stage_progress=0, current_stage_target=?,
                   updated_at=? WHERE id=1""",
                (base, now_str),
            )
            # Give building XP = 1×BUILDING_XP_PER_LEVEL (already at cap lv1 before this)
            # After upgrade stage clear, new stages_cleared=5, level_cap=2 → can upgrade
            xp_per = int(ALL_TEST_ENV["BUILDING_XP_PER_LEVEL"])
            await db.execute(
                "UPDATE buildings SET level=1, xp_progress=? WHERE building_type='gathering_field'",
                (xp_per,),  # has xp_progress=xp_per, which is enough to reach Lv2 (needs 2×xp_per; has 1×, so not enough)
            )
            await db.commit()

        cycle_end = _now() - timedelta(minutes=1)
        await self._insert_player(
            action="gathering",
            completion_time=cycle_end,
            last_update_time=cycle_end - timedelta(minutes=10),
        )
        await settle_complete_cycles(self.TEST_USER, _now())
        stage_after = await self._get_stage_state()
        self.assertEqual(stage_after["stages_cleared"], 5)
        # Building should NOT have upgraded (1×xp_per < 2×xp_per needed for Lv2)
        bld = await self._get_building("gathering_field")
        self.assertEqual(bld["level"], 1)


# ---------------------------------------------------------------------------
# Building upgrade tests
# ---------------------------------------------------------------------------

class BuildingUpgradeTest(SettlementTestBase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        await self._set_resource("food", 10000)
        await self._set_resource("wood", 10000)
        await self._set_resource("knowledge", 10000)

    async def test_building_xp_triggers_upgrade(self):
        """When XP reaches threshold, building upgrades from Lv0 to Lv1."""
        xp_per = int(ALL_TEST_ENV["BUILDING_XP_PER_LEVEL"])
        # Set building XP just below threshold so next cycle pushes it over
        async with schema.get_connection() as db:
            from datetime import timezone
            now_str = datetime.now(timezone.utc).isoformat()
            # Set stages_cleared to 0 → level_cap = 1; Lv0→Lv1 needs xp_per
            base_output = int(ALL_TEST_ENV["BASE_OUTPUT"])
            # xp_progress = xp_per - base_output + 1 so that adding base_output crosses threshold
            pre_xp = xp_per - base_output + 1
            await db.execute(
                "UPDATE buildings SET level=0, xp_progress=? WHERE building_type='gathering_field'",
                (max(0, pre_xp),),
            )
            await db.commit()

        cycle_end = _now() - timedelta(minutes=1)
        await self._insert_player(
            action="building",
            action_target="gathering_field",
            completion_time=cycle_end,
            last_update_time=cycle_end - timedelta(minutes=10),
        )
        bld_before = await self._get_building("gathering_field")
        await settle_complete_cycles(self.TEST_USER, _now())
        bld_after = await self._get_building("gathering_field")
        self.assertEqual(bld_after["level"], 1)

    async def test_building_capped_at_level_cap(self):
        """Building does not upgrade beyond level_cap."""
        xp_per = int(ALL_TEST_ENV["BUILDING_XP_PER_LEVEL"])
        base_output = int(ALL_TEST_ENV["BASE_OUTPUT"])
        # stages_cleared=0 → level_cap=1; building already at Lv1
        async with schema.get_connection() as db:
            from datetime import timezone
            now_str = datetime.now(timezone.utc).isoformat()
            await db.execute(
                "UPDATE buildings SET level=1, xp_progress=0 WHERE building_type='gathering_field'",
            )
            await db.commit()

        cycle_end = _now() - timedelta(minutes=1)
        await self._insert_player(
            action="building",
            action_target="gathering_field",
            completion_time=cycle_end,
            last_update_time=cycle_end - timedelta(minutes=10),
        )
        await settle_complete_cycles(self.TEST_USER, _now())
        bld_after = await self._get_building("gathering_field")
        # Level should remain 1 (cap), xp_progress capped at 1×xp_per
        self.assertEqual(bld_after["level"], 1)
        self.assertLessEqual(bld_after["xp_progress"], xp_per)


# ---------------------------------------------------------------------------
# Partial cycle (action change) tests
# ---------------------------------------------------------------------------

class PartialCycleTest(SettlementTestBase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        await self._set_resource("food", 10000)
        await self._set_resource("wood", 10000)
        await self._set_resource("knowledge", 10000)

    async def test_partial_cycle_proportional_output(self):
        """At 50% elapsed, output is approximately floor(BASE_OUTPUT × 0.5)."""
        cycle_mins = int(ALL_TEST_ENV["ACTION_CYCLE_MINUTES"])
        last_update = _now() - timedelta(minutes=cycle_mins / 2)
        completion = _now() + timedelta(minutes=cycle_mins / 2)
        await self._insert_player(
            action="gathering",
            completion_time=completion,
            last_update_time=last_update,
        )
        wood_before = await self._get_resource("wood")
        await change_action(self.TEST_USER, "combat", None, _now())
        wood_after = await self._get_resource("wood")
        base = int(ALL_TEST_ENV["BASE_OUTPUT"])
        expected = math.floor(base * 0.5)
        self.assertEqual(wood_after - wood_before, expected)

    async def test_first_time_action_no_partial(self):
        """When last_update_time is null (first action), no partial settlement occurs."""
        await self._insert_player(action=None, completion_time=None, last_update_time=None)
        wood_before = await self._get_resource("wood")
        await change_action(self.TEST_USER, "gathering", None, _now())
        wood_after = await self._get_resource("wood")
        self.assertEqual(wood_before, wood_after)

    async def test_first_time_sets_last_update_time(self):
        """First action setup writes last_update_time = now."""
        await self._insert_player(action=None, completion_time=None, last_update_time=None)
        now = _now()
        await change_action(self.TEST_USER, "gathering", None, now)
        player = await self._get_player()
        self.assertIsNotNone(player["last_update_time"])
        lut = _utc(datetime.fromisoformat(player["last_update_time"]))
        self.assertAlmostEqual(lut.timestamp(), now.timestamp(), delta=2)

    async def test_partial_cycle_no_material_drop(self):
        """Partial cycle never drops materials, even with 100% drop rate."""
        os.environ["MATERIAL_DROP_RATE"] = "1.0"
        cycle_mins = int(ALL_TEST_ENV["ACTION_CYCLE_MINUTES"])
        last_update = _now() - timedelta(minutes=cycle_mins / 2)
        completion = _now() + timedelta(minutes=cycle_mins / 2)
        await self._insert_player(
            action="gathering",
            completion_time=completion,
            last_update_time=last_update,
        )
        await change_action(self.TEST_USER, "combat", None, _now())
        player = await self._get_player()
        self.assertEqual(player["materials_gathering"], 0)

    async def test_action_change_settles_overdue_cycles_first(self):
        """If completion_time < now, full cycles are caught up before partial."""
        cycle_mins = int(ALL_TEST_ENV["ACTION_CYCLE_MINUTES"])
        overdue_start = _now() - timedelta(minutes=cycle_mins * 2 + cycle_mins / 2)
        await self._insert_player(
            action="gathering",
            completion_time=overdue_start + timedelta(minutes=cycle_mins),
            last_update_time=overdue_start,
        )
        wood_before = await self._get_resource("wood")
        await change_action(self.TEST_USER, "combat", None, _now())
        wood_after = await self._get_resource("wood")
        base = int(ALL_TEST_ENV["BASE_OUTPUT"])
        # 2 full cycles + ~50% partial = 2×base + floor(base×0.5)
        expected_min = base * 2
        self.assertGreaterEqual(wood_after - wood_before, expected_min)

    async def test_new_action_written_after_change(self):
        """change_action writes the new action to the player row."""
        await self._insert_player(action="gathering", completion_time=_now() + timedelta(minutes=5),
                                   last_update_time=_now() - timedelta(minutes=5))
        await change_action(self.TEST_USER, "combat", None, _now())
        player = await self._get_player()
        self.assertEqual(player["action"], "combat")

    async def test_building_target_stored_only_for_building(self):
        """action_target is stored for building, cleared for other actions."""
        await self._insert_player(action="gathering", completion_time=_now() + timedelta(minutes=5),
                                   last_update_time=_now() - timedelta(minutes=5))
        await change_action(self.TEST_USER, "building", "workshop", _now())
        player = await self._get_player()
        self.assertEqual(player["action_target"], "workshop")

        await change_action(self.TEST_USER, "gathering", None, _now())
        player = await self._get_player()
        self.assertIsNone(player["action_target"])


# ---------------------------------------------------------------------------
# Burst tests
# ---------------------------------------------------------------------------

class BurstTest(SettlementTestBase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        await self._set_resource("food", 10000)
        await self._set_resource("wood", 10000)
        await self._set_resource("knowledge", 10000)

    async def _insert_player_with_ap(self, ap: int):
        """Insert player with specific AP count (by setting ap_full_time)."""
        ap_cap = int(ALL_TEST_ENV["AP_CAP"])
        recovery_mins = int(ALL_TEST_ENV["AP_RECOVERY_MINUTES"])
        now = _now()
        if ap >= ap_cap:
            ap_full_time = now - timedelta(minutes=1)
        else:
            ap_full_time = now + timedelta(minutes=(ap_cap - ap) * recovery_mins)
        await self._insert_player(
            action="gathering",
            completion_time=now + timedelta(minutes=10),
            last_update_time=now - timedelta(minutes=5),
            ap_full_time=ap_full_time,
        )

    async def test_burst_with_no_ap_returns_false(self):
        """Burst returns False when player has 0 AP."""
        await self._insert_player_with_ap(0)
        result = await settle_burst(self.TEST_USER, _now())
        self.assertFalse(result)

    async def test_burst_with_sufficient_ap_returns_true(self):
        """Burst returns True when player has >= 1 AP."""
        await self._insert_player_with_ap(1)
        result = await settle_burst(self.TEST_USER, _now())
        self.assertTrue(result)

    async def test_burst_runs_exactly_3_cycles(self):
        """Burst distributes 3 × settlement_output."""
        await self._insert_player_with_ap(5)
        wood_before = await self._get_resource("wood")
        await settle_burst(self.TEST_USER, _now())
        wood_after = await self._get_resource("wood")
        base = int(ALL_TEST_ENV["BASE_OUTPUT"])
        self.assertEqual(wood_after - wood_before, base * 3)

    async def test_burst_does_not_update_completion_time(self):
        """Burst does not change completion_time or last_update_time."""
        now = _now()
        completion = now + timedelta(minutes=10)
        last_update = now - timedelta(minutes=5)
        await self._insert_player(
            action="gathering",
            completion_time=completion,
            last_update_time=last_update,
            ap_full_time=now - timedelta(minutes=1),  # full AP
        )
        await settle_burst(self.TEST_USER, now)
        player = await self._get_player()
        ct = _utc(datetime.fromisoformat(player["completion_time"]))
        lut = _utc(datetime.fromisoformat(player["last_update_time"]))
        self.assertAlmostEqual(ct.timestamp(), completion.timestamp(), delta=1)
        self.assertAlmostEqual(lut.timestamp(), last_update.timestamp(), delta=1)

    async def test_burst_spends_1_ap(self):
        """Burst spends exactly 1 AP."""
        ap_cap = int(ALL_TEST_ENV["AP_CAP"])
        recovery_mins = int(ALL_TEST_ENV["AP_RECOVERY_MINUTES"])
        now = _now()
        # Start with full AP
        ap_full_time = now - timedelta(minutes=1)
        await self._insert_player(
            action="gathering",
            completion_time=now + timedelta(minutes=10),
            last_update_time=now - timedelta(minutes=5),
            ap_full_time=ap_full_time,
        )
        await settle_burst(self.TEST_USER, now)
        player = await self._get_player()
        new_ap_full = _utc(datetime.fromisoformat(player["ap_full_time"]))
        # After spending 1 AP at full capacity: ap_full_time = max(now, old_ap_full) + 1×recovery
        expected = max(now, ap_full_time) + timedelta(minutes=recovery_mins)
        self.assertAlmostEqual(new_ap_full.timestamp(), expected.timestamp(), delta=2)

    async def test_burst_rolls_material_three_times(self):
        """Burst runs 3 material rolls (each at 100% drop rate gives 3 materials)."""
        os.environ["MATERIAL_DROP_RATE"] = "1.0"
        await self._insert_player_with_ap(5)
        await settle_burst(self.TEST_USER, _now())
        player = await self._get_player()
        self.assertEqual(player["materials_gathering"], 3)

    async def test_burst_with_no_action_returns_false(self):
        """Burst returns False when player has no active action."""
        now = _now()
        await self._insert_player(
            action=None,
            ap_full_time=now - timedelta(minutes=1),
        )
        result = await settle_burst(self.TEST_USER, now)
        self.assertFalse(result)


# ---------------------------------------------------------------------------
# AP helpers
# ---------------------------------------------------------------------------

class APTest(SettlementTestBase):
    async def test_full_ap_when_past_ap_full_time(self):
        """Player returns AP_CAP when ap_full_time is in the past."""
        from core.settlement import _get_ap, _read_player
        now = _now()
        ap_full_time = now - timedelta(minutes=1)
        await self._insert_player(ap_full_time=ap_full_time)
        async with schema.get_connection() as db:
            ap = await _get_ap(db, self.TEST_USER, now)
        self.assertEqual(ap, int(ALL_TEST_ENV["AP_CAP"]))

    async def test_zero_ap_when_just_spent(self):
        """Player returns 0 AP when ap_full_time is AP_CAP × recovery from now."""
        from core.settlement import _get_ap
        ap_cap = int(ALL_TEST_ENV["AP_CAP"])
        recovery_mins = int(ALL_TEST_ENV["AP_RECOVERY_MINUTES"])
        now = _now()
        ap_full_time = now + timedelta(minutes=ap_cap * recovery_mins)
        await self._insert_player(ap_full_time=ap_full_time)
        async with schema.get_connection() as db:
            ap = await _get_ap(db, self.TEST_USER, now)
        self.assertEqual(ap, 0)


if __name__ == "__main__":
    unittest.main()

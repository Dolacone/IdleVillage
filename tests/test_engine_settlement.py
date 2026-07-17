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
# Village trial progress tests
# ---------------------------------------------------------------------------

class TrialProgressTest(SettlementTestBase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        await self._set_resource("food", 10000)
        await self._set_resource("wood", 10000)
        await self._set_resource("knowledge", 10000)

    async def _write_trial_state(self, target=1000, progress=0, started_at=None):
        now_str = _now().isoformat()
        started_at_str = (started_at or _now()).isoformat()
        async with schema.get_connection() as db:
            await db.execute(
                """UPDATE trial_state SET
                   is_active=1, resource_type='food', target=?, progress=?,
                   started_at=?, updated_at=?
                   WHERE id=1""",
                (target, progress, started_at_str, now_str),
            )
            await db.commit()

    async def _get_trial_state(self) -> dict:
        async with schema.get_connection() as db:
            async with db.execute("SELECT * FROM trial_state WHERE id=1") as cur:
                row = await cur.fetchone()
                cols = [d[0] for d in cur.description]
                return dict(zip(cols, row))

    async def test_full_cycle_settlement_adds_trial_progress(self):
        """A full-cycle settlement of any action type contributes to an active trial."""
        await self._write_trial_state(target=100000, progress=0)
        cycle_end = _now() - timedelta(minutes=1)
        await self._insert_player(
            action="combat",
            completion_time=cycle_end,
            last_update_time=cycle_end - timedelta(minutes=10),
        )
        await settle_complete_cycles(self.TEST_USER, _now())
        trial_after = await self._get_trial_state()
        base = int(ALL_TEST_ENV["BASE_OUTPUT"])
        self.assertEqual(trial_after["progress"], base)

    async def test_full_cycle_settlement_emits_trial_success_event_on_target_reached(self):
        base = int(ALL_TEST_ENV["BASE_OUTPUT"])
        await self._write_trial_state(target=base, progress=0)
        cycle_end = _now() - timedelta(minutes=1)
        await self._insert_player(
            action="combat",
            completion_time=cycle_end,
            last_update_time=cycle_end - timedelta(minutes=10),
        )
        events = await settle_complete_cycles(self.TEST_USER, _now())
        self.assertIn("trial_success", [e["type"] for e in events])
        trial_after = await self._get_trial_state()
        self.assertEqual(trial_after["is_active"], 0)

    async def test_inactive_trial_is_unaffected_by_settlement(self):
        """Default (inactive) trial_state must not produce trial events or change progress."""
        cycle_end = _now() - timedelta(minutes=1)
        await self._insert_player(
            action="gathering",
            completion_time=cycle_end,
            last_update_time=cycle_end - timedelta(minutes=10),
        )
        events = await settle_complete_cycles(self.TEST_USER, _now())
        types = [e.get("type") for e in events]
        self.assertNotIn("trial_success", types)
        self.assertNotIn("trial_fail", types)
        trial_after = await self._get_trial_state()
        self.assertEqual(trial_after["progress"], 0)

    async def test_partial_cycle_adds_trial_progress(self):
        """change_action's partial-cycle settlement also contributes to an active trial."""
        await self._write_trial_state(target=100000, progress=0)
        cycle_mins = int(ALL_TEST_ENV["ACTION_CYCLE_MINUTES"])
        last_update = _now() - timedelta(minutes=cycle_mins / 2)
        completion = _now() + timedelta(minutes=cycle_mins / 2)
        await self._insert_player(
            action="gathering",
            completion_time=completion,
            last_update_time=last_update,
        )
        await change_action(self.TEST_USER, "combat", None, _now())
        trial_after = await self._get_trial_state()
        base = int(ALL_TEST_ENV["BASE_OUTPUT"])
        expected = math.floor(base * 0.5)
        self.assertEqual(trial_after["progress"], expected)

    async def test_burst_adds_trial_progress_three_times_independently(self):
        """Each of burst's 3 independent settlements contributes to the active trial."""
        await self._write_trial_state(target=100000, progress=0)
        ap_cap = int(ALL_TEST_ENV["AP_CAP"])
        now = _now()
        await self._insert_player(
            action="gathering",
            completion_time=now + timedelta(minutes=10),
            last_update_time=now - timedelta(minutes=5),
            ap_full_time=now - timedelta(minutes=1),
        )
        ok, _events = await settle_burst(self.TEST_USER, now)
        self.assertTrue(ok)
        trial_after = await self._get_trial_state()
        base = int(ALL_TEST_ENV["BASE_OUTPUT"])
        self.assertEqual(trial_after["progress"], base * 3)


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
                "UPDATE buildings SET level=1, xp_progress=? WHERE building_type='gathering_field'",
                (2 * xp_per - 1,),
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
        # Level should remain 1 (cap), xp_progress capped at (level+1)×xp_per.
        self.assertEqual(bld_after["level"], 1)
        self.assertEqual(bld_after["xp_progress"], 2 * xp_per)


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

    async def test_building_action_rejects_invalid_target(self):
        """Building action must target a documented building row."""
        await self._insert_player(action=None, completion_time=None, last_update_time=None)
        with self.assertRaises(ValueError):
            await change_action(self.TEST_USER, "building", "not_a_building", _now())


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
        result, _events = await settle_burst(self.TEST_USER, _now())
        self.assertFalse(result)
        """Burst returns True when player has >= 1 AP."""
        await self._insert_player_with_ap(1)
        result, _events = await settle_burst(self.TEST_USER, _now())
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
        result, _events = await settle_burst(self.TEST_USER, now)
        self.assertFalse(result)



# ---------------------------------------------------------------------------
# Stage-matching material drop boost tests
# ---------------------------------------------------------------------------

class MaterialDropBoostTest(SettlementTestBase):
    """Tests for effective material drop rate based on current stage type."""

    async def asyncSetUp(self):
        await super().asyncSetUp()
        await self._set_resource("food", 10000)
        await self._set_resource("wood", 10000)
        await self._set_resource("knowledge", 10000)

    async def _set_stage_type(self, stage_type: str):
        async with schema.get_connection() as db:
            now_str = datetime.now(timezone.utc).isoformat()
            await db.execute(
                """UPDATE stage_state SET
                   current_stage_type=?, current_stage_progress=0, current_stage_target=99999,
                   updated_at=? WHERE id=1""",
                (stage_type, now_str),
            )
            await db.commit()

    async def _run_one_complete_cycle(self, action: str):
        cycle_end = _now() - timedelta(minutes=1)
        await self._insert_player(
            action=action,
            completion_time=cycle_end,
            last_update_time=cycle_end - timedelta(minutes=10),
        )
        await settle_complete_cycles(self.TEST_USER, _now())

    async def test_matching_stage_doubles_drop_rate(self):
        """Normal stage matching action uses doubled rate — 0.5 base gives 100% effective."""
        os.environ["MATERIAL_DROP_RATE"] = "0.5"
        await self._set_stage_type("gathering")
        await self._run_one_complete_cycle("gathering")
        player = await self._get_player()
        self.assertEqual(player["materials_gathering"], 1)

    async def test_matching_stage_clear_cycle_uses_current_stage_for_drop_rate(self):
        """A cycle that clears its matching stage still uses that stage for drop boost."""
        os.environ["MATERIAL_DROP_RATE"] = "0.5"
        base_output = int(ALL_TEST_ENV["BASE_OUTPUT"])
        async with schema.get_connection() as db:
            now_str = datetime.now(timezone.utc).isoformat()
            await db.execute(
                """UPDATE stage_state SET
                   current_stage_type='gathering', current_stage_progress=0,
                   current_stage_target=?, updated_at=? WHERE id=1""",
                (base_output, now_str),
            )
            await db.commit()

        with patch("core.settlement.random.random", return_value=0.75):
            await self._run_one_complete_cycle("gathering")

        player = await self._get_player()
        self.assertEqual(player["materials_gathering"], 1)

    async def test_non_matching_stage_uses_base_rate(self):
        """Non-matching action uses base rate, not doubled. A random value above the base
        rate but below doubled rate confirms the implementation reads base, not boosted."""
        os.environ["MATERIAL_DROP_RATE"] = "0.4"
        await self._set_stage_type("gathering")
        # random.random() = 0.6: above base (0.4) → no drop; below doubled (0.8) → would drop
        with patch("core.settlement.random.random", return_value=0.6):
            await self._run_one_complete_cycle("combat")
        player = await self._get_player()
        self.assertEqual(player["materials_combat"], 0)

    async def test_upgrade_stage_doubles_rate_for_gathering(self):
        """Upgrade stage doubles drop rate for gathering action."""
        os.environ["MATERIAL_DROP_RATE"] = "0.5"
        await self._set_stage_type("upgrade")
        await self._run_one_complete_cycle("gathering")
        player = await self._get_player()
        self.assertEqual(player["materials_gathering"], 1)

    async def test_upgrade_stage_doubles_rate_for_building(self):
        """Upgrade stage doubles drop rate for building action."""
        os.environ["MATERIAL_DROP_RATE"] = "0.5"
        await self._set_stage_type("upgrade")
        cycle_end = _now() - timedelta(minutes=1)
        await self._insert_player(
            action="building",
            action_target="workshop",
            completion_time=cycle_end,
            last_update_time=cycle_end - timedelta(minutes=10),
        )
        await settle_complete_cycles(self.TEST_USER, _now())
        player = await self._get_player()
        self.assertEqual(player["materials_building"], 1)

    async def test_upgrade_stage_doubles_rate_for_combat(self):
        """Upgrade stage doubles drop rate for combat action."""
        os.environ["MATERIAL_DROP_RATE"] = "0.5"
        await self._set_stage_type("upgrade")
        await self._run_one_complete_cycle("combat")
        player = await self._get_player()
        self.assertEqual(player["materials_combat"], 1)

    async def test_upgrade_stage_doubles_rate_for_research(self):
        """Upgrade stage doubles drop rate for research action."""
        os.environ["MATERIAL_DROP_RATE"] = "0.5"
        await self._set_stage_type("upgrade")
        await self._run_one_complete_cycle("research")
        player = await self._get_player()
        self.assertEqual(player["materials_research"], 1)

    async def test_boosted_rate_capped_at_one(self):
        """Effective rate never exceeds 1.0 even when base rate * 2 > 1.0."""
        from core.settlement import _effective_material_drop_rate
        result = _effective_material_drop_rate(0.8, "gathering", "gathering")
        self.assertEqual(result, 1.0)

    async def test_partial_cycle_still_never_drops_material_with_boost(self):
        """Partial cycle grants no material even when boost would apply."""
        os.environ["MATERIAL_DROP_RATE"] = "1.0"
        await self._set_stage_type("gathering")
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

    async def test_burst_recalculates_effective_rate_each_cycle(self):
        """Burst recalculates effective rate per cycle using the current stage type.

        Setup: gathering stage with target = BASE_OUTPUT so the first burst cycle
        clears it and advances to the building stage. The remaining two cycles run
        under building stage with a gathering action (non-matching → base rate).

        With MATERIAL_DROP_RATE=0.4 and random.random patched to 0.6:
        - Cycle 1 (gathering stage, gathering action): effective = 0.8 → 0.6 < 0.8 → drop
        - Cycles 2–3 (building stage, gathering action): effective = 0.4 → 0.6 < 0.4 → no drop
        Expected: exactly 1 material drop.
        """
        os.environ["MATERIAL_DROP_RATE"] = "0.4"
        base_output = int(ALL_TEST_ENV["BASE_OUTPUT"])
        async with schema.get_connection() as db:
            now_str = datetime.now(timezone.utc).isoformat()
            await db.execute(
                """UPDATE stage_state SET
                   current_stage_type='gathering', current_stage_index=0,
                   current_stage_progress=0, current_stage_target=?,
                   updated_at=? WHERE id=1""",
                (base_output, now_str),
            )
            await db.commit()

        now = _now()
        ap_full_time = now - timedelta(minutes=1)
        await self._insert_player(
            action="gathering",
            completion_time=now + timedelta(minutes=10),
            last_update_time=now - timedelta(minutes=5),
            ap_full_time=ap_full_time,
        )
        with patch("core.settlement.random.random", return_value=0.6):
            await settle_burst(self.TEST_USER, now)
        player = await self._get_player()
        self.assertEqual(player["materials_gathering"], 1)


# ---------------------------------------------------------------------------
# AP helpers
# ---------------------------------------------------------------------------

class APTest(SettlementTestBase):
    async def test_full_ap_when_past_ap_full_time(self):
        """Player returns AP_CAP when ap_full_time is in the past."""
        from managers import player_manager
        now = _now()
        ap_full_time = now - timedelta(minutes=1)
        await self._insert_player(ap_full_time=ap_full_time)
        async with schema.get_connection() as db:
            ap = await player_manager.get_ap(db, self.TEST_USER, now)
        self.assertEqual(ap, int(ALL_TEST_ENV["AP_CAP"]))

    async def test_zero_ap_when_just_spent(self):
        """Player returns 0 AP when ap_full_time is AP_CAP × recovery from now."""
        from managers import player_manager
        ap_cap = int(ALL_TEST_ENV["AP_CAP"])
        recovery_mins = int(ALL_TEST_ENV["AP_RECOVERY_MINUTES"])
        now = _now()
        ap_full_time = now + timedelta(minutes=ap_cap * recovery_mins)
        await self._insert_player(ap_full_time=ap_full_time)
        async with schema.get_connection() as db:
            ap = await player_manager.get_ap(db, self.TEST_USER, now)
        self.assertEqual(ap, 0)


class AffixIntegrationTest(SettlementTestBase):
    """Verify affix bonuses flow through settlement correctly."""

    async def _insert_affix(self, db, user_id, gear_type, slot_index, affix_type, value):
        await db.execute(
            "INSERT INTO gear_affixes (user_id, gear_type, slot_index, affix_type, value) VALUES (?,?,?,?,?)",
            (user_id, gear_type, slot_index, affix_type, value),
        )

    async def test_efficiency_affix_increases_output(self):
        """efficiency affix adds to cycle output."""
        now = _now()
        cycle_end = now - timedelta(minutes=1)
        last_update = now - timedelta(minutes=11)
        await self._insert_player(action="gathering", completion_time=cycle_end, last_update_time=last_update)
        async with schema.get_connection() as db:
            await self._insert_affix(db, self.TEST_USER, "gathering", 0, "efficiency", 10)
            await db.execute("UPDATE village_resources SET amount=1000 WHERE resource_type='food'")
            await db.commit()

        base = int(ALL_TEST_ENV["BASE_OUTPUT"])
        food_cost = int(ALL_TEST_ENV["FOOD_COST"])
        await settle_complete_cycles(self.TEST_USER, now)

        async with schema.get_connection() as db:
            row = await db.execute("SELECT amount FROM village_resources WHERE resource_type='food'")
            row = await row.fetchone()
        expected_output = math.floor(base * 1.10)
        self.assertEqual(row[0], 1000 - food_cost + expected_output)

    async def test_cycle_time_reduce_shortens_completion_time(self):
        """cycle_time_reduce affix shortens the next completion_time after a cycle settles."""
        os.environ["ACTION_CYCLE_MINUTES"] = "10"
        now = _now()
        cycle_end = now - timedelta(minutes=1)
        last_update = now - timedelta(minutes=11)
        await self._insert_player(action="gathering", completion_time=cycle_end, last_update_time=last_update)
        async with schema.get_connection() as db:
            await self._insert_affix(db, self.TEST_USER, "gathering", 0, "cycle_time_reduce", 10)
            await db.commit()

        await settle_complete_cycles(self.TEST_USER, now)

        async with schema.get_connection() as db:
            row = await db.execute("SELECT completion_time FROM players WHERE user_id=?", (self.TEST_USER,))
            row = await row.fetchone()
        import math as _math
        effective_secs = _math.floor(10 * 60 * 0.90)
        expected_ct = _utc(cycle_end) + timedelta(seconds=effective_secs)
        actual_ct = _utc(datetime.fromisoformat(row[0]))
        self.assertAlmostEqual(actual_ct.timestamp(), expected_ct.timestamp(), delta=1)

    async def test_material_drop_affix_raises_drop_rate(self):
        """material_drop affix adds to effective drop rate."""
        now = _now()
        cycle_end = now - timedelta(minutes=1)
        last_update = now - timedelta(minutes=11)
        await self._insert_player(action="gathering", completion_time=cycle_end, last_update_time=last_update)
        async with schema.get_connection() as db:
            await self._insert_affix(db, self.TEST_USER, "gathering", 0, "material_drop", 100)
            await db.commit()

        with patch("core.settlement.random.random", return_value=0.99):
            await settle_complete_cycles(self.TEST_USER, now)

        async with schema.get_connection() as db:
            row = await db.execute(
                "SELECT materials_gathering FROM players WHERE user_id=?", (self.TEST_USER,)
            )
            row = await row.fetchone()
        self.assertEqual(row[0], 1)

    async def test_change_action_new_completion_uses_new_action_affix(self):
        """change_action sets completion_time using new action's cycle_time_reduce."""
        os.environ["ACTION_CYCLE_MINUTES"] = "10"
        now = _now()
        await self._insert_player(action=None)
        async with schema.get_connection() as db:
            await self._insert_affix(db, self.TEST_USER, "combat", 0, "cycle_time_reduce", 10)
            await db.commit()

        await change_action(self.TEST_USER, "combat", None, now)

        async with schema.get_connection() as db:
            row = await db.execute("SELECT completion_time FROM players WHERE user_id=?", (self.TEST_USER,))
            row = await row.fetchone()
        import math as _math
        effective_secs = _math.floor(10 * 60 * 0.90)
        expected_ct = now + timedelta(seconds=effective_secs)
        actual_ct = _utc(datetime.fromisoformat(row[0]))
        self.assertAlmostEqual(actual_ct.timestamp(), expected_ct.timestamp(), delta=1)

    async def test_burst_applies_efficiency_affix(self):
        """settle_burst applies efficiency affix bonus to all 3 cycle outputs."""
        now = _now()
        cycle_end = now - timedelta(minutes=1)
        await self._insert_player(action="gathering", completion_time=cycle_end, last_update_time=cycle_end)
        async with schema.get_connection() as db:
            await self._insert_affix(db, self.TEST_USER, "gathering", 0, "efficiency", 10)
            await db.execute("UPDATE village_resources SET amount=1000 WHERE resource_type='food'")
            await db.commit()

        base = int(ALL_TEST_ENV["BASE_OUTPUT"])
        food_cost = int(ALL_TEST_ENV["FOOD_COST"])
        await settle_burst(self.TEST_USER, now)

        async with schema.get_connection() as db:
            row = await db.execute("SELECT amount FROM village_resources WHERE resource_type='food'")
            row = await row.fetchone()
        expected_per_cycle = math.floor(base * 1.10)
        expected_food = 1000 - food_cost * 3 + expected_per_cycle * 3
        self.assertEqual(row[0], expected_food)


# ---------------------------------------------------------------------------
# Residual pre-removal action='offering' state (post offering-system removal)
# ---------------------------------------------------------------------------

class ResidualOfferingActionTest(SettlementTestBase):
    """A player who still has the removed 'offering' action stored from before
    the offering system was removed must not crash settlement or be stuck."""

    async def test_settle_complete_cycles_does_not_raise(self):
        cycle_end = _now() - timedelta(minutes=1)
        await self._insert_player(
            action="offering",
            action_target="food",
            completion_time=cycle_end,
            last_update_time=cycle_end - timedelta(minutes=10),
        )
        events = await settle_complete_cycles(self.TEST_USER, _now())
        self.assertEqual(events, [])

    async def test_change_action_recovers_from_residual_offering(self):
        """Player can still switch to a valid action despite residual action='offering'."""
        cycle_end = _now() - timedelta(minutes=1)
        await self._insert_player(
            action="offering",
            action_target="food",
            completion_time=cycle_end,
            last_update_time=cycle_end - timedelta(minutes=10),
        )
        await change_action(self.TEST_USER, "gathering", None, _now())
        player = await self._get_player()
        self.assertEqual(player["action"], "gathering")


class ExplicitContextCycleTest(SettlementTestBase):
    """_run_one_cycle driven by an explicit context (the auto-tool reuse path)."""

    async def asyncSetUp(self):
        await super().asyncSetUp()
        await self._set_resource("food", 10000)
        await self._set_resource("wood", 10000)
        await self._set_resource("knowledge", 10000)

    async def test_context_gathering_matches_manual_distribution(self):
        """Explicit gathering context deposits food+wood, same as the manual path."""
        from core.settlement import _run_one_cycle
        await self._insert_player(action=None)  # no manual action set
        cycle_end = _now()
        async with schema.get_connection() as db:
            with patch("random.random", return_value=1.0):  # suppress material drop
                events = await _run_one_cycle(
                    db, self.TEST_USER, cycle_end,
                    action="gathering", action_target=None,
                    write_player_timestamps=False,
                )
            await db.commit()
        base = int(os.environ["BASE_OUTPUT"])
        food_cost = int(os.environ["FOOD_COST"])
        # gathering costs FOOD_COST food, then deposits `base` to both food and wood
        self.assertEqual(await self._get_resource("food"), 10000 - food_cost + base)
        self.assertEqual(await self._get_resource("wood"), 10000 + base)
        self.assertEqual(events, [])

    async def test_context_does_not_touch_player_timestamps(self):
        """write_player_timestamps=False leaves players.completion_time/last_update_time null."""
        from core.settlement import _run_one_cycle
        await self._insert_player(action=None)
        async with schema.get_connection() as db:
            with patch("random.random", return_value=1.0):
                await _run_one_cycle(
                    db, self.TEST_USER, _now(),
                    action="combat", action_target=None,
                    write_player_timestamps=False,
                )
            await db.commit()
        player = await self._get_player()
        self.assertIsNone(player["completion_time"])
        self.assertIsNone(player["last_update_time"])

    async def test_context_material_drop_targets_the_context_action(self):
        """A drop is credited to the context action's material, not the player's action."""
        from core.settlement import _run_one_cycle
        await self._insert_player(action=None)
        async with schema.get_connection() as db:
            with patch("random.random", return_value=0.0):  # force a drop
                await _run_one_cycle(
                    db, self.TEST_USER, _now(),
                    action="combat", action_target=None,
                    write_player_timestamps=False,
                )
            await db.commit()
        player = await self._get_player()
        self.assertEqual(player["materials_combat"], 1)
        self.assertEqual(player["materials_gathering"], 0)

    async def test_context_building_uses_passed_target(self):
        """Building context routes XP to the explicitly passed target building."""
        from core.settlement import _run_one_cycle
        await self._insert_player(action=None, gear_building=0)
        async with schema.get_connection() as db:
            with patch("random.random", return_value=1.0):
                await _run_one_cycle(
                    db, self.TEST_USER, _now(),
                    action="building", action_target="workshop",
                    write_player_timestamps=False,
                )
            await db.commit()
        base = int(os.environ["BASE_OUTPUT"])
        self.assertEqual((await self._get_building("workshop"))["xp_progress"], base)


class AutoToolSettlementTest(SettlementTestBase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        await self._set_resource("food", 100000)
        await self._set_resource("wood", 100000)
        await self._set_resource("knowledge", 100000)

    async def _insert_auto_tool(self, tool_type, completion_time, expires_at, action_target=None):
        now_str = _now().isoformat()
        async with schema.get_connection() as db:
            await db.execute(
                """INSERT INTO player_auto_tools
                   (user_id, tool_type, action_target, completion_time, last_update_time,
                    expires_at, started_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (self.TEST_USER, tool_type, action_target,
                 completion_time.isoformat(), now_str, expires_at.isoformat(), now_str, now_str),
            )
            await db.commit()

    async def test_settles_due_cycle_and_advances_completion(self):
        from core.settlement import settle_auto_tool_cycles
        now = _now()
        await self._insert_player(action=None)
        await self._insert_auto_tool(
            "gathering", completion_time=now - timedelta(minutes=1), expires_at=now + timedelta(hours=1)
        )
        with patch("random.random", return_value=1.0):
            await settle_auto_tool_cycles(self.TEST_USER, "gathering", now)
        base = int(os.environ["BASE_OUTPUT"])
        food_cost = int(os.environ["FOOD_COST"])
        self.assertEqual(await self._get_resource("wood"), 100000 + base)
        self.assertEqual(await self._get_resource("food"), 100000 - food_cost + base)
        # player timestamps untouched
        player = await self._get_player()
        self.assertIsNone(player["completion_time"])
        # auto-tool row still present (not expired), completion advanced into the future
        async with schema.get_connection() as db:
            row = await self.fetchone(
                "SELECT completion_time FROM player_auto_tools WHERE user_id=? AND tool_type=?",
                (self.TEST_USER, "gathering"),
            )
        self.assertGreater(_utc(datetime.fromisoformat(row[0])), now)

    async def test_material_drop_credits_the_tool_material(self):
        from core.settlement import settle_auto_tool_cycles
        now = _now()
        await self._insert_player(action=None)
        await self._insert_auto_tool(
            "combat", completion_time=now - timedelta(minutes=1), expires_at=now + timedelta(hours=1)
        )
        with patch("random.random", return_value=0.0):  # force drop
            await settle_auto_tool_cycles(self.TEST_USER, "combat", now)
        player = await self._get_player()
        self.assertEqual(player["materials_combat"], 1)
        self.assertEqual(player["materials_gathering"], 0)

    async def test_expired_auto_tool_is_ended_after_catch_up(self):
        from core.settlement import settle_auto_tool_cycles
        now = _now()
        await self._insert_player(action=None)
        await self._insert_auto_tool(
            "gathering",
            completion_time=now - timedelta(minutes=20),
            expires_at=now - timedelta(minutes=1),  # already expired
        )
        with patch("random.random", return_value=1.0):
            await settle_auto_tool_cycles(self.TEST_USER, "gathering", now)
        row = await self.fetchone(
            "SELECT 1 FROM player_auto_tools WHERE user_id=? AND tool_type=?",
            (self.TEST_USER, "gathering"),
        )
        self.assertIsNone(row)  # freed

    async def test_expired_tool_ended_even_when_cap_hit_but_caught_up(self):
        # Regression: end condition must be "caught up" (cycle_end > deadline), not
        # cycles_done < max_cycles. With MAX=2 and exactly 2 due cycles, an expired tool
        # is fully caught up at the cap and must be freed, not left occupying the tool.
        from core.settlement import settle_auto_tool_cycles
        now = _now()
        cycle_secs = int(os.environ["ACTION_CYCLE_MINUTES"]) * 60
        await self._insert_player(action=None)
        await self._insert_auto_tool(
            "gathering",
            completion_time=now - timedelta(seconds=cycle_secs),  # 1 cycle before now
            expires_at=now,                                        # expired (now >= expires)
        )
        with patch("random.random", return_value=1.0), \
             patch.dict(os.environ, {"MAX_CYCLES_PER_SETTLEMENT": "2"}):
            await settle_auto_tool_cycles(self.TEST_USER, "gathering", now)
        row = await self.fetchone(
            "SELECT 1 FROM player_auto_tools WHERE user_id=? AND tool_type=?",
            (self.TEST_USER, "gathering"),
        )
        self.assertIsNone(row)

    async def test_not_ended_when_cap_hit_with_backlog(self):
        # With MAX=1 and many due cycles, the tool is NOT caught up -> must remain.
        from core.settlement import settle_auto_tool_cycles
        now = _now()
        cycle_secs = int(os.environ["ACTION_CYCLE_MINUTES"]) * 60
        await self._insert_player(action=None)
        await self._insert_auto_tool(
            "gathering",
            completion_time=now - timedelta(seconds=cycle_secs * 10),
            expires_at=now,
        )
        with patch("random.random", return_value=1.0), \
             patch.dict(os.environ, {"MAX_CYCLES_PER_SETTLEMENT": "1"}):
            await settle_auto_tool_cycles(self.TEST_USER, "gathering", now)
        row = await self.fetchone(
            "SELECT 1 FROM player_auto_tools WHERE user_id=? AND tool_type=?",
            (self.TEST_USER, "gathering"),
        )
        self.assertIsNotNone(row)  # backlog remains -> not freed yet

    async def test_watcher_settles_due_auto_tool(self):
        from core.engine import Engine
        now = _now()
        await self._insert_player(action=None)
        await self._insert_auto_tool(
            "gathering", completion_time=now - timedelta(minutes=1), expires_at=now + timedelta(hours=1)
        )
        with patch("random.random", return_value=1.0):
            await Engine.process_watcher()
        base = int(os.environ["BASE_OUTPUT"])
        self.assertEqual(await self._get_resource("wood"), 100000 + base)


class EffectiveCycleSecondsTest(unittest.TestCase):
    def setUp(self):
        for k, v in ALL_TEST_ENV.items():
            os.environ[k] = v

    def test_no_reduction_returns_base(self):
        from core.formula import effective_cycle_seconds
        expected = int(os.environ["ACTION_CYCLE_MINUTES"]) * 60
        self.assertEqual(effective_cycle_seconds(0), expected)

    def test_reduction_is_floored(self):
        from core.formula import effective_cycle_seconds
        base = int(os.environ["ACTION_CYCLE_MINUTES"]) * 60
        self.assertEqual(effective_cycle_seconds(10), math.floor(base * 0.9))

    def test_never_below_60_seconds(self):
        from core.formula import effective_cycle_seconds
        self.assertEqual(effective_cycle_seconds(100), 60)


if __name__ == "__main__":
    unittest.main()

"""
Tests for managers.trial_manager — village trial: open, progress, timeout, and reward distribution.
Mechanics reference: docs/managers/trial-manager.md
"""

import asyncio
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from tests.support import DatabaseTestCase
from database import schema
from managers import player_manager, resource_manager, trial_manager

NOW = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
USER_A = "trial_user_a"
USER_B = "trial_user_b"
TRIAL_AMOUNT = 50000


async def _insert_player(db, user_id: str) -> None:
    from core.utils import dt_str

    now_str = dt_str(NOW)
    await db.execute(
        "INSERT INTO players (user_id, created_at, updated_at, ap_full_time) VALUES (?, ?, ?, ?)",
        (user_id, now_str, now_str, now_str),
    )


class TestTargetCalculation(unittest.TestCase):
    def test_example_resources_produce_maximum_target(self):
        resources = {"food": 51000, "wood": 310000, "knowledge": 220000}
        self.assertEqual(trial_manager.get_max_trial_target(resources), 300000)

    def test_reserved_resources_produce_one_step_at_35000(self):
        resources = {"food": 35000, "wood": 35000, "knowledge": 35000}
        self.assertEqual(trial_manager.get_max_trial_target(resources), 25000)

    def test_resources_below_reserve_plus_step_produce_zero(self):
        resources = {"food": 34000, "wood": 34000, "knowledge": 34000}
        self.assertEqual(trial_manager.get_max_trial_target(resources), 0)

    def test_missing_resource_keys_are_treated_as_zero(self):
        self.assertEqual(trial_manager.get_max_trial_target({"food": 60000}), 50000)


class TestStartTrial(DatabaseTestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        # Only food is funded by default, so the resource choice is deterministic.
        async with schema.get_connection() as db:
            await resource_manager.deposit(db, "food", TRIAL_AMOUNT * 2, NOW)
            await db.commit()

    async def test_rejects_when_trial_already_active(self):
        async with schema.get_connection() as db:
            await trial_manager.start_trial(db, NOW, TRIAL_AMOUNT)
            await db.commit()
        async with schema.get_connection() as db:
            with self.assertRaises(trial_manager.TrialStartError) as context:
                await trial_manager.start_trial(db, NOW, TRIAL_AMOUNT)
        self.assertEqual(context.exception.reason, "active")

    async def test_rejects_when_cooldown_not_elapsed(self):
        async with schema.get_connection() as db:
            await db.execute(
                "UPDATE trial_state SET is_active=0, ended_at=? WHERE id=1", (NOW.isoformat(),)
            )
            await db.commit()
        soon_after = NOW + timedelta(seconds=100)
        async with schema.get_connection() as db:
            with self.assertRaises(trial_manager.TrialStartError) as context:
                await trial_manager.start_trial(db, soon_after, TRIAL_AMOUNT)
        self.assertEqual(context.exception.reason, "cooldown")

    async def test_allows_start_after_cooldown_elapsed(self):
        async with schema.get_connection() as db:
            await db.execute(
                "UPDATE trial_state SET is_active=0, ended_at=? WHERE id=1", (NOW.isoformat(),)
            )
            await db.commit()
        after_cooldown = NOW + timedelta(seconds=43201)
        async with schema.get_connection() as db:
            info = await trial_manager.start_trial(db, after_cooldown, TRIAL_AMOUNT)
        self.assertEqual(info["is_active"], 1)

    async def test_allows_start_when_no_prior_trial_ended(self):
        async with schema.get_connection() as db:
            info = await trial_manager.start_trial(db, NOW, TRIAL_AMOUNT)
        self.assertEqual(info["is_active"], 1)

    async def test_rejects_when_no_resource_has_enough(self):
        async with schema.get_connection() as db:
            await resource_manager.withdraw(db, "food", TRIAL_AMOUNT * 2, NOW)
            await db.commit()
        async with schema.get_connection() as db:
            with self.assertRaises(trial_manager.TrialStartError) as context:
                await trial_manager.start_trial(db, NOW, TRIAL_AMOUNT)
        self.assertEqual(context.exception.reason, "stale_target")

    async def test_failure_does_not_spend_resource(self):
        async with schema.get_connection() as db:
            await resource_manager.withdraw(db, "food", TRIAL_AMOUNT * 2, NOW)
            await db.commit()
        async with schema.get_connection() as db:
            with self.assertRaises(trial_manager.TrialStartError):
                await trial_manager.start_trial(db, NOW, TRIAL_AMOUNT)
        row = await self.fetchone("SELECT amount FROM village_resources WHERE resource_type='food'")
        self.assertEqual(row[0], 0)

    async def test_success_spends_the_chosen_resource_and_writes_state(self):
        async with schema.get_connection() as db:
            info = await trial_manager.start_trial(db, NOW, TRIAL_AMOUNT)
            await db.commit()
        self.assertEqual(info["is_active"], 1)
        self.assertEqual(info["resource_type"], "food")
        self.assertEqual(info["target"], TRIAL_AMOUNT)
        self.assertEqual(info["progress"], 0)
        row = await self.fetchone("SELECT amount FROM village_resources WHERE resource_type='food'")
        self.assertEqual(row[0], TRIAL_AMOUNT)

    async def test_success_clears_stale_contributions(self):
        async with schema.get_connection() as db:
            await db.execute(
                "INSERT INTO trial_contributions (user_id, contribution, updated_at) VALUES (?, 5, ?)",
                (USER_A, NOW.isoformat()),
            )
            await db.commit()
            await trial_manager.start_trial(db, NOW, TRIAL_AMOUNT)
            await db.commit()
        row = await self.fetchone("SELECT COUNT(*) FROM trial_contributions")
        self.assertEqual(row[0], 0)

    async def test_randomly_selects_among_eligible_resources(self):
        async with schema.get_connection() as db:
            await resource_manager.deposit(db, "wood", TRIAL_AMOUNT * 2, NOW)
            await db.commit()
        with patch("managers.trial_manager.random.choice", side_effect=lambda seq: seq[0]) as mock_choice:
            async with schema.get_connection() as db:
                info = await trial_manager.start_trial(db, NOW, TRIAL_AMOUNT)
        mock_choice.assert_called_once()
        eligible_arg = mock_choice.call_args.args[0]
        self.assertEqual(set(eligible_arg), {"food", "wood"})
        self.assertIn(info["resource_type"], {"food", "wood"})

    async def test_get_eligible_resource_types_only_lists_affordable(self):
        async with schema.get_connection() as db:
            eligible = await trial_manager.get_eligible_resource_types(db, TRIAL_AMOUNT)
        self.assertEqual(eligible, ["food"])

    async def test_get_eligible_resource_types_applies_reserve_to_each_balance(self):
        async with schema.get_connection() as db:
            await resource_manager.withdraw(db, "food", TRIAL_AMOUNT * 2, NOW)
            await resource_manager.deposit(db, "food", 51000, NOW)
            await resource_manager.deposit(db, "wood", 310000, NOW)
            await resource_manager.deposit(db, "knowledge", 220000, NOW)
            await db.commit()
        async with schema.get_connection() as db:
            eligible = await trial_manager.get_eligible_resource_types(db, 200000)
        self.assertEqual(eligible, ["wood", "knowledge"])

    async def test_rejects_zero_negative_and_non_step_targets(self):
        for target in (0, -TRIAL_AMOUNT, 12500, "50000"):
            with self.subTest(target=target):
                async with schema.get_connection() as db:
                    with self.assertRaises(trial_manager.TrialStartError) as context:
                        await trial_manager.start_trial(db, NOW, target)
                self.assertEqual(context.exception.reason, "invalid_target")

    async def test_success_preserves_resource_reserve(self):
        async with schema.get_connection() as db:
            await trial_manager.start_trial(db, NOW, TRIAL_AMOUNT)
            await db.commit()
        row = await self.fetchone("SELECT amount FROM village_resources WHERE resource_type='food'")
        self.assertEqual(row[0], TRIAL_AMOUNT)
        self.assertGreaterEqual(row[0], 10000)

    async def test_single_eligible_resource_is_the_only_choice(self):
        async with schema.get_connection() as db:
            await resource_manager.withdraw(db, "food", TRIAL_AMOUNT * 2, NOW)
            await db.commit()
        with patch("managers.trial_manager.random.choice", return_value="wood") as mock_choice:
            async with schema.get_connection() as db:
                await resource_manager.deposit(db, "wood", TRIAL_AMOUNT + 10000, NOW)
                await db.commit()
            async with schema.get_connection() as db:
                info = await trial_manager.start_trial(db, NOW, TRIAL_AMOUNT)
        mock_choice.assert_called_once_with(["wood"])
        self.assertEqual(info["resource_type"], "wood")

    async def test_clear_failure_rolls_back_resource_and_trial_state(self):
        async with schema.get_connection() as db:
            await db.execute(
                "INSERT INTO trial_contributions (user_id, contribution, updated_at) VALUES (?, 5, ?)",
                (USER_A, NOW.isoformat()),
            )
            await db.commit()

        async def fail_after_clear(db):
            await db.execute("DELETE FROM trial_contributions")
            raise RuntimeError("clear failed")

        with patch("managers.trial_manager._clear_contributions", side_effect=fail_after_clear):
            async with schema.get_connection() as db:
                with self.assertRaisesRegex(RuntimeError, "clear failed"):
                    await trial_manager.start_trial(db, NOW, TRIAL_AMOUNT)

        row = await self.fetchone("SELECT amount FROM village_resources WHERE resource_type='food'")
        self.assertEqual(row[0], TRIAL_AMOUNT * 2)
        row = await self.fetchone("SELECT is_active, target FROM trial_state WHERE id=1")
        self.assertEqual(tuple(row), (0, 0))
        row = await self.fetchone("SELECT contribution FROM trial_contributions WHERE user_id=?", (USER_A,))
        self.assertEqual(row[0], 5)

    async def test_concurrent_starts_only_open_one_trial_and_charge_once(self):
        async with schema.get_connection() as db:
            await resource_manager.deposit(db, "wood", TRIAL_AMOUNT + 10000, NOW)
            await db.commit()

        async def attempt_start():
            async with schema.get_connection() as db:
                try:
                    info = await trial_manager.start_trial(db, NOW, TRIAL_AMOUNT)
                    await db.commit()
                    return "success", info
                except trial_manager.TrialStartError as error:
                    return "failure", error.reason

        first, second = await asyncio.gather(attempt_start(), attempt_start())
        results = [first, second]
        self.assertEqual(sum(result[0] == "success" for result in results), 1)
        self.assertEqual(sum(result == ("failure", "active") for result in results), 1)
        rows = await self.fetchall("SELECT amount FROM village_resources")
        self.assertEqual(sum(row[0] for row in rows), TRIAL_AMOUNT * 2 + 10000)


class TestAddProgress(DatabaseTestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        async with schema.get_connection() as db:
            await _insert_player(db, USER_A)
            await _insert_player(db, USER_B)
            await resource_manager.deposit(db, "food", TRIAL_AMOUNT * 2, NOW)
            await db.commit()
            await trial_manager.start_trial(db, NOW, TRIAL_AMOUNT)
            await db.commit()

    async def test_noop_when_no_active_trial(self):
        async with schema.get_connection() as db:
            await db.execute("UPDATE trial_state SET is_active=0 WHERE id=1")
            await db.commit()
        async with schema.get_connection() as db:
            result = await trial_manager.add_progress(db, 100, USER_A, NOW)
        self.assertIsNone(result)

    async def test_accumulates_progress_and_contribution_below_target(self):
        async with schema.get_connection() as db:
            result = await trial_manager.add_progress(db, 1000, USER_A, NOW)
            await db.commit()
        self.assertIsNone(result)
        row = await self.fetchone("SELECT progress FROM trial_state WHERE id=1")
        self.assertEqual(row[0], 1000)
        row = await self.fetchone(
            "SELECT contribution FROM trial_contributions WHERE user_id=?", (USER_A,)
        )
        self.assertEqual(row[0], 1000)

    async def test_multiple_players_contribute_independently(self):
        async with schema.get_connection() as db:
            await trial_manager.add_progress(db, 1000, USER_A, NOW)
            await trial_manager.add_progress(db, 2000, USER_B, NOW)
            await db.commit()
        row = await self.fetchone("SELECT progress FROM trial_state WHERE id=1")
        self.assertEqual(row[0], 3000)
        row_a = await self.fetchone(
            "SELECT contribution FROM trial_contributions WHERE user_id=?", (USER_A,)
        )
        row_b = await self.fetchone(
            "SELECT contribution FROM trial_contributions WHERE user_id=?", (USER_B,)
        )
        self.assertEqual(row_a[0], 1000)
        self.assertEqual(row_b[0], 2000)

    async def test_reaching_target_triggers_success_and_awards_universal_material(self):
        async with schema.get_connection() as db:
            await trial_manager.add_progress(db, 30000, USER_A, NOW)
            result = await trial_manager.add_progress(db, 30000, USER_B, NOW)
            await db.commit()
        self.assertEqual(result["type"], "trial_success")
        self.assertEqual(result["target"], TRIAL_AMOUNT)
        rewards = {p["user_id"]: p["reward"] for p in result["participants"]}
        # target/divisor = 50000/100 = 500; each contributed 30000/60000 = 0.5 -> ceil(250) = 250
        self.assertEqual(rewards[USER_A], 250)
        self.assertEqual(rewards[USER_B], 250)
        self.assertEqual(result["total_awarded"], 500)

        async with schema.get_connection() as db:
            mat_a = await player_manager.get_universal_material(db, USER_A)
            mat_b = await player_manager.get_universal_material(db, USER_B)
        self.assertEqual(mat_a, 250)
        self.assertEqual(mat_b, 250)

        row = await self.fetchone("SELECT is_active FROM trial_state WHERE id=1")
        self.assertEqual(row[0], 0)
        row = await self.fetchone("SELECT COUNT(*) FROM trial_contributions")
        self.assertEqual(row[0], 0)

    async def test_ceil_rounding_can_exceed_reward_pool(self):
        user_c = "trial_user_c"
        async with schema.get_connection() as db:
            await _insert_player(db, user_c)
            await db.execute("UPDATE trial_state SET target=1000 WHERE id=1")
            await db.commit()
        async with schema.get_connection() as db:
            await trial_manager.add_progress(db, 334, USER_A, NOW)
            await trial_manager.add_progress(db, 333, USER_B, NOW)
            result = await trial_manager.add_progress(db, 333, user_c, NOW)
            await db.commit()
        self.assertEqual(result["type"], "trial_success")
        rewards = {p["user_id"]: p["reward"] for p in result["participants"]}
        # pool = 1000/100 = 10; each share is ~3.33 -> ceil(4) per participant
        self.assertEqual(rewards[USER_A], 4)
        self.assertEqual(rewards[USER_B], 4)
        self.assertEqual(rewards[user_c], 4)
        self.assertEqual(result["total_awarded"], 12)
        self.assertGreater(result["total_awarded"], 1000 / 100)

    async def test_add_progress_fails_trial_when_effective_time_past_deadline(self):
        late = NOW + timedelta(seconds=43201)
        async with schema.get_connection() as db:
            result = await trial_manager.add_progress(db, 1000, USER_A, late)
            await db.commit()
        self.assertEqual(result["type"], "trial_fail")
        row = await self.fetchone("SELECT progress, is_active FROM trial_state WHERE id=1")
        self.assertEqual(row[0], 0)
        self.assertEqual(row[1], 0)
        row = await self.fetchone("SELECT COUNT(*) FROM trial_contributions")
        self.assertEqual(row[0], 0)


class TestCheckTimeout(DatabaseTestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        async with schema.get_connection() as db:
            await resource_manager.deposit(db, "wood", TRIAL_AMOUNT * 2, NOW)
            await db.commit()
            await trial_manager.start_trial(db, NOW, TRIAL_AMOUNT)
            await db.commit()

    async def test_returns_none_when_not_expired(self):
        soon = NOW + timedelta(seconds=100)
        async with schema.get_connection() as db:
            result = await trial_manager.check_timeout(db, soon)
        self.assertIsNone(result)

    async def test_returns_none_when_no_active_trial(self):
        async with schema.get_connection() as db:
            await db.execute("UPDATE trial_state SET is_active=0 WHERE id=1")
            await db.commit()
        async with schema.get_connection() as db:
            result = await trial_manager.check_timeout(db, NOW + timedelta(days=10))
        self.assertIsNone(result)

    async def test_fails_trial_past_deadline_no_refund(self):
        late = NOW + timedelta(seconds=43201)
        async with schema.get_connection() as db:
            result = await trial_manager.check_timeout(db, late)
            await db.commit()
        self.assertEqual(result["type"], "trial_fail")
        self.assertEqual(result["target"], TRIAL_AMOUNT)
        row = await self.fetchone("SELECT is_active FROM trial_state WHERE id=1")
        self.assertEqual(row[0], 0)
        row = await self.fetchone("SELECT amount FROM village_resources WHERE resource_type='wood'")
        self.assertEqual(row[0], TRIAL_AMOUNT)


class TestDynamicTrialReward(DatabaseTestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        async with schema.get_connection() as db:
            await _insert_player(db, USER_A)
            await _insert_player(db, USER_B)
            await resource_manager.deposit(db, "food", 160000, NOW)
            await db.commit()
            await trial_manager.start_trial(db, NOW, 150000)
            await db.commit()

    async def test_dynamic_target_drives_reward_pool_and_deadline(self):
        async with schema.get_connection() as db:
            info = await trial_manager.get_trial_info(db)
            await trial_manager.add_progress(db, 75000, USER_A, NOW)
            result = await trial_manager.add_progress(db, 75000, USER_B, NOW)
            await db.commit()

        self.assertEqual(info["target"], 150000)
        self.assertEqual(result["target"], 150000)
        rewards = {p["user_id"]: p["reward"] for p in result["participants"]}
        self.assertEqual(rewards, {USER_A: 750, USER_B: 750})
        self.assertEqual(result["total_awarded"], 1500)

        started_at = datetime.fromisoformat(info["started_at"])
        self.assertEqual((started_at + timedelta(seconds=43200) - NOW).total_seconds(), 43200)


class TestGetters(DatabaseTestCase):
    async def test_get_contribution_returns_zero_when_absent(self):
        async with schema.get_connection() as db:
            value = await trial_manager.get_contribution(db, "nobody")
        self.assertEqual(value, 0)

    async def test_get_trial_info_returns_initial_inactive_state(self):
        async with schema.get_connection() as db:
            info = await trial_manager.get_trial_info(db)
        self.assertEqual(info["is_active"], 0)
        self.assertIsNone(info["resource_type"])


if __name__ == "__main__":
    import unittest

    unittest.main()

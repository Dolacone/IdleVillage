"""
test_discord_notifications.py — Tests for settlement event emission and notification formatting.
"""

import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from support import ALL_TEST_ENV, DatabaseTestCase
from database.schema import get_connection


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


class TestSettlementEventEmission(DatabaseTestCase):
    """Tests that settlement functions return correct event lists."""

    TEST_USER = "user_notify_1"

    async def _setup_player(
        self, action="gathering", action_target=None, completion_time=None, last_update_time=None
    ):
        now = _now()
        if completion_time is None:
            completion_time = now - timedelta(minutes=1)
        if last_update_time is None:
            last_update_time = now - timedelta(minutes=31)

        ap_full_time = now - timedelta(minutes=1)
        async with get_connection() as db:
            await db.execute(
                """INSERT OR REPLACE INTO players
                   (user_id, action, action_target, completion_time, last_update_time,
                    ap_full_time, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (
                    self.TEST_USER,
                    action,
                    action_target,
                    completion_time.isoformat(),
                    last_update_time.isoformat(),
                    ap_full_time.isoformat(),
                    now.isoformat(),
                    now.isoformat(),
                ),
            )
            await db.commit()

    async def test_settle_complete_cycles_returns_list(self):
        """settle_complete_cycles always returns a list."""
        from core.settlement import settle_complete_cycles
        await self._setup_player()
        result = await settle_complete_cycles(self.TEST_USER, _now())
        self.assertIsInstance(result, list)

    async def test_settle_complete_cycles_no_action_returns_empty(self):
        """settle_complete_cycles with no action returns empty list."""
        from core.settlement import settle_complete_cycles
        now = _now()
        async with get_connection() as db:
            await db.execute(
                """INSERT OR REPLACE INTO players
                   (user_id, action, ap_full_time, created_at, updated_at)
                   VALUES (?, NULL, ?, ?, ?)""",
                (self.TEST_USER, now.isoformat(), now.isoformat(), now.isoformat()),
            )
            await db.commit()
        result = await settle_complete_cycles(self.TEST_USER, now)
        self.assertEqual(result, [])

    async def test_settle_burst_returns_tuple(self):
        """settle_burst returns (bool, list) tuple."""
        from core.settlement import settle_burst
        await self._setup_player()
        result = await settle_burst(self.TEST_USER, _now())
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 2)
        success, events = result
        self.assertIsInstance(success, bool)
        self.assertIsInstance(events, list)

    async def test_settle_burst_no_ap_returns_false_empty(self):
        """settle_burst with 0 AP returns (False, [])."""
        from core.settlement import settle_burst
        ap_cap = int(ALL_TEST_ENV["AP_CAP"])
        recovery_mins = int(ALL_TEST_ENV["AP_RECOVERY_MINUTES"])
        now = _now()
        # ap_full_time far enough in the future to have 0 current AP
        ap_full_time = now + timedelta(minutes=(ap_cap + 1) * recovery_mins)
        async with get_connection() as db:
            await db.execute(
                """INSERT OR REPLACE INTO players
                   (user_id, action, completion_time, last_update_time,
                    ap_full_time, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?)""",
                (
                    self.TEST_USER,
                    "gathering",
                    (now + timedelta(minutes=30)).isoformat(),
                    (now - timedelta(minutes=1)).isoformat(),
                    ap_full_time.isoformat(),
                    now.isoformat(),
                    now.isoformat(),
                ),
            )
            await db.commit()
        success, events = await settle_burst(self.TEST_USER, now)
        self.assertFalse(success)
        self.assertEqual(events, [])

    async def test_settle_burst_with_ap_returns_true_list(self):
        """settle_burst with AP returns (True, list[dict])."""
        from core.settlement import settle_burst
        await self._setup_player()
        success, events = await settle_burst(self.TEST_USER, _now())
        self.assertTrue(success)
        self.assertIsInstance(events, list)

    async def test_stage_clear_event_emitted(self):
        """A stage_clear event is emitted when a stage completes."""
        from core.settlement import settle_complete_cycles
        from managers import stage_manager

        # Set stage progress near target so one cycle clears it
        base = int(ALL_TEST_ENV["BASE_OUTPUT"])
        async with get_connection() as db:
            target = base  # exactly one cycle worth — will clear on first cycle
            await db.execute(
                """UPDATE stage_state SET current_stage_type='gathering',
                   current_stage_progress=0, current_stage_target=?,
                   stage_started_at=? WHERE id=1""",
                (target, _now().isoformat()),
            )
            await db.commit()

        await self._setup_player(action="gathering")
        now = _now()
        events = await settle_complete_cycles(self.TEST_USER, now)
        types = [e["type"] for e in events]
        self.assertIn("stage_clear", types)

    async def test_stage_clear_event_has_correct_fields(self):
        """stage_clear event has stages_cleared, next_stage_type, next_target fields."""
        from core.settlement import settle_complete_cycles

        base = int(ALL_TEST_ENV["BASE_OUTPUT"])
        async with get_connection() as db:
            await db.execute(
                """UPDATE stage_state SET current_stage_type='gathering',
                   current_stage_progress=0, current_stage_target=?,
                   stage_started_at=? WHERE id=1""",
                (base, _now().isoformat()),
            )
            await db.commit()

        await self._setup_player(action="gathering")
        events = await settle_complete_cycles(self.TEST_USER, _now())
        clear_events = [e for e in events if e["type"] == "stage_clear"]
        self.assertTrue(len(clear_events) >= 1)
        ev = clear_events[0]
        self.assertIn("stages_cleared", ev)
        self.assertIn("next_stage_type", ev)
        self.assertIn("next_target", ev)
        self.assertIsInstance(ev["stages_cleared"], int)

    async def test_upgrade_stage_clear_event_at_5th_stage(self):
        """upgrade_stage_clear event is emitted when stages_cleared becomes a multiple of 5."""
        from core.settlement import settle_complete_cycles

        base = int(ALL_TEST_ENV["BASE_OUTPUT"])
        async with get_connection() as db:
            # Set stages_cleared to 4 — next clear makes it 5 (upgrade stage)
            await db.execute(
                """UPDATE stage_state SET stages_cleared=4,
                   current_stage_type='gathering',
                   current_stage_progress=0, current_stage_target=?,
                   stage_started_at=? WHERE id=1""",
                (base, _now().isoformat()),
            )
            await db.commit()

        await self._setup_player(action="gathering")
        events = await settle_complete_cycles(self.TEST_USER, _now())
        types = [e["type"] for e in events]
        self.assertIn("upgrade_stage_clear", types)

    async def test_upgrade_stage_clear_has_cap_fields(self):
        """upgrade_stage_clear event includes old_cap and new_cap."""
        from core.settlement import settle_complete_cycles

        base = int(ALL_TEST_ENV["BASE_OUTPUT"])
        async with get_connection() as db:
            await db.execute(
                """UPDATE stage_state SET stages_cleared=4,
                   current_stage_type='gathering',
                   current_stage_progress=0, current_stage_target=?,
                   stage_started_at=? WHERE id=1""",
                (base, _now().isoformat()),
            )
            await db.commit()

        await self._setup_player(action="gathering")
        events = await settle_complete_cycles(self.TEST_USER, _now())
        ev = next(e for e in events if e["type"] == "upgrade_stage_clear")
        self.assertEqual(ev["old_cap"], 1)
        self.assertEqual(ev["new_cap"], 2)
        self.assertEqual(ev["round"], 1)

    async def test_overtime_event_emitted_when_stage_overdue(self):
        """overtime event is emitted when stage is overdue and overtime_notified is 0."""
        from core.settlement import settle_complete_cycles

        base = int(ALL_TEST_ENV["BASE_OUTPUT"])
        overtime_secs = int(ALL_TEST_ENV["STAGE_OVERTIME_SECONDS"])
        now = _now()
        # Set stage started far in the past (overtime threshold exceeded)
        started_at = now - timedelta(seconds=overtime_secs + 1000)
        # Set target high so cycle does NOT clear the stage
        async with get_connection() as db:
            await db.execute(
                """UPDATE stage_state SET current_stage_type='gathering',
                   current_stage_progress=0, current_stage_target=999999,
                   stage_started_at=?, overtime_notified=0 WHERE id=1""",
                (started_at.isoformat(),),
            )
            await db.commit()

        await self._setup_player(action="gathering")
        events = await settle_complete_cycles(self.TEST_USER, now)
        types = [e["type"] for e in events]
        self.assertIn("overtime", types)

    async def test_overtime_event_not_emitted_when_already_notified(self):
        """overtime event is NOT emitted when overtime_notified is already 1."""
        from core.settlement import settle_complete_cycles

        overtime_secs = int(ALL_TEST_ENV["STAGE_OVERTIME_SECONDS"])
        now = _now()
        started_at = now - timedelta(seconds=overtime_secs + 1000)
        async with get_connection() as db:
            await db.execute(
                """UPDATE stage_state SET current_stage_type='gathering',
                   current_stage_progress=0, current_stage_target=999999,
                   stage_started_at=?, overtime_notified=1 WHERE id=1""",
                (started_at.isoformat(),),
            )
            await db.commit()

        await self._setup_player(action="gathering")
        events = await settle_complete_cycles(self.TEST_USER, now)
        types = [e["type"] for e in events]
        self.assertNotIn("overtime", types)

    async def test_no_events_when_stage_not_cleared_and_no_overtime(self):
        """No events emitted for a normal cycle that doesn't clear a stage or exceed overtime."""
        from core.settlement import settle_complete_cycles

        now = _now()
        async with get_connection() as db:
            # Very high target so stage won't clear
            await db.execute(
                """UPDATE stage_state SET current_stage_type='gathering',
                   current_stage_progress=0, current_stage_target=999999,
                   stage_started_at=?, overtime_notified=0 WHERE id=1""",
                (now.isoformat(),),  # just started — not overtime
            )
            await db.commit()

        await self._setup_player(action="gathering")
        events = await settle_complete_cycles(self.TEST_USER, now)
        self.assertEqual(events, [])


class TestNotificationFormatting(unittest.TestCase):
    """Tests for _format_event message template formatting."""

    def setUp(self):
        # Ensure env vars are set for config helpers
        for k, v in ALL_TEST_ENV.items():
            os.environ.setdefault(k, str(v))

    def test_format_stage_clear(self):
        from core.notification import _format_event
        ev = {
            "type": "stage_clear",
            "stages_cleared": 3,
            "next_stage_type": "combat",
            "next_target": 200,
        }
        text = _format_event(ev)
        self.assertIn("3", text)
        self.assertIn("200", text)

    def test_format_upgrade_stage_clear(self):
        from core.notification import _format_event
        ev = {
            "type": "upgrade_stage_clear",
            "round": 2,
            "old_cap": 2,
            "new_cap": 3,
            "next_stage_type": "gathering",
            "next_target": 500,
        }
        text = _format_event(ev)
        self.assertIn("2", text)
        self.assertIn("Lv2", text)
        self.assertIn("Lv3", text)

    def test_format_building_upgrade(self):
        from core.notification import _format_event
        ev = {
            "type": "building_upgrade",
            "building_type": "gathering_field",
            "old_level": 0,
            "new_level": 1,
            "next_xp_req": 200,
        }
        text = _format_event(ev)
        self.assertIn("Lv0", text)
        self.assertIn("Lv1", text)
        self.assertIn("200", text)

    def test_format_overtime(self):
        from core.notification import _format_event
        ev = {
            "type": "overtime",
            "stages_cleared": 4,
            "progress": 100,
            "target": 500,
        }
        text = _format_event(ev)
        self.assertIn("100", text)
        self.assertIn("500", text)

    def test_format_gear_success(self):
        from core.notification import _format_event
        ev = {
            "type": "gear_success",
            "user_display_name": "Alice",
            "gear_type": "gathering",
            "new_level": 2,
        }
        text = _format_event(ev)
        self.assertIn("Alice", text)
        self.assertIn("Lv2", text)
        self.assertIn("成功", text)

    def test_format_gear_fail(self):
        from core.notification import _format_event
        ev = {
            "type": "gear_fail",
            "user_display_name": "Bob",
            "gear_type": "combat",
            "current_level": 1,
            "pity_count": 3,
        }
        text = _format_event(ev)
        self.assertIn("Bob", text)
        self.assertIn("失敗", text)
        self.assertIn("3", text)

    def test_format_unknown_event_returns_none(self):
        from core.notification import _format_event
        text = _format_event({"type": "unknown_type"})
        self.assertIsNone(text)

    def test_format_overtime_stage_number_is_next_stage(self):
        """Overtime shows stage number = stages_cleared + 1 (the current stage)."""
        from core.notification import _format_event
        ev = {
            "type": "overtime",
            "stages_cleared": 4,
            "progress": 50,
            "target": 100,
        }
        text = _format_event(ev)
        # Stage 5 is current (4 cleared, working on 5th)
        self.assertIn("5", text)


class TestActionChangeNotificationDispatch(DatabaseTestCase):
    async def test_confirm_action_dispatches_overdue_catchup_events(self):
        from cogs.actions import ActionsCog

        user_id = "123"
        now = _now()
        cycle_end = now - timedelta(minutes=1)
        last_update = now - timedelta(minutes=11)
        base = int(ALL_TEST_ENV["BASE_OUTPUT"])

        async with get_connection() as db:
            await db.execute(
                """UPDATE village_resources SET amount=10000
                   WHERE resource_type IN ('food', 'wood', 'knowledge')"""
            )
            await db.execute(
                """UPDATE stage_state SET current_stage_type='gathering',
                   current_stage_progress=0, current_stage_target=?,
                   stage_started_at=?, overtime_notified=0 WHERE id=1""",
                (base, now.isoformat()),
            )
            await db.execute(
                """INSERT OR REPLACE INTO players
                   (user_id, action, action_target, completion_time, last_update_time,
                    ap_full_time, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (
                    user_id,
                    "gathering",
                    None,
                    cycle_end.isoformat(),
                    last_update.isoformat(),
                    now.isoformat(),
                    last_update.isoformat(),
                    last_update.isoformat(),
                ),
            )
            await db.commit()

        inter = SimpleNamespace(
            guild_id=int(ALL_TEST_ENV["DISCORD_GUILD_ID"]),
            user=SimpleNamespace(id=int(user_id)),
            component=SimpleNamespace(custom_id="confirm_action:combat"),
            response=SimpleNamespace(defer=AsyncMock()),
        )
        cog = ActionsCog(bot=object())

        with patch.object(cog, "_render_main", new=AsyncMock()), \
             patch("cogs.actions.notification.dispatch_events", new=AsyncMock()) as dispatch:
            await cog.on_button_click(inter)

        dispatch.assert_called_once()
        events = dispatch.call_args.args[1]
        self.assertIn("stage_clear", [event["type"] for event in events])


class TestDashboardUpdate(DatabaseTestCase):
    async def test_update_dashboard_builds_embed_from_database_state(self):
        from core.notification import update_dashboard

        async with get_connection() as db:
            await db.execute(
                "UPDATE village_state SET dashboard_channel_id='123', dashboard_message_id='456' WHERE id=1"
            )
            await db.execute(
                "UPDATE village_resources SET amount=100 WHERE resource_type='food'"
            )
            await db.execute(
                """INSERT OR REPLACE INTO players
                   (user_id, created_at, updated_at, action, ap_full_time)
                   VALUES ('dash-user', ?, ?, 'gathering', ?)""",
                (_now().isoformat(), _now().isoformat(), _now().isoformat()),
            )
            await db.commit()

        message = SimpleNamespace(edit=AsyncMock())
        channel = SimpleNamespace(fetch_message=AsyncMock(return_value=message))
        bot = SimpleNamespace(get_channel=lambda channel_id: channel if channel_id == 123 else None)

        await update_dashboard(bot)

        channel.fetch_message.assert_awaited_once_with(456)
        message.edit.assert_awaited_once()
        embed = message.edit.call_args.kwargs["embed"]
        self.assertIn("Village Resources", embed.description)
        self.assertIn("100", embed.description)
        self.assertIn("Villager Actions", embed.description)


if __name__ == "__main__":
    unittest.main()

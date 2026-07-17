"""
Tests for managers.auto_tool_manager — activation, refuel cap, mutual exclusion, lifecycle.
Mechanics reference: docs/managers/auto-tool-manager.md
"""

import os
import unittest
from datetime import datetime, timedelta, timezone

from support import ALL_TEST_ENV, DatabaseTestCase
from database import schema
from core.settlement import change_action
from core.utils import dt_str
from managers import auto_tool_manager, player_manager

NOW = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
USER = "auto_user"


async def _insert_player(db, user_id=USER, action=None, action_target=None, **materials):
    now_str = dt_str(NOW)
    await db.execute(
        "INSERT OR IGNORE INTO players (user_id, ap_full_time, created_at, updated_at) VALUES (?,?,?,?)",
        (user_id, now_str, now_str, now_str),
    )
    await db.execute(
        "UPDATE players SET action=?, action_target=?, updated_at=? WHERE user_id=?",
        (action, action_target, now_str, user_id),
    )
    for col, amount in materials.items():
        await db.execute(
            f"UPDATE players SET {col}=? WHERE user_id=?", (amount, user_id)
        )
    await db.commit()


class MaxAddMaterials(unittest.TestCase):
    def setUp(self):
        for k, v in ALL_TEST_ENV.items():
            os.environ[k] = v

    def test_fresh_activation_allows_full_cap(self):
        self.assertEqual(auto_tool_manager.max_add_materials(None, NOW), 6)

    def test_remaining_5h01m_allows_zero(self):
        expires = dt_str(NOW + timedelta(hours=5, minutes=1))
        self.assertEqual(auto_tool_manager.max_add_materials(expires, NOW), 0)

    def test_remaining_1m_allows_five(self):
        expires = dt_str(NOW + timedelta(minutes=1))
        self.assertEqual(auto_tool_manager.max_add_materials(expires, NOW), 5)

    def test_remaining_at_cap_allows_zero(self):
        expires = dt_str(NOW + timedelta(hours=6))
        self.assertEqual(auto_tool_manager.max_add_materials(expires, NOW), 0)


class StartAutoTool(DatabaseTestCase):
    async def test_start_deducts_own_material_and_writes_row(self):
        async with schema.get_connection() as db:
            await _insert_player(db, materials_gathering=5, materials_universal=9)
            await auto_tool_manager.start(db, USER, "gathering", 3, None, NOW)
            await db.commit()
            row = await auto_tool_manager.get(db, USER, "gathering")
            gathering = await player_manager.get_material(db, USER, "gathering")
            universal = await player_manager.get_universal_material(db, USER)
        self.assertIsNotNone(row)
        self.assertEqual(gathering, 2)          # 5 - 3 spent
        self.assertEqual(universal, 9)          # universal never touched
        self.assertEqual(row["expires_at"], dt_str(NOW + timedelta(hours=3)))

    async def test_start_insufficient_material_raises_and_writes_nothing(self):
        async with schema.get_connection() as db:
            await _insert_player(db, materials_gathering=2)
            with self.assertRaises(ValueError):
                await auto_tool_manager.start(db, USER, "gathering", 3, None, NOW)
            # not committed -> connection rolls back; re-open to confirm clean state
        async with schema.get_connection() as db:
            row = await auto_tool_manager.get(db, USER, "gathering")
            gathering = await player_manager.get_material(db, USER, "gathering")
        self.assertIsNone(row)
        self.assertEqual(gathering, 2)

    async def test_start_rejects_tool_equal_to_manual_action(self):
        async with schema.get_connection() as db:
            await _insert_player(db, action="gathering", materials_gathering=5)
            with self.assertRaises(ValueError):
                await auto_tool_manager.start(db, USER, "gathering", 1, None, NOW)

    async def test_start_rejects_already_active_tool(self):
        async with schema.get_connection() as db:
            await _insert_player(db, materials_gathering=5)
            await auto_tool_manager.start(db, USER, "gathering", 1, None, NOW)
            await db.commit()
            with self.assertRaises(ValueError):
                await auto_tool_manager.start(db, USER, "gathering", 1, None, NOW)

    async def test_start_rejects_count_over_cap(self):
        async with schema.get_connection() as db:
            await _insert_player(db, materials_gathering=20)
            with self.assertRaises(ValueError):
                await auto_tool_manager.start(db, USER, "gathering", 7, None, NOW)

    async def test_start_building_requires_valid_target(self):
        async with schema.get_connection() as db:
            await _insert_player(db, materials_building=5)
            with self.assertRaises(ValueError):
                await auto_tool_manager.start(db, USER, "building", 1, "research_lab", NOW)
            await _insert_player(db, materials_building=5)
            await auto_tool_manager.start(db, USER, "building", 1, "workshop", NOW)
            await db.commit()
            row = await auto_tool_manager.get(db, USER, "building")
        self.assertEqual(row["action_target"], "workshop")

    async def test_start_research_targets_research_lab(self):
        async with schema.get_connection() as db:
            await _insert_player(db, materials_research=5)
            await auto_tool_manager.start(db, USER, "research", 1, None, NOW)
            await db.commit()
            row = await auto_tool_manager.get(db, USER, "research")
        self.assertEqual(row["action_target"], "research_lab")


class RefuelAutoTool(DatabaseTestCase):
    async def test_refuel_extends_and_spends_material(self):
        async with schema.get_connection() as db:
            await _insert_player(db, materials_gathering=10)
            await auto_tool_manager.start(db, USER, "gathering", 1, None, NOW)
            await db.commit()
        # 1h remaining -> max_add 5; refuel 2 at the same NOW
        async with schema.get_connection() as db:
            await auto_tool_manager.refuel(db, USER, "gathering", 2, NOW)
            await db.commit()
            row = await auto_tool_manager.get(db, USER, "gathering")
            gathering = await player_manager.get_material(db, USER, "gathering")
        self.assertEqual(row["expires_at"], dt_str(NOW + timedelta(hours=3)))
        self.assertEqual(gathering, 7)  # 10 - 1 (start) - 2 (refuel)

    async def test_refuel_rejected_when_remaining_over_5h(self):
        async with schema.get_connection() as db:
            await _insert_player(db, materials_gathering=10)
            await auto_tool_manager.start(db, USER, "gathering", 6, None, NOW)  # full 6h
            await db.commit()
            # remaining 6h -> max_add 0
            with self.assertRaises(ValueError):
                await auto_tool_manager.refuel(db, USER, "gathering", 1, NOW)

    async def test_refuel_capped_at_six_hours(self):
        async with schema.get_connection() as db:
            await _insert_player(db, materials_gathering=10)
            await auto_tool_manager.start(db, USER, "gathering", 1, None, NOW)
            await db.commit()
        # remaining 1h -> max_add 5; refuel 6 must be rejected (would exceed cap)
        async with schema.get_connection() as db:
            with self.assertRaises(ValueError):
                await auto_tool_manager.refuel(db, USER, "gathering", 6, NOW)
            await auto_tool_manager.refuel(db, USER, "gathering", 5, NOW)  # -> exactly 6h
            await db.commit()
            row = await auto_tool_manager.get(db, USER, "gathering")
        self.assertEqual(row["expires_at"], dt_str(NOW + timedelta(hours=6)))

    async def test_refuel_inactive_tool_raises(self):
        async with schema.get_connection() as db:
            await _insert_player(db, materials_gathering=5)
            with self.assertRaises(ValueError):
                await auto_tool_manager.refuel(db, USER, "gathering", 1, NOW)


class IdleAndLifecycle(DatabaseTestCase):
    async def test_get_idle_tools_excludes_manual_and_active(self):
        async with schema.get_connection() as db:
            await _insert_player(db, action="research", materials_gathering=5)
            await auto_tool_manager.start(db, USER, "gathering", 1, None, NOW)
            await db.commit()
            idle = await auto_tool_manager.get_idle_tools(db, USER)
        self.assertEqual(set(idle), {"building", "combat"})

    async def test_advance_cycle_sets_completion(self):
        async with schema.get_connection() as db:
            await _insert_player(db, materials_gathering=5)
            await auto_tool_manager.start(db, USER, "gathering", 2, None, NOW)
            await db.commit()
            nxt = NOW + timedelta(minutes=30)
            await auto_tool_manager.advance_cycle(db, USER, "gathering", NOW + timedelta(minutes=10), nxt)
            await db.commit()
            row = await auto_tool_manager.get(db, USER, "gathering")
        self.assertEqual(row["completion_time"], dt_str(nxt))

    async def test_end_deletes_row(self):
        async with schema.get_connection() as db:
            await _insert_player(db, materials_gathering=5)
            await auto_tool_manager.start(db, USER, "gathering", 1, None, NOW)
            await db.commit()
            await auto_tool_manager.end(db, USER, "gathering")
            await db.commit()
            row = await auto_tool_manager.get(db, USER, "gathering")
        self.assertIsNone(row)


class ChangeActionExclusion(DatabaseTestCase):
    async def test_change_action_rejects_active_auto_tool(self):
        async with schema.get_connection() as db:
            await _insert_player(db, materials_combat=5)
            await auto_tool_manager.start(db, USER, "combat", 1, None, NOW)
            await db.commit()
        with self.assertRaises(ValueError):
            await change_action(USER, "combat", None, NOW)
        # action must remain unset
        async with schema.get_connection() as db:
            async with db.execute("SELECT action FROM players WHERE user_id=?", (USER,)) as cur:
                row = await cur.fetchone()
        self.assertIsNone(row[0])


if __name__ == "__main__":
    unittest.main()

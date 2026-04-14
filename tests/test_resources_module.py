from datetime import datetime, timedelta
from unittest.mock import patch

from support import DatabaseTestCase
from database import schema
from core.engine import Engine


class ResourcesModuleBehaviorTests(DatabaseTestCase):
    async def test_init_db_does_not_rewrite_legacy_village_schema(self):
        async with schema.get_connection() as db:
            await db.execute("PRAGMA foreign_keys = OFF")
            await db.execute("DROP TABLE villages")
            await db.execute(
                """
                CREATE TABLE villages (
                    id INTEGER PRIMARY KEY,
                    food INTEGER DEFAULT 1000,
                    wood INTEGER DEFAULT 1000,
                    stone INTEGER DEFAULT 1000,
                    food_efficiency_xp INTEGER DEFAULT 0,
                    storage_capacity_xp INTEGER DEFAULT 0,
                    resource_yield_xp INTEGER DEFAULT 0,
                    last_tick_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    announcement_channel_id TEXT,
                    announcement_message_id TEXT,
                    last_announcement_updated TIMESTAMP
                )
                """
            )
            await db.execute(
                """
                INSERT INTO villages (
                    id, food, wood, stone, food_efficiency_xp, storage_capacity_xp, resource_yield_xp
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (100, 10, 20, 30, 40, 50, 60),
            )
            await db.executemany(
                """
                INSERT INTO village_resources (village_id, resource_type, amount)
                VALUES (?, ?, ?)
                """,
                (
                    (100, "food", 700),
                    (100, "wood", 800),
                    (100, "stone", 900),
                ),
            )
            await db.executemany(
                """
                INSERT INTO buffs (village_id, buff_id, xp)
                VALUES (?, ?, ?)
                """,
                (
                    (100, 1, 111),
                    (100, 2, 222),
                    (100, 3, 333),
                ),
            )
            await db.commit()
            await db.execute("PRAGMA foreign_keys = ON")

        await schema.init_db()

        resources = await self.fetch_resources(100)
        buffs = await self.fetch_buffs(100)
        village_columns = await self.fetchall("PRAGMA table_info(villages)")

        self.assertEqual(resources, {"food": 700, "stone": 900, "wood": 800})
        self.assertEqual(buffs, {1: 111, 2: 222, 3: 333})
        self.assertIn("food", {column[1] for column in village_columns})

    async def test_init_db_does_not_merge_duplicate_resource_nodes(self):
        village_id = await self.create_village(wood=0)
        keeper_id = await self.create_resource_node(
            village_id,
            node_type="wood",
            quality=100,
            remaining_amount=100,
            expiry_time=datetime.utcnow() + timedelta(hours=4),
        )
        duplicate_id = await self.create_resource_node(
            village_id,
            node_type="wood",
            quality=150,
            remaining_amount=50,
            expiry_time=datetime.utcnow() + timedelta(hours=8),
        )
        player_discord_id = await self.create_player(
            village_id,
            status="gathering",
            target_id=duplicate_id,
            last_update_time=datetime.utcnow(),
            completion_time=datetime.utcnow() + timedelta(hours=1),
        )

        await schema.init_db()

        nodes = await self.fetchall(
            """
            SELECT id, type, quality, remaining_amount, expiry_time
            FROM resource_nodes
            WHERE village_id = ?
            ORDER BY id
            """,
            (village_id,),
        )
        player = await self.fetchone(
            "SELECT status, target_id FROM players WHERE discord_id = ? AND village_id = ?",
            (player_discord_id, village_id),
        )

        self.assertEqual(
            nodes,
            [
                (keeper_id, "wood", 100, 100, nodes[0][4]),
                (duplicate_id, "wood", 150, 50, nodes[1][4]),
            ],
        )
        self.assertEqual(player, ("gathering", duplicate_id))
        self.assertNotEqual(keeper_id, duplicate_id)

    async def test_init_db_does_not_normalize_resource_node_fields_on_restart(self):
        village_id = await self.create_village()
        node_id = await self.create_resource_node(
            village_id,
            node_type="stone",
            quality=100,
            remaining_amount=9001,
            expiry_time=datetime.utcnow() + timedelta(hours=12),
        )

        await schema.init_db()
        await schema.init_db()

        node = await self.fetchone(
            """
            SELECT type, quality, remaining_amount, expiry_time
            FROM resource_nodes
            WHERE id = ?
            """,
            (node_id,),
        )
        self.assertEqual(node[0], "stone")
        self.assertEqual(node[1], 100)
        self.assertEqual(node[2], 9001)
        self.assertIsNotNone(node[3])

    async def test_init_db_migrates_legacy_monsters_table_to_2026_04_13_schema(self):
        village_id = await self.create_village()

        async with schema.get_connection() as db:
            await db.execute("DROP TABLE monsters")
            await db.execute(
                """
                CREATE TABLE monsters (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    village_id INTEGER NOT NULL UNIQUE,
                    name TEXT NOT NULL,
                    reward_resource_type TEXT NOT NULL,
                    quality INTEGER NOT NULL,
                    hp INTEGER NOT NULL,
                    max_hp INTEGER NOT NULL,
                    expires_at TIMESTAMP NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (village_id) REFERENCES villages(id)
                )
                """
            )
            await db.execute(
                """
                INSERT INTO monsters (
                    village_id, name, reward_resource_type, quality, hp, max_hp, expires_at, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    village_id,
                    "Wild Boar",
                    "food",
                    125,
                    321,
                    999,
                    (datetime.utcnow() + timedelta(hours=48)).isoformat(),
                    datetime.utcnow().isoformat(),
                ),
            )
            await db.commit()

        await schema.init_db()

        monster_columns = await self.fetchall("PRAGMA table_info(monsters)")
        monster = await self.fetchone(
            """
            SELECT village_id, name, reward_resource_type, quality, hp, max_hp
            FROM monsters
            WHERE village_id = ?
            """,
            (village_id,),
        )

        self.assertNotIn("expires_at", {column[1] for column in monster_columns})
        self.assertEqual(monster, (village_id, "Wild Boar", "food", 125, 321, 999))

    async def test_init_db_leaves_2026_04_13_monsters_table_untouched_on_restart(self):
        village_id = await self.create_village()
        monster_id = await self.create_monster(
            village_id,
            name="Monsters",
            reward_resource_type="food",
            quality=140,
            hp=222,
            max_hp=2000,
        )

        await schema.init_db()
        await schema.init_db()

        monster_columns = await self.fetchall("PRAGMA table_info(monsters)")
        monster = await self.fetchone(
            """
            SELECT id, village_id, name, reward_resource_type, quality, hp, max_hp
            FROM monsters
            WHERE id = ?
            """,
            (monster_id,),
        )

        self.assertNotIn("expires_at", {column[1] for column in monster_columns})
        self.assertEqual(monster, (monster_id, village_id, "Monsters", "food", 140, 222, 2000))

    async def test_resources_idle_state_produces_food_without_food_cost(self):
        village_id = await self.create_village(food=0)
        now = datetime.utcnow()
        player_discord_id = await self.create_player(
            village_id,
            status="idle",
            last_update_time=now - timedelta(hours=2),
            completion_time=None,
        )

        async with schema.get_connection() as db:
            await Engine.settle_player(player_discord_id, village_id, db)

        resources = await self.fetch_resources(village_id)
        self.assertEqual(resources["food"], 25)

    async def test_resources_gathering_food_uses_node_quality_and_yield_bonus(self):
        village_id = await self.create_village(food=0, resource_yield_xp=1000)
        node_id = await self.create_resource_node(village_id, node_type="food", quality=150, remaining_amount=50)
        now = datetime.utcnow()
        player_discord_id = await self.create_player(
            village_id,
            status="gathering",
            target_id=node_id,
            last_update_time=now - timedelta(hours=1),
            completion_time=now,
        )

        async with schema.get_connection() as db:
            await Engine.settle_player(player_discord_id, village_id, db, interrupted=True)

        resources = await self.fetch_resources(village_id)
        node = await self.fetchone("SELECT remaining_amount FROM resource_nodes WHERE id = ?", (node_id,))
        self.assertEqual(resources["food"], 41)
        self.assertEqual(node[0], 9)

    async def test_buildings_resource_yield_bonus_does_not_modify_idle_output(self):
        village_id = await self.create_village(food=0, resource_yield_xp=1000)
        now = datetime.utcnow()
        player_discord_id = await self.create_player(
            village_id,
            status="idle",
            last_update_time=now - timedelta(hours=2),
        )

        async with schema.get_connection() as db:
            await Engine.settle_player(player_discord_id, village_id, db)

        resources = await self.fetch_resources(village_id)
        self.assertEqual(resources["food"], 25)

    async def test_resources_exploring_creates_a_node_from_successful_roll(self):
        village_id = await self.create_village(wood=0)
        now = datetime.utcnow()
        player_discord_id = await self.create_player(
            village_id,
            status="exploring",
            last_update_time=now - timedelta(hours=1),
            completion_time=now,
        )

        with patch("core.engine.random.random", side_effect=[0.0, 1.0]), patch("core.engine.random.choice", return_value="stone"), patch("core.engine.random.gauss", return_value=140), patch("core.engine.random.randint", return_value=28):
            async with schema.get_connection() as db:
                await Engine.settle_player(player_discord_id, village_id, db, interrupted=True)

        nodes = await self.fetchall(
            "SELECT type, quality, remaining_amount FROM resource_nodes WHERE village_id = ?",
            (village_id,),
        )
        self.assertEqual(nodes, [("stone", 140, 700)])

    async def test_resources_exploring_replenishes_existing_singleton_node_with_weighted_quality(self):
        village_id = await self.create_village()
        await self.create_resource_node(village_id, node_type="wood", quality=100, remaining_amount=100)
        now = datetime.utcnow()
        player_discord_id = await self.create_player(
            village_id,
            status="exploring",
            last_update_time=now - timedelta(hours=1),
            completion_time=now,
        )

        with patch("core.engine.random.random", side_effect=[0.0, 1.0]), patch("core.engine.random.choice", return_value="wood"), patch("core.engine.random.gauss", return_value=150), patch("core.engine.random.randint", return_value=20):
            async with schema.get_connection() as db:
                await Engine.settle_player(player_discord_id, village_id, db, interrupted=True)

        nodes = await self.fetchall(
            "SELECT type, quality, remaining_amount FROM resource_nodes WHERE village_id = ? ORDER BY id",
            (village_id,),
        )
        self.assertEqual(nodes, [("wood", 141, 600)])

    async def test_resources_exploring_caps_singleton_stock_but_still_updates_quality(self):
        village_id = await self.create_village()
        await self.create_resource_node(village_id, node_type="wood", quality=100, remaining_amount=1950)
        now = datetime.utcnow()
        player_discord_id = await self.create_player(
            village_id,
            status="exploring",
            last_update_time=now - timedelta(hours=1),
            completion_time=now,
        )

        with patch("core.engine.random.random", side_effect=[0.0, 1.0]), patch("core.engine.random.choice", return_value="wood"), patch("core.engine.random.gauss", return_value=400), patch("core.engine.random.randint", return_value=20):
            async with schema.get_connection() as db:
                await Engine.settle_player(player_discord_id, village_id, db, interrupted=True)

        node = await self.fetchone(
            "SELECT type, quality, remaining_amount FROM resource_nodes WHERE village_id = ?",
            (village_id,),
        )
        self.assertEqual(node, ("wood", 115, 2000))

    async def test_resources_gathering_clamps_quality_to_seventy_five_percent(self):
        village_id = await self.create_village(wood=0)
        node_id = await self.create_resource_node(village_id, node_type="wood", quality=20, remaining_amount=100)
        now = datetime.utcnow()
        player_discord_id = await self.create_player(
            village_id,
            status="gathering",
            target_id=node_id,
            last_update_time=now - timedelta(hours=1),
            completion_time=now,
        )

        async with schema.get_connection() as db:
            await Engine.settle_player(player_discord_id, village_id, db, interrupted=True)

        resources = await self.fetch_resources(village_id)
        self.assertEqual(resources["wood"], 18)

    async def test_resources_exploring_uses_stats_based_discovery_probability(self):
        village_id = await self.create_village()
        await self.create_resource_node(village_id, node_type="food")
        await self.create_resource_node(village_id, node_type="wood")
        now = datetime.utcnow()
        player_discord_id = await self.create_player(
            village_id,
            status="exploring",
            last_update_time=now - timedelta(hours=1),
            completion_time=now,
        )

        with patch("core.engine.random.random", return_value=0.8):
            async with schema.get_connection() as db:
                await Engine.settle_player(player_discord_id, village_id, db, interrupted=True)

        node_count = await self.fetchone("SELECT count(*) FROM resource_nodes WHERE village_id = ?", (village_id,))
        self.assertEqual(node_count[0], 2)

    async def test_resources_exploring_can_add_persistent_monster_hp_instead_of_resource_node(self):
        village_id = await self.create_village()
        now = datetime.utcnow()
        player_discord_id = await self.create_player(
            village_id,
            status="exploring",
            last_update_time=now - timedelta(hours=1),
            completion_time=now,
        )

        with patch("core.engine.random.random", return_value=0.0), patch("core.engine.random.choice", return_value="threat"), patch("core.engine.random.gauss", return_value=130), patch("core.engine.random.randint", return_value=20):
            async with schema.get_connection() as db:
                await Engine.settle_player(player_discord_id, village_id, db, interrupted=True)

        monster = await self.fetchone(
            "SELECT name, reward_resource_type, quality, hp, max_hp FROM monsters WHERE village_id = ?",
            (village_id,),
        )
        node_count = await self.fetchone("SELECT count(*) FROM resource_nodes WHERE village_id = ?", (village_id,))
        self.assertEqual(monster, ("Monsters", "food", 130, 50, 2000))
        self.assertEqual(node_count[0], 0)

    async def test_resources_attack_damage_grants_gold_and_random_base_resource_without_hunting_xp(self):
        village_id = await self.create_village(food=200, wood=0, stone=0, gold=0)
        now = datetime.utcnow()
        monster_id = await self.create_monster(
            village_id,
            name="Monsters",
            reward_resource_type="food",
            quality=100,
            hp=20,
            max_hp=20,
        )
        player_discord_id = await self.create_player(
            village_id,
            status="attack",
            target_id=monster_id,
            last_update_time=now - timedelta(hours=1),
            completion_time=now,
        )

        with patch("core.engine.random.choice", return_value="food"):
            async with schema.get_connection() as db:
                await Engine.settle_player(player_discord_id, village_id, db, interrupted=True)

        resources = await self.fetch_resources(village_id)
        buffs = await self.fetch_buffs(village_id)
        player = await self.fetchone(
            "SELECT status, target_id FROM players WHERE discord_id = ? AND village_id = ?",
            (player_discord_id, village_id),
        )
        monster = await self.fetchone("SELECT id FROM monsters WHERE village_id = ?", (village_id,))
        latest_log = await self.fetchone(
            """
            SELECT strength_delta, agility_delta, perception_delta, knowledge_delta, endurance_delta
            FROM player_actions_log
            WHERE player_discord_id = ? AND village_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (player_discord_id, village_id),
        )

        self.assertEqual(resources["food"], 220)
        self.assertEqual(resources["gold"], 20)
        self.assertEqual(buffs[4], 0)
        self.assertEqual(player, ("idle", None))
        self.assertIsNone(monster)
        self.assertEqual(latest_log, (1, 1, 0, 0, 0))

    async def test_completed_cycle_grants_matching_action_token(self):
        village_id = await self.create_village(food=200, wood=100, stone=100)
        now = datetime.utcnow()
        player_discord_id = await self.create_player(
            village_id,
            status="building",
            target_id=1,
            last_update_time=now - timedelta(hours=1),
            completion_time=now,
        )

        async with schema.get_connection() as db:
            await Engine.settle_player(player_discord_id, village_id, db)

        tokens = await self.fetch_tokens(player_discord_id, village_id)
        self.assertEqual(tokens["building"], 1)

    async def test_matching_player_buff_adds_total_one_hundred_stats_to_formula(self):
        village_id = await self.create_village(food=0)
        node_id = await self.create_resource_node(village_id, node_type="food", quality=100, remaining_amount=100)
        now = datetime.utcnow()
        player_discord_id = await self.create_player(
            village_id,
            status="gathering",
            target_id=node_id,
            last_update_time=now - timedelta(hours=1),
            completion_time=now,
        )

        async with schema.get_connection() as db:
            await db.execute(
                """
                INSERT INTO player_buffs (player_discord_id, village_id, buff_type, expires_at)
                VALUES (?, ?, ?, ?)
                """,
                (player_discord_id, village_id, "gathering", (now + timedelta(hours=1)).isoformat()),
            )
            await db.commit()
            await Engine.settle_player(player_discord_id, village_id, db, interrupted=True)

        resources = await self.fetch_resources(village_id)
        self.assertEqual(resources["food"], 50)

    async def test_idle_players_fallback_to_food_when_village_command_target_is_missing(self):
        village_id = await self.create_village(food=0)
        now = datetime.utcnow()
        player_discord_id = await self.create_player(
            village_id,
            status="idle",
            last_update_time=now - timedelta(hours=1),
            completion_time=None,
        )

        async with schema.get_connection() as db:
            await db.execute(
                "UPDATE villages SET active_command = ? WHERE id = ?",
                ("gathering_wood", village_id),
            )
            await db.commit()
            await Engine.settle_player(player_discord_id, village_id, db, interrupted=True)

        resources = await self.fetch_resources(village_id)
        self.assertEqual(resources["food"], 12)

    async def test_resources_storage_overflow_rule_preserves_overcap_stock(self):
        village_id = await self.create_village(food=1500)
        now = datetime.utcnow()
        player_discord_id = await self.create_player(
            village_id,
            status="idle",
            last_update_time=now - timedelta(hours=1),
            completion_time=now,
        )

        async with schema.get_connection() as db:
            await Engine.settle_player(player_discord_id, village_id, db, interrupted=True)

        resources = await self.fetch_resources(village_id)
        self.assertEqual(resources["food"], 1500)

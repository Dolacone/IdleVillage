from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from support import DatabaseTestCase
from cogs.actions import ActionsCog, _build_embed
from cogs.events import EventsCog
from cogs.general import (
    General,
    ManageView,
    NodeSelect,
    RemoveNodeButton,
    ResourceAmountModal,
    SetCustomButton,
    _adjust_village_resource,
    _remove_village_node,
)
from database import schema
from core.config import get_primary_admin_id
from core.engine import Engine

ADMIN_ID = get_primary_admin_id()


class _FakeResponse:
    def __init__(self):
        self.calls = []

    async def send_message(self, content, ephemeral=False, **kwargs):
        self.calls.append({"content": content, "ephemeral": ephemeral, **kwargs})

    async def edit_message(self, content=None, **kwargs):
        self.calls.append({"content": content, **kwargs})

    async def send_modal(self, modal):
        self.calls.append({"modal": modal})


class _FakeMessage:
    _next_id = 1

    def __init__(self, content):
        self.id = _FakeMessage._next_id
        _FakeMessage._next_id += 1
        self.content = content

    async def edit(self, *, content):
        self.content = content


class _FakeChannel:
    def __init__(self):
        self.id = 456
        self.mention = "#village-board"
        self.messages = {}

    async def send(self, content):
        message = _FakeMessage(content)
        self.messages[message.id] = message
        return message

    async def fetch_message(self, message_id):
        return self.messages[message_id]


class _FakeGuild:
    def __init__(self, guild_id):
        self.id = guild_id
        self.name = f"Village {guild_id}"

    def get_member(self, member_id):
        return SimpleNamespace(display_name=f"User {member_id}")


class _FakeBot(SimpleNamespace):
    def __init__(self, *, channel=None):
        super().__init__(latency=0)
        self._channel = channel or _FakeChannel()
        self._guilds = {}

    def get_channel(self, channel_id):
        if int(channel_id) == self._channel.id:
            return self._channel
        return None

    def get_guild(self, guild_id):
        return self._guilds.get(int(guild_id))

    def register_guild(self, guild_id):
        guild = _FakeGuild(guild_id)
        self._guilds[int(guild_id)] = guild
        return guild


class PlayerSystemAndCommandsBehaviorTests(DatabaseTestCase):
    async def test_player_system_same_discord_user_can_exist_in_multiple_guilds(self):
        first_village_id = await self.create_village(guild_id=41)
        second_village_id = await self.create_village(guild_id=42)

        await self.create_player(first_village_id, discord_id=555, status="idle")
        await self.create_player(second_village_id, discord_id=555, status="building", target_id=1)

        players = await self.fetchall(
            """
            SELECT discord_id, village_id, status, target_id
            FROM players
            WHERE discord_id = ?
            ORDER BY village_id
            """,
            (555,),
        )

        self.assertEqual(
            players,
            [
                (555, 41, "idle", None),
                (555, 42, "building", 1),
            ],
        )

    async def test_player_system_message_activity_updates_last_message_time(self):
        village_id = await self.create_village(guild_id=42)
        player_discord_id = await self.create_player(
            village_id,
            discord_id=123,
            last_message_time="2000-01-01T00:00:00",
            last_command_time="2001-01-01T00:00:00",
        )
        cog = EventsCog(bot=None)
        message = SimpleNamespace(
            author=SimpleNamespace(bot=False, id=123),
            guild=SimpleNamespace(id=42),
        )

        await cog.on_message(message)

        player = await self.fetchone(
            "SELECT last_message_time, last_command_time FROM players WHERE discord_id = ? AND village_id = ?",
            (player_discord_id, village_id),
        )
        self.assertNotEqual(player[0], "2000-01-01T00:00:00")
        self.assertEqual(player[1], "2001-01-01T00:00:00")

    async def test_idlevillage_command_updates_last_command_time_only(self):
        village_id = await self.create_village(guild_id=42)
        player_discord_id = await self.create_player(
            village_id,
            discord_id=123,
            last_message_time="2000-01-01T00:00:00",
            last_command_time="2001-01-01T00:00:00",
        )
        bot = _FakeBot()
        bot.register_guild(42)
        cog = ActionsCog(bot=bot)
        inter = SimpleNamespace(
            author=SimpleNamespace(id=123),
            guild=SimpleNamespace(id=42, name="Village 42"),
            response=_FakeResponse(),
            bot=bot,
        )

        await cog.idlevillage.callback(cog, inter)

        player = await self.fetchone(
            "SELECT last_message_time, last_command_time FROM players WHERE discord_id = ? AND village_id = ?",
            (player_discord_id, village_id),
        )
        self.assertEqual(player[0], "2000-01-01T00:00:00")
        self.assertNotEqual(player[1], "2001-01-01T00:00:00")

    async def test_village_binding_owner_can_initialize_once(self):
        cog = General(bot=_FakeBot())
        inter = SimpleNamespace(
            author=SimpleNamespace(id=ADMIN_ID),
            guild=SimpleNamespace(id=77),
            response=_FakeResponse(),
        )

        await cog.idlevillage_initial.callback(cog, inter)

        resources = await self.fetch_resources(77)
        buffs = await self.fetch_buffs(77)
        self.assertEqual(resources, {"food": 1000, "gold": 0, "stone": 1000, "wood": 1000})
        self.assertEqual(buffs, {1: 0, 2: 0, 3: 0, 4: 0})
        self.assertEqual(inter.response.calls[-1]["ephemeral"], True)

    async def test_village_binding_rejects_reuse_on_existing_server(self):
        await self.create_village(guild_id=88)
        cog = General(bot=_FakeBot())
        inter = SimpleNamespace(
            author=SimpleNamespace(id=ADMIN_ID),
            guild=SimpleNamespace(id=88),
            response=_FakeResponse(),
        )

        await cog.idlevillage_initial.callback(cog, inter)

        self.assertIn("already exists", inter.response.calls[-1]["content"])
        self.assertEqual(inter.response.calls[-1]["ephemeral"], True)

    async def test_village_binding_rejects_non_owner(self):
        cog = General(bot=_FakeBot())
        inter = SimpleNamespace(
            author=SimpleNamespace(id=1),
            guild=SimpleNamespace(id=99),
            response=_FakeResponse(),
        )

        await cog.idlevillage_initial.callback(cog, inter)

        village = await self.fetchone("SELECT id FROM villages WHERE id = ?", (99,))
        self.assertIsNone(village)
        self.assertIn("do not have permission", inter.response.calls[-1]["content"])

    async def test_announcement_command_stores_channel_and_message_id(self):
        await self.create_village(guild_id=77)
        bot = _FakeBot()
        bot.register_guild(77)
        cog = General(bot=bot)
        inter = SimpleNamespace(
            author=SimpleNamespace(id=ADMIN_ID),
            guild=SimpleNamespace(id=77),
            channel=bot.get_channel(456),
            response=_FakeResponse(),
            bot=bot,
        )

        await cog.idlevillage_announcement.callback(cog, inter)

        village = await self.fetchone(
            """
            SELECT announcement_channel_id, announcement_message_id
            FROM villages
            WHERE id = ?
            """,
            (77,),
        )
        self.assertEqual(village[0], "456")
        self.assertIsNotNone(village[1])
        self.assertEqual(inter.response.calls[-1]["ephemeral"], True)

    async def test_exploring_discovery_does_not_post_to_announcement_channel(self):
        village_id = await self.create_village(guild_id=55)
        now = datetime.utcnow()
        player_discord_id = await self.create_player(
            village_id,
            discord_id=123,
            status="exploring",
            last_update_time=now - timedelta(hours=1),
            completion_time=now,
        )
        bot = _FakeBot()
        bot.register_guild(55)
        Engine.bot = bot

        async with schema.get_connection() as db:
            await db.execute(
                """
                UPDATE villages
                SET announcement_channel_id = ?, announcement_message_id = ?, last_announcement_updated = ?
                WHERE id = ?
                """,
                ("456", "999", now.isoformat(), village_id),
            )
            await db.commit()

        with patch("core.engine.random.random", side_effect=[0.0, 1.0]), patch("core.engine.random.choice", return_value="wood"), patch("core.engine.random.gauss", return_value=130), patch("core.engine.random.randint", return_value=2100):
            async with schema.get_connection() as db:
                await Engine.settle_player(player_discord_id, village_id, db, interrupted=True)

        channel = bot.get_channel(456)
        self.assertEqual(len(channel.messages), 0)

    async def test_idlevillage_embed_uses_localized_building_names_and_compact_status_line(self):
        village_id = await self.create_village(guild_id=66, food_efficiency_xp=1500)
        now = datetime.utcnow()
        player_discord_id = await self.create_player(
            village_id,
            discord_id=321,
            status="building",
            target_id=1,
            last_update_time=now - timedelta(minutes=10),
            completion_time=now + timedelta(minutes=50),
        )

        async with schema.get_connection() as db:
            embed = await _build_embed(
                SimpleNamespace(guild=SimpleNamespace(name="Village 66")),
                db,
                village_id,
                player_discord_id,
            )

        village_buildings_field = next(field for field in embed.fields if field.name == "Village Buildings")
        player_status_field = next(field for field in embed.fields if field.name == "Player Status")

        self.assertIn("廚房", village_buildings_field.value)
        self.assertIn("倉庫", village_buildings_field.value)
        self.assertIn("加工", village_buildings_field.value)
        self.assertIn("廚房: Lv.1 [XP: 500 / 2,000]", village_buildings_field.value)
        self.assertIn("Status: Building 廚房 (Last activity:", player_status_field.value)
        self.assertIn("Next check:", player_status_field.value)

    async def test_idlevillage_embed_uses_utc_timestamp_for_discord_rendering(self):
        village_id = await self.create_village(guild_id=67)
        last_update = datetime(2026, 4, 8, 0, 15, 0)
        completion_time = datetime(2026, 4, 8, 1, 15, 0)
        player_discord_id = await self.create_player(
            village_id,
            discord_id=322,
            status="building",
            target_id=1,
            last_update_time=last_update,
            completion_time=completion_time,
        )

        async with schema.get_connection() as db:
            embed = await _build_embed(
                SimpleNamespace(guild=SimpleNamespace(name="Village 67")),
                db,
                village_id,
                player_discord_id,
            )

        player_status_field = next(field for field in embed.fields if field.name == "Player Status")
        self.assertIn(f"<t:{Engine._to_discord_unix(last_update)}:t>", player_status_field.value)
        self.assertIn(f"<t:{Engine._to_discord_unix(completion_time)}:R>", player_status_field.value)

    async def test_idlevillage_embed_shows_next_cycle_for_idle_players(self):
        village_id = await self.create_village(guild_id=68)
        last_update = datetime(2026, 4, 8, 0, 15, 0)
        player_discord_id = await self.create_player(
            village_id,
            discord_id=323,
            status="idle",
            last_update_time=last_update,
            completion_time=None,
        )

        async with schema.get_connection() as db:
            embed = await _build_embed(
                SimpleNamespace(guild=SimpleNamespace(name="Village 68")),
                db,
                village_id,
                player_discord_id,
            )

        player_status_field = next(field for field in embed.fields if field.name == "Player Status")
        expected_next_check = Engine._next_idle_completion(last_update)
        self.assertIn(f"<t:{Engine._to_discord_unix(expected_next_check)}:R>", player_status_field.value)
        self.assertNotIn("Manual refresh", player_status_field.value)

    async def test_village_announcement_uses_mixed_rich_text_and_villager_code_block(self):
        village_id = await self.create_village(
            guild_id=88,
            food=1234,
            wood=5678,
            stone=90,
            food_efficiency_xp=1500,
            storage_capacity_xp=1000,
        )
        node_id = await self.create_resource_node(village_id, node_type="wood", quality=100, remaining_amount=200)
        fixed_render_time = datetime(2026, 4, 8, 0, 15, 0)
        for discord_id, status, target_id in (
            (999, "idle", None),
            (1001, "idle", None),
            (1002, "building", 1),
            (1003, "gathering", node_id),
        ):
            await self.create_player(village_id, discord_id=discord_id, status=status, target_id=target_id)
        bot = _FakeBot()
        bot.register_guild(88)
        Engine.bot = bot

        async with schema.get_connection() as db:
            announcement = await Engine.render_announcement(village_id, db=db, bot=bot, rendered_at=fixed_render_time)

        self.assertTrue(announcement.startswith(f"(Last Update: <t:{Engine._to_discord_unix(fixed_render_time)}:R>)"))
        self.assertIn("Village Resources (Cap: 2,000)", announcement)
        self.assertIn("🍎 1,234 | 🪵 5,678 | 🪨 90 | 💰 0", announcement)
        self.assertIn("Village Buildings", announcement)
        self.assertIn("廚房: Lv.1 [XP: 500 / 2,000]", announcement)
        self.assertIn("Active Villagers", announcement)
        self.assertIn("Idle: 2", announcement)
        self.assertIn("Building 廚房: 1", announcement)
        self.assertIn("Gathering Wood: 1", announcement)
        self.assertGreaterEqual(announcement.count("```text"), 2)
        self.assertNotIn("STR", announcement)
        self.assertNotIn("AGI", announcement)
        self.assertNotIn("**", announcement)

    async def test_manage_command_returns_interactive_view(self):
        await self.create_village(guild_id=90, food=5, wood=6, stone=7)
        bot = _FakeBot()
        bot.register_guild(90)
        cog = General(bot=bot)
        inter = SimpleNamespace(
            author=SimpleNamespace(id=ADMIN_ID),
            guild=SimpleNamespace(id=90),
            response=_FakeResponse(),
            bot=bot,
        )

        await cog.idlevillage_manage.callback(cog, inter)

        self.assertTrue(inter.response.calls[-1]["ephemeral"])
        self.assertIsInstance(inter.response.calls[-1]["view"], ManageView)
        self.assertEqual(inter.response.calls[-1]["embed"].title, "Idle Village Admin - Village 90")

    async def test_manage_helpers_can_adjust_resources_and_remove_nodes(self):
        await self.create_village(guild_id=90, food=5, wood=6, stone=7)
        village_id = await self.create_village(guild_id=91)
        node_id = await self.create_resource_node(village_id, node_type="stone", remaining_amount=25)
        new_amount = await _adjust_village_resource(90, "wood", 4315)
        removed_type = await _remove_village_node(village_id, node_id)

        resources = await self.fetch_resources(90)
        node = await self.fetchone("SELECT id FROM resource_nodes WHERE id = ?", (node_id,))
        self.assertEqual(new_amount, 4321)
        self.assertEqual(resources, {"food": 5, "gold": 0, "stone": 7, "wood": 4321})
        self.assertEqual(removed_type, "stone")
        self.assertIsNone(node)

    async def test_manage_set_custom_modal_updates_resource_and_refreshes_announcement(self):
        village_id = await self.create_village(guild_id=94, food=5, wood=6, stone=7)
        bot = _FakeBot()
        bot.register_guild(94)
        Engine.bot = bot

        async with schema.get_connection() as db:
            await db.execute(
                """
                UPDATE villages
                SET announcement_channel_id = ?
                WHERE id = ?
                """,
                ("456", village_id),
            )
            await db.commit()

        view = await ManageView(village_id, bot, "REQ-MODAL").refresh_state()
        set_custom_button = next(item for item in view.children if isinstance(item, SetCustomButton))
        button_inter = SimpleNamespace(
            author=SimpleNamespace(id=ADMIN_ID),
            response=_FakeResponse(),
        )

        await set_custom_button.callback(button_inter)

        modal = button_inter.response.calls[-1]["modal"]
        self.assertIsInstance(modal, ResourceAmountModal)

        modal_inter = SimpleNamespace(
            author=SimpleNamespace(id=ADMIN_ID),
            text_values={"amount": "4321"},
            response=_FakeResponse(),
        )

        await modal.callback(modal_inter)

        resources = await self.fetch_resources(village_id)
        board_message = next(iter(bot.get_channel(456).messages.values()))

        self.assertEqual(resources, {"food": 4321, "gold": 0, "stone": 7, "wood": 6})
        self.assertIn("Food set to 4,321.", modal_inter.response.calls[-1]["content"])
        self.assertIn("🍎 4,321", board_message.content)

    async def test_manage_remove_node_callback_removes_node_and_refreshes_announcement(self):
        village_id = await self.create_village(guild_id=95)
        node_id = await self.create_resource_node(village_id, node_type="stone", remaining_amount=25)
        bot = _FakeBot()
        bot.register_guild(95)
        Engine.bot = bot

        async with schema.get_connection() as db:
            await db.execute(
                """
                UPDATE villages
                SET announcement_channel_id = ?
                WHERE id = ?
                """,
                ("456", village_id),
            )
            await db.commit()

        view = await ManageView(village_id, bot, "REQ-NODE").refresh_state()
        view.mode = "nodes"
        await view.refresh_state()
        node_select = next(item for item in view.children if isinstance(item, NodeSelect))
        remove_button = next(item for item in view.children if isinstance(item, RemoveNodeButton))
        self.assertEqual(view.selected_node_id, node_id)
        self.assertEqual(node_select.options[0].value, f"node:{node_id}")

        remove_inter = SimpleNamespace(
            author=SimpleNamespace(id=ADMIN_ID),
            response=_FakeResponse(),
        )

        await remove_button.callback(remove_inter)

        node = await self.fetchone("SELECT id FROM resource_nodes WHERE id = ?", (node_id,))
        village = await self.fetchone(
            "SELECT announcement_message_id, last_announcement_updated FROM villages WHERE id = ?",
            (village_id,),
        )
        board_message = next(iter(bot.get_channel(456).messages.values()))

        self.assertIsNone(node)
        self.assertIsNotNone(village[0])
        self.assertIsNotNone(village[1])
        self.assertIn(f"Removed stone #{node_id}.", remove_inter.response.calls[-1]["content"])
        self.assertIn("Village Resources", board_message.content)

    async def test_settle_player_posts_idle_and_node_expiry_notifications(self):
        village_id = await self.create_village(guild_id=92)
        node_id = await self.create_resource_node(village_id, node_type="food", quality=100, remaining_amount=20)
        now = datetime.utcnow()
        player_discord_id = await self.create_player(
            village_id,
            discord_id=987,
            status="gathering",
            target_id=node_id,
            last_update_time=now - timedelta(hours=1),
            completion_time=now,
        )
        bot = _FakeBot()
        bot.register_guild(92)
        Engine.bot = bot

        async with schema.get_connection() as db:
            await db.execute(
                """
                UPDATE villages
                SET announcement_channel_id = ?
                WHERE id = ?
                """,
                ("456", village_id),
            )
            await db.commit()
            await Engine.settle_player(player_discord_id, village_id, db)

        messages = [message.content for message in bot.get_channel(456).messages.values()]
        event_messages = [message for message in messages if "Village Resources" not in message]
        node = await self.fetchone("SELECT remaining_amount FROM resource_nodes WHERE id = ?", (node_id,))
        self.assertEqual(len(event_messages), 2)
        self.assertTrue(any("out of stock" in message for message in event_messages))
        self.assertTrue(any("<@987>" in message and "now idle" in message for message in event_messages))
        self.assertEqual(node[0], 0)

    async def test_building_level_up_posts_upgrade_announcement(self):
        village_id = await self.create_village(guild_id=93, food_efficiency_xp=990)
        now = datetime.utcnow()
        player_discord_id = await self.create_player(
            village_id,
            discord_id=654,
            status="building",
            target_id=1,
            last_update_time=now - timedelta(hours=1),
            completion_time=now,
        )
        bot = _FakeBot()
        bot.register_guild(93)
        Engine.bot = bot

        async with schema.get_connection() as db:
            await db.execute(
                """
                UPDATE villages
                SET announcement_channel_id = ?
                WHERE id = ?
                """,
                ("456", village_id),
            )
            await db.commit()
            await Engine.settle_player(player_discord_id, village_id, db)

        messages = [message.content for message in bot.get_channel(456).messages.values()]
        self.assertTrue(any("廚房" in message and "Level 1" in message for message in messages))

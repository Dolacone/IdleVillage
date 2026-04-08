from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from cogs.actions import _build_embed
from support import DatabaseTestCase
from cogs.events import EventsCog
from cogs.general import ALLOWED_OWNER_ID, General
from core.engine import Engine


class _FakeResponse:
    def __init__(self):
        self.calls = []

    async def send_message(self, content, ephemeral=False, **kwargs):
        self.calls.append({"content": content, "ephemeral": ephemeral, **kwargs})


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
    async def test_player_system_message_activity_updates_last_message_time(self):
        village_id = await self.create_village(guild_id="guild-42")
        player_id = await self.create_player(village_id, discord_id="123", last_message_time="2000-01-01T00:00:00")
        cog = EventsCog(bot=None)
        message = SimpleNamespace(
            author=SimpleNamespace(bot=False, id=123),
            guild=SimpleNamespace(id="guild-42"),
        )

        await cog.on_message(message)

        player = await self.fetchone("SELECT last_message_time FROM players WHERE id = ?", (player_id,))
        self.assertNotEqual(player[0], "2000-01-01T00:00:00")

    async def test_village_binding_owner_can_initialize_once(self):
        cog = General(bot=_FakeBot())
        inter = SimpleNamespace(
            author=SimpleNamespace(id=ALLOWED_OWNER_ID),
            guild=SimpleNamespace(id="guild-77"),
            response=_FakeResponse(),
        )

        await cog.idlevillage_initial.callback(cog, inter)

        village = await self.fetchone("SELECT food, wood, stone FROM villages WHERE guild_id = ?", ("guild-77",))
        self.assertEqual(village, (100, 0, 0))
        self.assertEqual(inter.response.calls[-1]["ephemeral"], True)

    async def test_village_binding_rejects_reuse_on_existing_server(self):
        await self.create_village(guild_id="guild-88")
        cog = General(bot=_FakeBot())
        inter = SimpleNamespace(
            author=SimpleNamespace(id=ALLOWED_OWNER_ID),
            guild=SimpleNamespace(id="guild-88"),
            response=_FakeResponse(),
        )

        await cog.idlevillage_initial.callback(cog, inter)

        self.assertIn("already exists", inter.response.calls[-1]["content"])
        self.assertEqual(inter.response.calls[-1]["ephemeral"], True)

    async def test_village_binding_rejects_non_owner(self):
        cog = General(bot=_FakeBot())
        inter = SimpleNamespace(
            author=SimpleNamespace(id=1),
            guild=SimpleNamespace(id="guild-99"),
            response=_FakeResponse(),
        )

        await cog.idlevillage_initial.callback(cog, inter)

        village = await self.fetchone("SELECT id FROM villages WHERE guild_id = ?", ("guild-99",))
        self.assertIsNone(village)
        self.assertIn("do not have permission", inter.response.calls[-1]["content"])

    async def test_announcement_command_stores_channel_and_message_id(self):
        await self.create_village(guild_id="77")
        bot = _FakeBot()
        bot.register_guild(77)
        cog = General(bot=bot)
        inter = SimpleNamespace(
            author=SimpleNamespace(id=ALLOWED_OWNER_ID),
            guild=SimpleNamespace(id="77"),
            channel=bot.get_channel(456),
            response=_FakeResponse(),
            bot=bot,
        )

        await cog.idlevillage_announcement.callback(cog, inter)

        village = await self.fetchone(
            """
            SELECT announcement_channel_id, announcement_message_id
            FROM villages
            WHERE guild_id = ?
            """,
            ("77",),
        )
        self.assertEqual(village[0], "456")
        self.assertIsNotNone(village[1])
        self.assertEqual(inter.response.calls[-1]["ephemeral"], True)

    async def test_exploring_discovery_posts_to_announcement_channel(self):
        village_id = await self.create_village(guild_id="55")
        now = datetime.utcnow()
        player_id = await self.create_player(
            village_id,
            discord_id="123",
            status="exploring",
            last_update_time=now - timedelta(hours=1),
            completion_time=now,
        )
        bot = _FakeBot()
        bot.register_guild(55)
        Engine.bot = bot

        async with __import__("database.schema", fromlist=["schema"]).get_connection() as db:
            await db.execute(
                """
                UPDATE villages
                SET announcement_channel_id = ?, announcement_message_id = ?, last_announcement_updated = ?
                WHERE id = ?
                """,
                ("456", "999", now.isoformat(), village_id),
            )
            await db.commit()

        with patch("core.engine.random.random", return_value=0.0), patch("core.engine.random.choice", return_value="wood"), patch("core.engine.random.gauss", return_value=130), patch("core.engine.random.randint", return_value=2100):
            async with __import__("database.schema", fromlist=["schema"]).get_connection() as db:
                await Engine.settle_player(player_id, db, interrupted=True)

        channel = bot.get_channel(456)
        self.assertEqual(len(channel.messages), 1)
        only_message = next(iter(channel.messages.values()))
        self.assertIn("New discovery", only_message.content)
        self.assertIn("User 123", only_message.content)
        self.assertIn("Quality 130%", only_message.content)
        self.assertNotIn("Lv", only_message.content)

    async def test_idlevillage_embed_uses_localized_building_names_and_compact_status_line(self):
        village_id = await self.create_village(guild_id="66")
        now = datetime.utcnow()
        player_id = await self.create_player(
            village_id,
            discord_id="321",
            status="building",
            target_id=1,
            last_update_time=now - timedelta(minutes=10),
            completion_time=now + timedelta(minutes=50),
        )

        async with __import__("database.schema", fromlist=["schema"]).get_connection() as db:
            embed = await _build_embed(
                SimpleNamespace(guild=SimpleNamespace(name="Village 66")),
                db,
                village_id,
                player_id,
            )

        village_buildings_field = next(field for field in embed.fields if field.name == "Village Buildings")
        player_status_field = next(field for field in embed.fields if field.name == "Player Status")

        self.assertIn("廚房", village_buildings_field.value)
        self.assertIn("倉庫", village_buildings_field.value)
        self.assertIn("加工", village_buildings_field.value)
        self.assertIn("1,000", village_buildings_field.value)
        self.assertIn("Status: Building 廚房 (Last activity:", player_status_field.value)
        self.assertIn("Next check:", player_status_field.value)

    async def test_idlevillage_embed_uses_utc_timestamp_for_discord_rendering(self):
        village_id = await self.create_village(guild_id="67")
        last_update = datetime(2026, 4, 8, 0, 15, 0)
        completion_time = datetime(2026, 4, 8, 1, 15, 0)
        player_id = await self.create_player(
            village_id,
            discord_id="322",
            status="building",
            target_id=1,
            last_update_time=last_update,
            completion_time=completion_time,
        )

        async with __import__("database.schema", fromlist=["schema"]).get_connection() as db:
            embed = await _build_embed(
                SimpleNamespace(guild=SimpleNamespace(name="Village 67")),
                db,
                village_id,
                player_id,
            )

        player_status_field = next(field for field in embed.fields if field.name == "Player Status")
        self.assertIn(f"<t:{Engine._to_discord_unix(last_update)}:t>", player_status_field.value)
        self.assertIn(f"<t:{Engine._to_discord_unix(completion_time)}:R>", player_status_field.value)

    async def test_village_announcement_uses_human_readable_names_without_emojis(self):
        village_id = await self.create_village(guild_id="88")
        player_id = await self.create_player(village_id, discord_id="999", status="idle")
        bot = _FakeBot()
        bot.register_guild(88)
        Engine.bot = bot

        async with __import__("database.schema", fromlist=["schema"]).get_connection() as db:
            await db.execute("INSERT INTO player_stats (player_id) VALUES (?)", (player_id,))
            await db.commit()
            announcement = await Engine.render_announcement(village_id, db=db, bot=bot)

        self.assertIn("=== [ Village 88 ] STATUS REPORT ===", announcement)
        self.assertIn("Resources: 食物", announcement)
        self.assertIn("Buildings: 廚房", announcement)
        self.assertIn("User 999", announcement)
        self.assertNotIn("🍎", announcement)
        self.assertNotIn("🌾", announcement)

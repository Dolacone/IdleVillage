from types import SimpleNamespace

from support import DatabaseTestCase
from cogs.events import EventsCog
from cogs.general import ALLOWED_OWNER_ID, General


class _FakeResponse:
    def __init__(self):
        self.calls = []

    async def send_message(self, content, ephemeral=False, **kwargs):
        self.calls.append({"content": content, "ephemeral": ephemeral, **kwargs})


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
        cog = General(bot=SimpleNamespace(latency=0))
        inter = SimpleNamespace(
            author=SimpleNamespace(id=ALLOWED_OWNER_ID),
            guild=SimpleNamespace(id="guild-77"),
            response=_FakeResponse(),
        )

        await cog.idlevillage_initial.callback(cog, inter)

        village = await self.fetchone("SELECT food, wood, stone FROM villages WHERE guild_id = ?", ("guild-77",))
        self.assertEqual(village, (0, 0, 0))
        self.assertEqual(inter.response.calls[-1]["ephemeral"], True)

    async def test_village_binding_rejects_reuse_on_existing_server(self):
        await self.create_village(guild_id="guild-88")
        cog = General(bot=SimpleNamespace(latency=0))
        inter = SimpleNamespace(
            author=SimpleNamespace(id=ALLOWED_OWNER_ID),
            guild=SimpleNamespace(id="guild-88"),
            response=_FakeResponse(),
        )

        await cog.idlevillage_initial.callback(cog, inter)

        self.assertIn("already exists", inter.response.calls[-1]["content"])
        self.assertEqual(inter.response.calls[-1]["ephemeral"], True)

    async def test_village_binding_rejects_non_owner(self):
        cog = General(bot=SimpleNamespace(latency=0))
        inter = SimpleNamespace(
            author=SimpleNamespace(id=1),
            guild=SimpleNamespace(id="guild-99"),
            response=_FakeResponse(),
        )

        await cog.idlevillage_initial.callback(cog, inter)

        village = await self.fetchone("SELECT id FROM villages WHERE guild_id = ?", ("guild-99",))
        self.assertIsNone(village)
        self.assertIn("do not have permission", inter.response.calls[-1]["content"])

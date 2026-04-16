from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

from support import DatabaseTestCase
from cogs.actions import ActionsCog, TokenView
from core.engine import Engine
from database import schema


class _FakeResponse:
    def __init__(self):
        self.calls = []

    async def send_message(self, content, ephemeral=False, **kwargs):
        self.calls.append({"content": content, "ephemeral": ephemeral, **kwargs})

    async def edit_message(self, content=None, **kwargs):
        self.calls.append({"content": content, **kwargs})


class _FakeGuild:
    def __init__(self, guild_id):
        self.id = guild_id
        self.name = f"Village {guild_id}"

    def get_member(self, member_id):
        return SimpleNamespace(display_name=f"User {member_id}")


class _FakeBot(SimpleNamespace):
    def __init__(self):
        super().__init__(latency=0)
        self._guilds = {}

    def get_channel(self, channel_id):
        return None

    def get_guild(self, guild_id):
        return self._guilds.get(int(guild_id))

    def register_guild(self, guild_id):
        guild = _FakeGuild(guild_id)
        self._guilds[int(guild_id)] = guild
        return guild


class FrozenDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        frozen = cls(2026, 4, 16, 12, 0, 0)
        if tz is not None:
            return frozen.replace(tzinfo=tz)
        return frozen


class TokenMultiTriggerTests(DatabaseTestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.village_id = await self.create_village(guild_id=71)
        self.player_id = await self.create_player(self.village_id, discord_id=123)

    async def _grant_tokens(self, token_type: str, amount: int):
        async with schema.get_connection() as db:
            await db.execute(
                "INSERT INTO tokens (player_discord_id, village_id, token_type, amount) VALUES (?, ?, ?, ?)",
                (self.player_id, self.village_id, token_type, amount),
            )
            await db.commit()

    async def test_player_buff_quantity_extends_same_type_from_existing_expiration(self):
        await self._grant_tokens("gathering", 8)
        existing_expiration = datetime(2026, 4, 16, 15, 0, 0)

        async with schema.get_connection() as db:
            await Engine._set_player_buff(db, self.player_id, self.village_id, "gathering", existing_expiration)
            await db.commit()
            success, expires_at = await Engine.use_player_buff_token(
                db,
                self.player_id,
                self.village_id,
                "gathering",
                quantity=5,
            )
            await db.commit()

        tokens = await self.fetch_tokens(self.player_id, self.village_id)
        self.assertTrue(success)
        self.assertEqual(expires_at, existing_expiration + timedelta(hours=15))
        self.assertEqual(tokens["gathering"], 3)

    async def test_player_buff_quantity_replaces_different_type_from_now(self):
        await self._grant_tokens("building", 4)
        old_expiration = datetime(2026, 4, 16, 18, 0, 0)

        async with schema.get_connection() as db:
            await Engine._set_player_buff(db, self.player_id, self.village_id, "gathering", old_expiration)
            await db.commit()
            with patch("core.engine.datetime", FrozenDateTime):
                success, expires_at = await Engine.use_player_buff_token(
                    db,
                    self.player_id,
                    self.village_id,
                    "building",
                    quantity=3,
                )
            await db.commit()

        buff_row = await self.fetchone(
            "SELECT buff_type, expires_at FROM player_buffs WHERE player_discord_id = ? AND village_id = ?",
            (self.player_id, self.village_id),
        )
        tokens = await self.fetch_tokens(self.player_id, self.village_id)
        self.assertTrue(success)
        self.assertEqual(buff_row[0], "building")
        self.assertEqual(datetime.fromisoformat(buff_row[1]), datetime(2026, 4, 16, 21, 0, 0))
        self.assertEqual(expires_at, datetime(2026, 4, 16, 21, 0, 0))
        self.assertEqual(tokens["building"], 1)

    async def test_village_protection_quantity_extends_from_existing_expiration(self):
        await self._grant_tokens("exploring", 5)
        existing_expiration = datetime(2026, 4, 16, 13, 0, 0)

        async with schema.get_connection() as db:
            await Engine._set_protection_expires_at(db, self.village_id, existing_expiration)
            await db.commit()
            success, expires_at = await Engine.use_village_protection_token(
                db,
                self.player_id,
                self.village_id,
                "exploring",
                quantity=2,
            )
            await db.commit()

        tokens = await self.fetch_tokens(self.player_id, self.village_id)
        self.assertTrue(success)
        self.assertEqual(expires_at, existing_expiration + timedelta(hours=2))
        self.assertEqual(tokens["exploring"], 3)

    async def test_token_quantity_rejects_when_inventory_is_insufficient(self):
        await self._grant_tokens("attacking", 2)
        existing_expiration = datetime(2026, 4, 16, 14, 0, 0)

        async with schema.get_connection() as db:
            await Engine._set_player_buff(db, self.player_id, self.village_id, "attacking", existing_expiration)
            await db.commit()
            success, message = await Engine.use_player_buff_token(
                db,
                self.player_id,
                self.village_id,
                "attacking",
                quantity=3,
            )
            await db.commit()

        buff_row = await self.fetchone(
            "SELECT buff_type, expires_at FROM player_buffs WHERE player_discord_id = ? AND village_id = ?",
            (self.player_id, self.village_id),
        )
        tokens = await self.fetch_tokens(self.player_id, self.village_id)
        self.assertFalse(success)
        self.assertEqual(message, "Not enough attacking tokens available.")
        self.assertEqual(buff_row[0], "attacking")
        self.assertEqual(datetime.fromisoformat(buff_row[1]), existing_expiration)
        self.assertEqual(tokens["attacking"], 2)

    async def test_token_view_quantity_dropdown_updates_embed_duration_preview(self):
        await self._grant_tokens("gathering", 10)
        bot = _FakeBot()
        bot.register_guild(71)
        cog = ActionsCog(bot=bot)
        inter = SimpleNamespace(
            author=SimpleNamespace(id=123),
            guild=SimpleNamespace(id=71, name="Village 71"),
            response=_FakeResponse(),
            bot=bot,
        )

        await cog.idlevillage_tokens.callback(cog, inter)

        view = inter.response.calls[-1]["view"]
        view.reset(mode="buff", token_type="gathering", quantity=10)
        quantity_dropdown = next(item for item in view.children if item.__class__.__name__ == "TokenQuantityDropdown")
        quantity_dropdown._selected_values = ["10"]

        await quantity_dropdown.callback(inter)

        updated_view = inter.response.calls[-1]["view"]
        embed = inter.response.calls[-1]["embed"]
        selected_quantity_field = next(field for field in embed.fields if field.name == "Selected Quantity")

        self.assertIsInstance(updated_view, TokenView)
        self.assertEqual(updated_view.quantity, 10)
        self.assertIn("1 matching token = 3 cycles", embed.fields[2].value)
        self.assertIn("10 tokens = 30 cycles", selected_quantity_field.value)

    async def test_switching_to_village_command_clears_quantity_preview(self):
        await self._grant_tokens("building", 10)
        bot = _FakeBot()
        bot.register_guild(71)
        cog = ActionsCog(bot=bot)
        inter = SimpleNamespace(
            author=SimpleNamespace(id=123),
            guild=SimpleNamespace(id=71, name="Village 71"),
            response=_FakeResponse(),
            bot=bot,
        )

        await cog.idlevillage_tokens.callback(cog, inter)

        view = inter.response.calls[-1]["view"]
        view.reset(mode="buff", token_type="gathering", quantity=10)
        mode_dropdown = next(item for item in view.children if item.__class__.__name__ == "TokenModeDropdown")
        mode_dropdown._selected_values = ["command"]

        await mode_dropdown.callback(inter)

        updated_view = inter.response.calls[-1]["view"]
        self.assertEqual(updated_view.mode, "command")
        self.assertEqual(updated_view.quantity, 1)
        self.assertFalse(any(field.name == "Selected Quantity" for field in inter.response.calls[-1]["embed"].fields))

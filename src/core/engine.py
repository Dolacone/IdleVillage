from datetime import datetime, timezone

from disnake.ext import tasks

from core.observability import log_event, new_request_id
from database.schema import get_connection


class Engine:
    """Runtime glue for bot state and the v2 watcher loop."""

    bot = None

    @staticmethod
    def set_bot(bot):
        Engine.bot = bot

    @staticmethod
    async def _process_watcher_v2(watcher_req_id: str) -> None:
        from core import notification
        from core.settlement import settle_complete_cycles

        log_event(watcher_req_id, "SYSTEM", "STATUS", "Watcher sweep started (v2)")
        now = datetime.now(timezone.utc)

        async with get_connection() as db:
            async with db.execute(
                "SELECT user_id FROM players WHERE completion_time <= ? AND action IS NOT NULL",
                (now.isoformat(),),
            ) as cursor:
                due_players = await cursor.fetchall()

        all_events: list[dict] = []
        for (user_id,) in due_players:
            events = await settle_complete_cycles(user_id, now)
            all_events.extend(events)

        if Engine.bot is not None and all_events:
            await notification.dispatch_events(Engine.bot, all_events)

        if Engine.bot is not None:
            await notification.update_dashboard(Engine.bot)

        log_event(watcher_req_id, "SYSTEM", "STATUS", "Watcher sweep completed (v2)")

    @staticmethod
    async def process_watcher(req_id: str = None):
        watcher_req_id = req_id or new_request_id()
        await Engine._process_watcher_v2(watcher_req_id)

    @staticmethod
    @tasks.loop(seconds=60)
    async def start_watcher_loop():
        await Engine.process_watcher()

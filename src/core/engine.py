import asyncio
from datetime import datetime, timedelta
import disnake
from disnake.ext import tasks
from src.database.schema import get_connection

class Engine:
    """Core game engine handling settlements and triggers."""

    @staticmethod
    async def settle_village(village_id: int, db=None):
        """
        Executes the hybrid decay algorithm for the village.
        """
        close_db = False
        if db is None:
            db = await get_connection()
            close_db = True

        try:
            async with db.execute('SELECT last_tick_time, food_efficiency_xp, storage_capacity_xp, resource_yield_xp FROM villages WHERE id = ?', (village_id,)) as cursor:
                village = await cursor.fetchone()

            if not village:
                return

            last_tick_time_str, food_xp, storage_xp, yield_xp = village

            now = datetime.utcnow()
            try:
                if last_tick_time_str.endswith('Z'):
                    last_tick_time_str = last_tick_time_str[:-1]
                last_tick = datetime.fromisoformat(last_tick_time_str).replace(tzinfo=None)
            except (ValueError, TypeError):
                last_tick = now

            delta = (now - last_tick).total_seconds()
            if delta < 3600:
                # Minimum decay threshold, or just do fractional if we want, but typically we want integer XP decay
                # The docs say: (Delta/3600) * (10 + active_players)
                pass

            hours = delta / 3600.0

            # Count active players (has sent a message in the last 7 days)
            active_threshold = (now - timedelta(days=7)).isoformat()
            async with db.execute('SELECT count(*) FROM players WHERE village_id = ? AND last_message_time >= ?', (village_id, active_threshold)) as cursor:
                active_count_row = await cursor.fetchone()
                active_count = active_count_row[0] if active_count_row else 0

            decay = int(hours * (10 + active_count))

            if decay > 0:
                new_food_xp = max(0, food_xp - decay)
                new_storage_xp = max(0, storage_xp - decay)
                new_yield_xp = max(0, yield_xp - decay)

                await db.execute('''
                    UPDATE villages
                    SET food_efficiency_xp = ?, storage_capacity_xp = ?, resource_yield_xp = ?, last_tick_time = ?
                    WHERE id = ?
                ''', (new_food_xp, new_storage_xp, new_yield_xp, now.isoformat(), village_id))
                await db.commit()

        finally:
            if close_db:
                await db.close()

    @staticmethod
    async def settle_player(player_id: int, db=None):
        """
        Executes the standard settlement process for a player.
        Calculates output, handles satiety, and updates the database.
        Accepts an existing db connection, otherwise creates one.
        """
        close_db = False
        if db is None:
            db = await get_connection()
            close_db = True

        try:
            async with db.execute('SELECT satiety_deadline, last_update_time, completion_time, status FROM players WHERE id = ?', (player_id,)) as cursor:
                player = await cursor.fetchone()

            if not player:
                return

            satiety_deadline_str, last_update_time_str, completion_time_str, status = player

            # Using UTC naive datetimes to align with SQLite's CURRENT_TIMESTAMP
            # and to allow simple subtraction against existing records.
            now = datetime.utcnow()

            # Parse last_update_time
            try:
                # Replace 'Z' or +00:00 to keep it naive if it was stored with timezone,
                # but SQLite defaults to naive YYYY-MM-DD HH:MM:SS
                if last_update_time_str.endswith('Z'):
                    last_update_time_str = last_update_time_str[:-1]
                last_update = datetime.fromisoformat(last_update_time_str).replace(tzinfo=None)
            except (ValueError, TypeError):
                last_update = now

            # Determine target time
            target_time = now
            if completion_time_str:
                try:
                    if completion_time_str.endswith('Z'):
                        completion_time_str = completion_time_str[:-1]
                    comp_time = datetime.fromisoformat(completion_time_str).replace(tzinfo=None)
                    target_time = min(now, comp_time)
                except (ValueError, TypeError):
                    pass

            # Calculate Delta
            delta = (target_time - last_update).total_seconds()
            if delta < 0:
                delta = 0

            # Handle satiety updates based on status
            new_satiety_deadline = satiety_deadline_str
            if status == 'idle' and satiety_deadline_str:
                try:
                    if satiety_deadline_str.endswith('Z'):
                        satiety_deadline_str = satiety_deadline_str[:-1]
                    curr_deadline = datetime.fromisoformat(satiety_deadline_str).replace(tzinfo=None)
                    new_deadline = curr_deadline + timedelta(seconds=delta)
                    new_satiety_deadline = new_deadline.isoformat()
                except (ValueError, TypeError):
                    pass

            # Update last_update_time and deadline
            await db.execute('''
                UPDATE players
                SET last_update_time = ?, satiety_deadline = ?
                WHERE id = ?
            ''', (target_time.isoformat(), new_satiety_deadline, player_id))
            await db.commit()
        finally:
            if close_db:
                await db.close()

    @staticmethod
    async def process_watcher():
        """
        Background task to process delayed settlements for players
        whose completion_time has passed, and actively apply village decay.
        """
        async with await get_connection() as db:
            now = datetime.utcnow().isoformat()

            # Settle expired players
            async with db.execute('SELECT id FROM players WHERE completion_time <= ?', (now,)) as cursor:
                players = await cursor.fetchall()

            for player in players:
                await Engine.settle_player(player[0], db)

            # Actively settle all villages (watcher sweep)
            async with db.execute('SELECT id FROM villages') as cursor:
                villages = await cursor.fetchall()

            for village in villages:
                await Engine.settle_village(village[0], db)

    @staticmethod
    @tasks.loop(seconds=300)
    async def start_watcher_loop():
        """Starts the Watcher loop to run every 300 seconds."""
        await Engine.process_watcher()

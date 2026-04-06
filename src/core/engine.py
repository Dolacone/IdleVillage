import asyncio
import math
from datetime import datetime, timedelta
import disnake
from disnake.ext import tasks
from src.database.schema import get_connection

class Engine:
    """Core game engine handling settlements and triggers."""

    @staticmethod
    def _parse_timestamp(value: str):
        if not value:
            return None
        normalized = value.replace("Z", "")
        if normalized.endswith("+00:00"):
            normalized = normalized[:-6]
        return datetime.fromisoformat(normalized).replace(tzinfo=None)

    @staticmethod
    def _resolve_action_type(status: str, current_action_type: str, location_status: str):
        if status == "idle":
            return "idle"
        if status == "moving" and location_status == "at_village":
            return "returning"
        if current_action_type == "build":
            return "build"
        if current_action_type == "explore" or status == "exploring":
            return "explore"
        if current_action_type == "gather":
            return "gather_material"
        if status == "moving":
            return "moving"
        return status or "idle"

    @staticmethod
    def _building_level_from_xp(xp: int):
        level = 0
        total_required = 0
        next_required = 1000
        current_xp = xp or 0

        while current_xp >= total_required + next_required:
            total_required += next_required
            level += 1
            next_required *= 2

        return level

    @staticmethod
    async def _try_refill_satiety(db, village_id: int, satiety_deadline: datetime, now: datetime):
        if satiety_deadline is None or village_id is None:
            return satiety_deadline

        remaining_hours = (satiety_deadline - now).total_seconds() / 3600.0

        async with db.execute(
            "SELECT food, food_efficiency_xp FROM villages WHERE id = ?",
            (village_id,),
        ) as cursor:
            village = await cursor.fetchone()

        if not village:
            return satiety_deadline

        village_food, food_efficiency_xp = village
        food_efficiency_level = Engine._building_level_from_xp(food_efficiency_xp)
        food_efficiency = 1.0 + (food_efficiency_level * 0.2)

        missing_hours = max(0.0, 100.0 - remaining_hours)
        food_cost = math.ceil(missing_hours / food_efficiency)
        if food_cost <= 0 or village_food < food_cost:
            return satiety_deadline

        await db.execute(
            "UPDATE villages SET food = food - ? WHERE id = ?",
            (food_cost, village_id),
        )
        return now + timedelta(hours=100)

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
                last_tick = Engine._parse_timestamp(last_tick_time_str)
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
            async with db.execute('SELECT satiety_deadline, last_update_time, completion_time, status, village_id, location_status, current_action_type, current_weight FROM players WHERE id = ?', (player_id,)) as cursor:
                player = await cursor.fetchone()

            if not player:
                return

            satiety_deadline_str, last_update_time_str, completion_time_str, status, village_id, location_status, current_action_type, current_weight = player

            # Using UTC naive datetimes to align with SQLite's CURRENT_TIMESTAMP
            # and to allow simple subtraction against existing records.
            now = datetime.utcnow()

            # Parse last_update_time
            try:
                last_update = Engine._parse_timestamp(last_update_time_str) or now
            except (ValueError, TypeError):
                last_update = now

            # Determine target time
            target_time = now
            completion_time = None
            if completion_time_str:
                try:
                    completion_time = Engine._parse_timestamp(completion_time_str)
                    if completion_time is not None:
                        target_time = min(now, completion_time)
                except (ValueError, TypeError):
                    pass

            # Calculate Delta
            delta = (target_time - last_update).total_seconds()
            if delta < 0:
                delta = 0

            # Get stat modifiers logic (efficiency) - simplified for foundational
            async with db.execute('SELECT strength, agility, perception, knowledge, endurance FROM player_stats WHERE player_id = ?', (player_id,)) as cursor:
                stats = await cursor.fetchone()

            p_str, p_agi, p_per, p_kno, p_end = stats if stats else (50, 50, 50, 50, 50)

            # Handle satiety updates based on status
            satiety_deadline = None
            new_satiety_deadline = None
            if satiety_deadline_str:
                try:
                    satiety_deadline = Engine._parse_timestamp(satiety_deadline_str)
                    new_satiety_deadline = satiety_deadline
                except (ValueError, TypeError):
                    pass

            if status == 'idle' and new_satiety_deadline is not None:
                new_satiety_deadline = new_satiety_deadline + timedelta(seconds=delta)

            # Settlement Effects
            new_status = status
            new_location = location_status
            new_action_type = current_action_type
            new_completion_time = completion_time_str
            new_weight = current_weight
            state_changed = False

            hours = delta / 3600.0

            if status == 'idle' and location_status == 'at_village':
                # Idle Gathering
                efficiency = (p_per + p_kno) / 2.0 / 100.0
                food_yield = int(hours * 10 * efficiency * 0.5)

                if food_yield > 0:
                    await db.execute('UPDATE villages SET food = food + ? WHERE id = ?', (food_yield, village_id))

                if new_satiety_deadline is not None:
                    new_satiety_deadline = await Engine._try_refill_satiety(
                        db,
                        village_id,
                        new_satiety_deadline,
                        target_time,
                    )

            # Check if action completed
            if completion_time is not None and target_time >= completion_time:
                new_status = 'idle'
                new_location = 'at_village'
                new_action_type = None
                new_completion_time = None
                new_weight = 0
                state_changed = True

                if new_satiety_deadline is not None:
                    new_satiety_deadline = await Engine._try_refill_satiety(
                        db,
                        village_id,
                        new_satiety_deadline,
                        target_time,
                    )

            # Log the finished action segment only when state changes.
            if delta > 0 and state_changed:
                await db.execute('''
                    INSERT INTO player_actions_log (player_id, action_type, start_time, end_time)
                    VALUES (?, ?, ?, ?)
                ''', (
                    player_id,
                    Engine._resolve_action_type(status, current_action_type, location_status),
                    last_update.isoformat(),
                    target_time.isoformat(),
                ))

            deadline_value = new_satiety_deadline.isoformat() if new_satiety_deadline is not None else None

            # Update last_update_time, deadline, and status
            await db.execute('''
                UPDATE players
                SET last_update_time = ?, satiety_deadline = ?, status = ?, location_status = ?, current_action_type = ?, completion_time = ?, current_weight = ?
                WHERE id = ?
            ''', (
                target_time.isoformat(),
                deadline_value,
                new_status,
                new_location,
                new_action_type,
                new_completion_time,
                new_weight,
                player_id,
            ))
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
        async with get_connection() as db:
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

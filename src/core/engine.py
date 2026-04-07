import asyncio
import math
import random
from datetime import datetime, timedelta
import disnake
from disnake.ext import tasks
from database.schema import get_connection

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
            hours = delta / 3600.0

            # Count active players (has sent a message in the last 7 days or has non-missing status)
            active_threshold = (now - timedelta(days=7)).isoformat()
            async with db.execute("SELECT count(*) FROM players WHERE village_id = ? AND (last_message_time >= ? OR status != 'missing')", (village_id, active_threshold)) as cursor:
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
    async def recalculate_player_stats(player_id: int, db):
        """Recalculates player stats based on the last 150 hours of action logs."""
        now = datetime.utcnow()
        window_start = now - timedelta(hours=150)

        async with db.execute(
            'SELECT action_type, start_time, end_time FROM player_actions_log WHERE player_id = ? AND end_time >= ?',
            (player_id, window_start.isoformat())
        ) as cursor:
            logs = await cursor.fetchall()

        p_str, p_agi, p_per, p_kno, p_end = 50.0, 50.0, 50.0, 50.0, 50.0

        for log in logs:
            action_type, start_str, end_str = log
            try:
                start = Engine._parse_timestamp(start_str)
                end = Engine._parse_timestamp(end_str)
                if start < window_start:
                    start = window_start
                duration_hours = (end - start).total_seconds() / 3600.0
                if duration_hours <= 0:
                    continue

                # 2 points per hour, distributed based on action
                if action_type == 'idle':
                    p_per += 1.0 * duration_hours
                    p_kno += 1.0 * duration_hours
                elif action_type == 'gathering_food':
                    p_per += 1.0 * duration_hours
                    p_kno += 1.0 * duration_hours
                elif action_type in ('gathering_wood', 'gathering_stone'):
                    p_str += 1.0 * duration_hours
                    p_end += 1.0 * duration_hours
                elif action_type == 'exploring':
                    p_agi += 1.0 * duration_hours
                    p_per += 1.0 * duration_hours
                elif action_type == 'building':
                    p_kno += 1.0 * duration_hours
                    p_end += 1.0 * duration_hours
            except (ValueError, TypeError):
                pass

        # Integer truncation for final stats
        final_str = int(p_str)
        final_agi = int(p_agi)
        final_per = int(p_per)
        final_kno = int(p_kno)
        final_end = int(p_end)

        await db.execute('''
            INSERT INTO player_stats (player_id, strength, agility, perception, knowledge, endurance, last_calc_time)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(player_id) DO UPDATE SET
                strength=excluded.strength,
                agility=excluded.agility,
                perception=excluded.perception,
                knowledge=excluded.knowledge,
                endurance=excluded.endurance,
                last_calc_time=excluded.last_calc_time
        ''', (player_id, final_str, final_agi, final_per, final_kno, final_end, now.isoformat()))

        return final_str, final_agi, final_per, final_kno, final_end

    @staticmethod
    async def settle_player(player_id: int, db=None, interrupted=False, is_ui_refresh=False):
        """
        Executes the settlement process for a player's current action.
        This represents the end of a 1-hour cycle (or an interruption).
        """
        close_db = False
        if db is None:
            db = await get_connection()
            close_db = True

        try:
            async with db.execute('SELECT last_update_time, completion_time, status, target_id, village_id FROM players WHERE id = ?', (player_id,)) as cursor:
                player = await cursor.fetchone()

            if not player:
                return

            last_update_time_str, completion_time_str, status, target_id, village_id = player

            now = datetime.utcnow()

            try:
                last_update = Engine._parse_timestamp(last_update_time_str) or now
            except (ValueError, TypeError):
                last_update = now

            target_time = now
            completion_time = None
            if completion_time_str:
                try:
                    completion_time = Engine._parse_timestamp(completion_time_str)
                    if completion_time is not None:
                        target_time = min(now, completion_time)
                except (ValueError, TypeError):
                    pass

            # Recalculate stats based on 150h window
            p_str, p_agi, p_per, p_kno, p_end = await Engine.recalculate_player_stats(player_id, db)

            delta = (target_time - last_update).total_seconds()
            if delta < 0:
                delta = 0

            hours = delta / 3600.0

            # Log the action
            action_type_log = status
            if status == 'gathering':
                # We need to know what we were gathering to log it properly
                if target_id:
                    async with db.execute('SELECT type FROM resource_nodes WHERE id = ?', (target_id,)) as cursor:
                        node = await cursor.fetchone()
                        if node:
                            action_type_log = f"gathering_{node[0]}"

            if delta > 0 and status != 'missing':
                await db.execute('''
                    INSERT INTO player_actions_log (player_id, action_type, start_time, end_time)
                    VALUES (?, ?, ?, ?)
                ''', (player_id, action_type_log, last_update.isoformat(), target_time.isoformat()))

            # Settlement logic
            async with db.execute('SELECT food, wood, stone, storage_capacity_xp, resource_yield_xp FROM villages WHERE id = ?', (village_id,)) as cursor:
                village_row = await cursor.fetchone()

            if village_row:
                v_food, v_wood, v_stone, v_storage_xp, v_yield_xp = village_row
                storage_capacity = 1000 * (2 ** Engine._building_level_from_xp(v_storage_xp))
                yield_mult = 1.0 + (Engine._building_level_from_xp(v_yield_xp) * 0.1)

                food_gained, wood_gained, stone_gained = 0, 0, 0

                if status == 'idle':
                    efficiency = (p_per + p_kno) / 2.0 / 100.0
                    food_gained = int(hours * 10 * efficiency * 0.5 * yield_mult)

                elif status == 'gathering' and target_id:
                    async with db.execute('SELECT type, remaining_amount, quality FROM resource_nodes WHERE id = ?', (target_id,)) as cursor:
                        node = await cursor.fetchone()

                    if node:
                        n_type, n_rem, n_qual = node
                        if n_type == 'food':
                            efficiency = (p_per + p_kno) / 2.0 / 100.0
                        else:
                            efficiency = (p_str + p_end) / 2.0 / 100.0

                        # If completed normally, or partial
                        amount_gathered = int(hours * 10 * efficiency * (n_qual / 100.0) * yield_mult)
                        actual_gathered = min(amount_gathered, n_rem)

                        if actual_gathered > 0:
                            await db.execute('UPDATE resource_nodes SET remaining_amount = remaining_amount - ? WHERE id = ?', (actual_gathered, target_id))
                            if n_type == 'food':
                                food_gained = actual_gathered
                            elif n_type == 'wood':
                                wood_gained = actual_gathered
                            elif n_type == 'stone':
                                stone_gained = actual_gathered

                elif status == 'building' and target_id:
                    efficiency = (p_kno + p_end) / 2.0 / 100.0
                    xp_gained = int(hours * 50 * efficiency)

                    if xp_gained > 0:
                        if target_id == 1:
                            await db.execute('UPDATE villages SET food_efficiency_xp = food_efficiency_xp + ? WHERE id = ?', (xp_gained, village_id))
                        elif target_id == 2:
                            await db.execute('UPDATE villages SET storage_capacity_xp = storage_capacity_xp + ? WHERE id = ?', (xp_gained, village_id))
                        elif target_id == 3:
                            await db.execute('UPDATE villages SET resource_yield_xp = resource_yield_xp + ? WHERE id = ?', (xp_gained, village_id))

                elif status == 'exploring':
                    efficiency = (p_agi + p_per) / 2.0 / 100.0
                    budget_minutes = hours * 60 * efficiency

                    # We process budget in 30m chunks
                    chunks = int(budget_minutes // 30)
                    for _ in range(chunks):
                        roll = random.random()
                        if roll < 0.40:
                            pass # Miss
                        else:
                            # Found a node
                            if roll < 0.75: # 35% chance (0.4 to 0.75)
                                n_lvl, n_stock = 1, 1000
                            elif roll < 0.90: # 15% chance
                                n_lvl, n_stock = 2, 2000
                            elif roll < 0.97: # 7% chance
                                n_lvl, n_stock = 3, 4000
                            else: # 3% chance
                                n_lvl, n_stock = 4, 8000

                            n_type = random.choice(['food', 'wood', 'stone'])
                            n_qual = random.randint(75 + (n_lvl - 1) * 25, 125 + (n_lvl - 1) * 25)
                            expiry = now + timedelta(hours=48)

                            await db.execute('''
                                INSERT INTO resource_nodes (village_id, type, level, quality, remaining_amount, expiry_time)
                                VALUES (?, ?, ?, ?, ?, ?)
                            ''', (village_id, n_type, n_lvl, n_qual, n_stock, expiry.isoformat()))
                            # We only find one node per hour cycle to simplify, or allow multiple.
                            # As per docs, multiple could be found if efficiency is extremely high, but normally one.

                # Apply storage capacity limits
                new_food = min(storage_capacity, v_food + food_gained)
                new_wood = min(storage_capacity, v_wood + wood_gained)
                new_stone = min(storage_capacity, v_stone + stone_gained)

                if food_gained > 0 or wood_gained > 0 or stone_gained > 0:
                    await db.execute('UPDATE villages SET food = ?, wood = ?, stone = ? WHERE id = ?', (new_food, new_wood, new_stone, village_id))

            new_status = status
            new_target = target_id
            new_completion = None

            # Check for inactive to missing transition
            async with db.execute('SELECT last_message_time FROM players WHERE id = ?', (player_id,)) as cursor:
                last_msg_row = await cursor.fetchone()

            if last_msg_row:
                last_msg = Engine._parse_timestamp(last_msg_row[0])
                if last_msg and (now - last_msg).total_days() >= 7 and (now - target_time).total_days() >= 7:
                    new_status = 'missing'
                    new_target = None

            if interrupted:
                new_status = 'idle'
                new_target = None

            if not interrupted and not is_ui_refresh and status != 'missing' and status != 'idle' and completion_time is not None and target_time >= completion_time:
                # Only auto-restart if the action actually completed its cycle.
                restarted = await Engine.start_action(player_id, status, target_id, db)
                if restarted:
                    return # start_action handles the DB update
                else:
                    new_status = 'idle'
                    new_target = None
            elif not interrupted and status != 'missing' and status != 'idle' and completion_time is not None and target_time < completion_time:
                # We haven't completed, retain current completion time
                new_completion = completion_time_str

            # Update the state if interrupted, completed & not restarted, or idle tracking, or UI refresh keeping completion
            if interrupted or new_status == 'idle' or (completion_time is None and status == 'idle') or is_ui_refresh:
                await db.execute('''
                    UPDATE players
                    SET status = ?, target_id = ?, last_update_time = ?, completion_time = ?
                    WHERE id = ?
                ''', (new_status, new_target, now.isoformat(), new_completion, player_id))

            await db.commit()

        finally:
            if close_db:
                await db.close()

    @staticmethod
    async def start_action(player_id: int, action: str, target_id: int = None, db=None) -> bool:
        """
        Attempts to start a 1-hour action cycle, pre-deducting resources.
        Returns True if successful, False if resources/conditions were not met.
        """
        close_db = False
        if db is None:
            db = await get_connection()
            close_db = True

        try:
            async with db.execute('SELECT village_id FROM players WHERE id = ?', (player_id,)) as cursor:
                player_row = await cursor.fetchone()

            if not player_row:
                return False

            village_id = player_row[0]

            async with db.execute('SELECT food, wood, stone, food_efficiency_xp FROM villages WHERE id = ?', (village_id,)) as cursor:
                village = await cursor.fetchone()

            if not village:
                return False

            v_food, v_wood, v_stone, v_food_xp = village

            food_cost, wood_cost, stone_cost = 0, 0, 0

            if action in ('gathering', 'exploring'):
                food_cost = 1
            elif action == 'building':
                food_cost = 1
                wood_cost = 10
                stone_cost = 5

            # Check costs
            if v_food < food_cost or v_wood < wood_cost or v_stone < stone_cost:
                return False

            # Additional checks for nodes
            if action == 'gathering' and target_id:
                async with db.execute('SELECT remaining_amount, expiry_time FROM resource_nodes WHERE id = ?', (target_id,)) as cursor:
                    node = await cursor.fetchone()
                if not node:
                    return False
                n_rem, n_exp_str = node
                if n_rem <= 0:
                    return False
                n_exp = Engine._parse_timestamp(n_exp_str)
                if n_exp and datetime.utcnow() >= n_exp:
                    return False

            # Deduct costs
            if food_cost > 0 or wood_cost > 0 or stone_cost > 0:
                await db.execute('UPDATE villages SET food = food - ?, wood = wood - ?, stone = stone - ? WHERE id = ?', (food_cost, wood_cost, stone_cost, village_id))

            # Calculate duration (1 hour, modified by food efficiency if it costs food)
            duration_hours = 1.0
            if food_cost > 0:
                food_eff_level = Engine._building_level_from_xp(v_food_xp)
                duration_hours = 1.0 + (food_eff_level * 0.2)

            now = datetime.utcnow()
            completion_time = now + timedelta(hours=duration_hours)

            await db.execute('''
                UPDATE players
                SET status = ?, target_id = ?, last_update_time = ?, completion_time = ?
                WHERE id = ?
            ''', (action, target_id, now.isoformat(), completion_time.isoformat(), player_id))

            await db.commit()
            return True

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

            # Clean up expired nodes
            await db.execute("DELETE FROM resource_nodes WHERE expiry_time <= ? OR remaining_amount <= 0", (now,))

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

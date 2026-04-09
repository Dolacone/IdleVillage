import math
import random
from datetime import datetime, timedelta, timezone

import disnake
from disnake.ext import tasks

from core.config import get_action_cycle_minutes
from core.observability import log_event, new_request_id
from database.schema import get_connection


class Engine:
    """Core game engine handling settlements, announcements, and watcher triggers."""

    bot = None

    BUILDING_NAMES = {
        1: "廚房",
        2: "倉庫",
        3: "加工",
    }

    @staticmethod
    def set_bot(bot):
        Engine.bot = bot

    @staticmethod
    def _parse_timestamp(value: str):
        if not value:
            return None
        normalized = value.replace("Z", "")
        if normalized.endswith("+00:00"):
            normalized = normalized[:-6]
        return datetime.fromisoformat(normalized).replace(tzinfo=None)

    @staticmethod
    def _to_discord_unix(dt: datetime):
        if dt is None:
            return None
        return int(dt.replace(tzinfo=timezone.utc).timestamp())

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
    def _next_building_threshold(level: int):
        return 1000 * (2 ** level)

    @staticmethod
    def _building_level_base_xp(level: int):
        total_required = 0
        next_required = 1000
        current_level = max(0, int(level or 0))

        for _ in range(current_level):
            total_required += next_required
            next_required *= 2

        return total_required

    @staticmethod
    def _action_cycle_minutes():
        return get_action_cycle_minutes()

    @staticmethod
    def _action_cycle_seconds():
        return Engine._action_cycle_minutes() * 60

    @staticmethod
    def _time_ratio(seconds: float):
        if seconds <= 0:
            return 0.0
        return seconds / Engine._action_cycle_seconds()

    @staticmethod
    def _food_cost(food_efficiency_xp: int):
        return max(1, 10 - Engine._building_level_from_xp(food_efficiency_xp))

    @staticmethod
    def _storage_capacity(storage_capacity_xp: int):
        return 1000 * (2 ** Engine._building_level_from_xp(storage_capacity_xp))

    @staticmethod
    def _yield_multiplier(resource_yield_xp: int):
        return 1.0 + (Engine._building_level_from_xp(resource_yield_xp) * 0.1)

    @staticmethod
    def _next_idle_completion(last_update: datetime):
        if last_update is None:
            return None
        return last_update + timedelta(minutes=Engine._action_cycle_minutes())

    @staticmethod
    def _building_decay_per_cycle(active_players: int, current_xp: int):
        active_players = max(0, int(active_players or 0))
        current_xp = max(0, int(current_xp or 0))
        return int(active_players * 0.5) + int(current_xp * (0.001 + (current_xp / 5_000_000.0)))

    @staticmethod
    def _building_progress_line(building_id: int, xp: int):
        level = Engine._building_level_from_xp(xp)
        level_base_xp = Engine._building_level_base_xp(level)
        current_level_xp = max(0, (xp or 0) - level_base_xp)
        next_threshold = Engine._next_building_threshold(level)
        return f"{Engine.BUILDING_NAMES[building_id]}: Lv.{level} [XP: {current_level_xp:,} / {next_threshold:,}]"

    @staticmethod
    def _format_remaining_short(target_time: datetime, reference_time: datetime = None):
        if target_time is None:
            return "manual"

        now = reference_time or datetime.utcnow()
        seconds = max(0, int((target_time - now).total_seconds()))
        if seconds < 60:
            return "<1m"

        minutes = math.ceil(seconds / 60.0)
        if minutes < 60:
            return f"{minutes}m"

        hours, remaining_minutes = divmod(minutes, 60)
        if remaining_minutes == 0:
            return f"{hours}h"
        return f"{hours}h {remaining_minutes}m"

    @staticmethod
    async def _build_villager_status_summary(db, status: str, target_id: int, last_update: datetime, completion_time: datetime):
        status_text = await Engine._get_target_description(db, status, target_id)
        next_check = completion_time
        if status == "idle":
            next_check = Engine._next_idle_completion(last_update)
        remaining = Engine._format_remaining_short(next_check)
        return f"[{status_text}] ({remaining})"

    @staticmethod
    async def _announce_channel_message(village_id: int, message: str, bot=None, req_id: str = None, user_id=None):
        if not message:
            return None

        async with get_connection() as db:
            async with db.execute(
                """
                SELECT announcement_channel_id
                FROM villages
                WHERE id = ?
                """,
                (village_id,),
            ) as cursor:
                row = await cursor.fetchone()

        if not row or not row[0]:
            return None

        channel = await Engine._resolve_channel(bot or Engine.bot, row[0])
        if channel is None:
            return None

        try:
            sent_message = await channel.send(message)
            log_event(req_id, user_id, "RESP", f"Announcement event sent for village {village_id}")
            return sent_message
        except Exception as exc:
            log_event(req_id, user_id, "ERROR", f"Announcement event failed for village {village_id}: {exc}")
            return None

    @staticmethod
    async def send_node_expiry_announcement(
        village_id: int,
        node_id: int,
        node_type: str,
        reason: str,
        bot=None,
        req_id: str = None,
        user_id=None,
    ):
        if reason == "out_of_stock":
            message = f"{node_type.title()} node #{node_id} is now out of stock."
        else:
            message = f"{node_type.title()} node #{node_id} is no longer available."
        return await Engine._announce_channel_message(
            village_id,
            message,
            bot=bot,
            req_id=req_id,
            user_id=user_id,
        )

    @staticmethod
    async def send_idle_announcement(village_id: int, player_discord_id: int, bot=None, req_id: str = None, user_id=None):
        message = f"<@{player_discord_id}> You have finished your task and are now idle in the village."
        return await Engine._announce_channel_message(
            village_id,
            message,
            bot=bot,
            req_id=req_id,
            user_id=user_id,
        )

    @staticmethod
    async def send_upgrade_announcement(
        village_id: int,
        building_name: str,
        new_level: int,
        bot=None,
        req_id: str = None,
        user_id=None,
    ):
        message = f"The village has successfully upgraded the {building_name} to Level {new_level}! 🎉"
        return await Engine._announce_channel_message(
            village_id,
            message,
            bot=bot,
            req_id=req_id,
            user_id=user_id,
        )

    @staticmethod
    def _player_is_missing(last_message_time: datetime, last_command_time: datetime, now: datetime):
        if last_message_time is None or last_command_time is None:
            return False
        return (now - last_message_time) >= timedelta(days=7) and (now - last_command_time) >= timedelta(days=7)

    @staticmethod
    def _chunk_time_range(start: datetime, end: datetime):
        if start >= end:
            return []

        segments = []
        cursor = start
        cycle_seconds = Engine._action_cycle_seconds()
        while cursor < end:
            next_cursor = min(end, cursor + timedelta(seconds=cycle_seconds))
            segments.append((cursor, next_cursor))
            cursor = next_cursor
        return segments

    @staticmethod
    async def _resolve_gathering_log_type(db, target_id: int):
        if not target_id:
            return "gathering"

        async with db.execute("SELECT type FROM resource_nodes WHERE id = ?", (target_id,)) as cursor:
            node = await cursor.fetchone()
        if not node:
            return "gathering"
        return f"gathering_{node[0]}"

    @staticmethod
    async def _record_action_logs(
        db,
        player_discord_id: int,
        village_id: int,
        status: str,
        target_id: int,
        start: datetime,
        end: datetime,
    ):
        if start >= end or status == "missing":
            return

        action_type = status
        if status == "gathering":
            action_type = await Engine._resolve_gathering_log_type(db, target_id)

        segments = Engine._chunk_time_range(start, end)
        for seg_start, seg_end in segments:
            await db.execute(
                """
                INSERT INTO player_actions_log (player_discord_id, village_id, action_type, start_time, end_time)
                VALUES (?, ?, ?, ?, ?)
                """,
                (player_discord_id, village_id, action_type, seg_start.isoformat(), seg_end.isoformat()),
            )

    @staticmethod
    async def _mark_missing_players(db, now: datetime, village_id: int = None, req_id: str = None, user_id=None):
        threshold = (now - timedelta(days=7)).isoformat()
        query = """
            SELECT discord_id, village_id
            FROM players
            WHERE status != 'missing'
              AND last_message_time != ''
              AND last_command_time != ''
              AND last_message_time <= ?
              AND last_command_time <= ?
        """
        params = [threshold, threshold]
        if village_id is not None:
            query += " AND village_id = ?"
            params.append(village_id)

        async with db.execute(query, tuple(params)) as cursor:
            players = await cursor.fetchall()

        for player_discord_id, player_village_id in players:
            await db.execute(
                """
                UPDATE players
                SET status = 'missing',
                    target_id = NULL,
                    completion_time = NULL
                WHERE discord_id = ?
                  AND village_id = ?
                """,
                (player_discord_id, player_village_id),
            )
            log_event(
                req_id,
                user_id,
                "STATUS",
                f"Player {player_discord_id} status changed to missing by inactivity scan",
            )

        return len(players)

    @staticmethod
    async def _settle_time_slice(
        player_discord_id: int,
        village_id: int,
        status: str,
        target_id: int,
        start_time: datetime,
        end_time: datetime,
        db,
        req_id: str = None,
        user_id=None,
    ):
        if end_time <= start_time or status == "missing":
            return {"discoveries": [], "expired_nodes": [], "upgrades": []}

        p_str, p_agi, p_per, p_kno, p_end = await Engine.recalculate_player_stats(player_discord_id, village_id, db)
        delta_seconds = max(0.0, (end_time - start_time).total_seconds())
        if delta_seconds <= 0:
            return {"discoveries": [], "expired_nodes": [], "upgrades": []}

        time_ratio = Engine._time_ratio(delta_seconds)
        await Engine._record_action_logs(
            db,
            player_discord_id,
            village_id,
            status,
            target_id,
            start_time,
            end_time,
        )

        async with db.execute(
            """
            SELECT food, wood, stone, food_efficiency_xp, storage_capacity_xp, resource_yield_xp
            FROM villages
            WHERE id = ?
            """,
            (village_id,),
        ) as cursor:
            village_row = await cursor.fetchone()

        if not village_row:
            return {"discoveries": [], "expired_nodes": [], "upgrades": []}

        discoveries = []
        upgrades = []
        v_food, v_wood, v_stone, _food_eff_xp, v_storage_xp, v_yield_xp = village_row
        storage_capacity = Engine._storage_capacity(v_storage_xp)
        yield_mult = Engine._yield_multiplier(v_yield_xp)

        food_gained, wood_gained, stone_gained = 0, 0, 0

        depleted_nodes = []

        if status == "idle":
            efficiency = (p_per + p_kno) / 2.0 / 100.0
            food_gained = int(50 * efficiency * 0.5 * yield_mult * time_ratio)

        elif status == "gathering" and target_id:
            async with db.execute(
                "SELECT type, remaining_amount, quality FROM resource_nodes WHERE id = ?",
                (target_id,),
            ) as cursor:
                node = await cursor.fetchone()

            if node:
                node_type, remaining_amount, quality = node
                if node_type == "food":
                    efficiency = (p_per + p_kno) / 2.0 / 100.0
                else:
                    efficiency = (p_str + p_end) / 2.0 / 100.0

                gathered = int(50 * efficiency * (max(75, quality) / 100.0) * yield_mult * time_ratio)
                actual_gathered = min(gathered, remaining_amount)

                if actual_gathered > 0:
                    new_remaining_amount = remaining_amount - actual_gathered
                    await db.execute(
                        "UPDATE resource_nodes SET remaining_amount = ? WHERE id = ?",
                        (max(0, new_remaining_amount), target_id),
                    )
                    if new_remaining_amount <= 0:
                        depleted_nodes.append(
                            {
                                "node_id": target_id,
                                "node_type": node_type,
                                "reason": "out_of_stock",
                            }
                        )
                    if node_type == "food":
                        food_gained = actual_gathered
                    elif node_type == "wood":
                        wood_gained = actual_gathered
                    elif node_type == "stone":
                        stone_gained = actual_gathered

        elif status == "building" and target_id:
            efficiency = (p_kno + p_end) / 2.0 / 100.0
            xp_gained = int(50 * efficiency * time_ratio)
            if xp_gained > 0:
                xp_by_building = {
                    1: _food_eff_xp,
                    2: v_storage_xp,
                    3: v_yield_xp,
                }
                previous_xp = xp_by_building.get(target_id, 0)
                previous_level = Engine._building_level_from_xp(previous_xp)
                new_xp = previous_xp + xp_gained
                new_level = Engine._building_level_from_xp(new_xp)
                if target_id == 1:
                    await db.execute(
                        "UPDATE villages SET food_efficiency_xp = food_efficiency_xp + ? WHERE id = ?",
                        (xp_gained, village_id),
                    )
                elif target_id == 2:
                    await db.execute(
                        "UPDATE villages SET storage_capacity_xp = storage_capacity_xp + ? WHERE id = ?",
                        (xp_gained, village_id),
                    )
                elif target_id == 3:
                    await db.execute(
                        "UPDATE villages SET resource_yield_xp = resource_yield_xp + ? WHERE id = ?",
                        (xp_gained, village_id),
                    )
                if new_level > previous_level:
                    upgrades.append(
                        {
                            "building_id": target_id,
                            "building_name": Engine.BUILDING_NAMES.get(target_id, f"Building {target_id}"),
                            "level": new_level,
                        }
                    )

        elif status == "exploring" and time_ratio > 0:
            discovery_chance = min(1.0, time_ratio * ((p_per + p_kno) / 400.0))
            if random.random() < discovery_chance:
                perception_knowledge = p_per + p_kno
                node_type = random.choice(["food", "wood", "stone"])
                quality = max(75, int(random.gauss((p_per + p_kno) / 2.0, 50)))
                stock = random.randint(perception_knowledge * 5, perception_knowledge * 10)

                async with db.execute(
                    """
                    SELECT id, quality, remaining_amount
                    FROM resource_nodes
                    WHERE village_id = ?
                      AND type = ?
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    (village_id, node_type),
                ) as cursor:
                    existing_node = await cursor.fetchone()

                if existing_node:
                    node_id, old_quality, old_stock = existing_node
                    cap_was_full = old_stock >= 8000
                    if old_stock <= 0:
                        new_quality = quality
                    else:
                        new_quality = math.floor(
                            ((old_quality * old_stock) + (quality * stock)) / (old_stock + stock)
                        )
                    new_stock = min(8000, old_stock + stock)
                    await db.execute(
                        """
                        UPDATE resource_nodes
                        SET quality = ?, remaining_amount = ?, expiry_time = NULL
                        WHERE id = ?
                        """,
                        (new_quality, new_stock, node_id),
                    )
                else:
                    new_quality = quality
                    new_stock = min(8000, stock)
                    await db.execute(
                        """
                        INSERT INTO resource_nodes (
                            village_id, type, quality, remaining_amount, expiry_time
                        )
                        VALUES (?, ?, ?, ?, NULL)
                        """,
                        (village_id, node_type, new_quality, new_stock),
                    )

                discoveries.append(
                    {
                        "type": node_type,
                        "quality": new_quality,
                        "remaining_amount": new_stock,
                        "stock_added": stock,
                        "is_new_node": existing_node is None,
                        "cap_was_full": existing_node is not None and cap_was_full,
                    }
                )

        new_food = min(storage_capacity, v_food + food_gained)
        new_wood = min(storage_capacity, v_wood + wood_gained)
        new_stone = min(storage_capacity, v_stone + stone_gained)

        if food_gained > 0 or wood_gained > 0 or stone_gained > 0:
            await db.execute(
                "UPDATE villages SET food = ?, wood = ?, stone = ? WHERE id = ?",
                (new_food, new_wood, new_stone, village_id),
            )
            log_event(
                req_id,
                user_id,
                "SETTLE",
                (
                    f"Player {player_discord_id} settled {status}: "
                    f"food={food_gained}, wood={wood_gained}, stone={stone_gained}, "
                    f"time_ratio={time_ratio:.2f}"
                ),
            )

        return {"discoveries": discoveries, "expired_nodes": depleted_nodes, "upgrades": upgrades}

    @staticmethod
    async def settle_village(village_id: int, db=None, req_id: str = None, user_id=None):
        """Executes the hybrid decay algorithm for the village."""
        close_db = False
        if db is None:
            db = await get_connection()
            close_db = True

        try:
            async with db.execute(
                """
                SELECT last_tick_time, food_efficiency_xp, storage_capacity_xp, resource_yield_xp
                FROM villages
                WHERE id = ?
                """,
                (village_id,),
            ) as cursor:
                village = await cursor.fetchone()

            if not village:
                return

            last_tick_time_str, food_xp, storage_xp, yield_xp = village
            now = datetime.utcnow()
            await Engine._mark_missing_players(db, now, village_id=village_id, req_id=req_id, user_id=user_id)
            try:
                last_tick = Engine._parse_timestamp(last_tick_time_str)
            except (ValueError, TypeError):
                last_tick = now

            delta = (now - last_tick).total_seconds()
            cycle_units = delta / Engine._action_cycle_seconds()

            async with db.execute(
                """
                SELECT count(*)
                FROM players
                WHERE village_id = ?
                  AND status != 'missing'
                """,
                (village_id,),
            ) as cursor:
                active_count_row = await cursor.fetchone()

            active_count = active_count_row[0] if active_count_row else 0
            food_decay = int(cycle_units * Engine._building_decay_per_cycle(active_count, food_xp))
            storage_decay = int(cycle_units * Engine._building_decay_per_cycle(active_count, storage_xp))
            yield_decay = int(cycle_units * Engine._building_decay_per_cycle(active_count, yield_xp))

            if food_decay > 0 or storage_decay > 0 or yield_decay > 0:
                await db.execute(
                    """
                    UPDATE villages
                    SET food_efficiency_xp = ?,
                        storage_capacity_xp = ?,
                        resource_yield_xp = ?,
                        last_tick_time = ?
                    WHERE id = ?
                    """,
                    (
                        max(0, food_xp - food_decay),
                        max(0, storage_xp - storage_decay),
                        max(0, yield_xp - yield_decay),
                        now.isoformat(),
                        village_id,
                    ),
                )
                await db.commit()
                log_event(
                    req_id,
                    user_id,
                    "SETTLE",
                    (
                        f"Village {village_id} decay applied: "
                        f"food={food_decay}, storage={storage_decay}, yield={yield_decay}"
                    ),
                )

        finally:
            if close_db:
                await db.close()

    @staticmethod
    async def recalculate_player_stats(player_discord_id: int, village_id: int, db):
        """Recalculates player stats based on the last 150 action log entries."""
        now = datetime.utcnow()
        async with db.execute(
            """
            SELECT action_type, start_time, end_time
            FROM player_actions_log
            WHERE player_discord_id = ?
              AND village_id = ?
            ORDER BY end_time DESC, id DESC
            LIMIT 150
            """,
            (player_discord_id, village_id),
        ) as cursor:
            logs = await cursor.fetchall()

        p_str, p_agi, p_per, p_kno, p_end = 50.0, 50.0, 50.0, 50.0, 50.0

        for action_type, start_str, end_str in reversed(logs):
            try:
                start = Engine._parse_timestamp(start_str)
                end = Engine._parse_timestamp(end_str)
                if start is None or end is None or end <= start:
                    continue
                time_ratio = Engine._time_ratio((end - start).total_seconds())
            except (ValueError, TypeError):
                continue

            if action_type == "idle":
                p_per += 1.0 * time_ratio
                p_kno += 1.0 * time_ratio
            elif action_type == "gathering_food":
                p_per += 1.0 * time_ratio
                p_kno += 1.0 * time_ratio
            elif action_type in ("gathering_wood", "gathering_stone"):
                p_str += 1.0 * time_ratio
                p_end += 1.0 * time_ratio
            elif action_type == "exploring":
                p_agi += 1.0 * time_ratio
                p_per += 1.0 * time_ratio
            elif action_type == "building":
                p_kno += 1.0 * time_ratio
                p_end += 1.0 * time_ratio

        final_stats = (int(p_str), int(p_agi), int(p_per), int(p_kno), int(p_end))
        await db.execute(
            """
            INSERT INTO player_stats (
                player_discord_id, village_id,
                strength, agility, perception, knowledge, endurance, last_calc_time
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(player_discord_id, village_id) DO UPDATE SET
                strength = excluded.strength,
                agility = excluded.agility,
                perception = excluded.perception,
                knowledge = excluded.knowledge,
                endurance = excluded.endurance,
                last_calc_time = excluded.last_calc_time
            """,
            (player_discord_id, village_id, *final_stats, now.isoformat()),
        )

        return final_stats

    @staticmethod
    async def _get_target_description(db, status: str, target_id: int):
        if status == "gathering" and target_id:
            async with db.execute("SELECT type FROM resource_nodes WHERE id = ?", (target_id,)) as cursor:
                node = await cursor.fetchone()
            if node:
                return f"Gathering {node[0].title()}"
            return "Gathering"

        if status == "building" and target_id:
            return f"Building {Engine.BUILDING_NAMES.get(target_id, 'Village Project')}"

        if status == "exploring":
            return "Exploring"
        if status == "idle":
            return "Idle"
        if status == "missing":
            return "Missing"
        return status.title()

    @staticmethod
    async def settle_player(
        player_discord_id: int,
        village_id: int,
        db=None,
        interrupted=False,
        is_ui_refresh=False,
        req_id: str = None,
        user_id=None,
    ):
        """Executes settlement for the player's current action."""
        close_db = False
        if db is None:
            db = await get_connection()
            close_db = True

        try:
            now = datetime.utcnow()
            async with db.execute(
                """
                SELECT last_update_time, completion_time, status, target_id, last_message_time, last_command_time
                FROM players
                WHERE discord_id = ?
                  AND village_id = ?
                """,
                (player_discord_id, village_id),
            ) as cursor:
                player = await cursor.fetchone()

            if not player:
                return None

            last_update_time_str, completion_time_str, status, target_id, last_message_time_str, last_command_time_str = player

            try:
                last_update = Engine._parse_timestamp(last_update_time_str) or now
            except (ValueError, TypeError):
                last_update = now

            try:
                last_message_time = Engine._parse_timestamp(last_message_time_str)
            except (ValueError, TypeError):
                last_message_time = None

            try:
                last_command_time = Engine._parse_timestamp(last_command_time_str)
            except (ValueError, TypeError):
                last_command_time = None

            completion_time = None
            if completion_time_str:
                try:
                    completion_time = Engine._parse_timestamp(completion_time_str)
                except (ValueError, TypeError):
                    completion_time = None

            discoveries = []
            expired_nodes = []
            upgrades = []
            send_idle_notification = False
            current_status = status
            current_target = target_id
            current_last_update = last_update
            current_completion = completion_time

            if Engine._player_is_missing(last_message_time, last_command_time, now):
                current_status = "missing"
                current_target = None
                current_completion = None
            elif not interrupted and current_status not in ("missing", "idle") and current_completion is not None:
                while now >= current_completion:
                    slice_result = await Engine._settle_time_slice(
                        player_discord_id,
                        village_id,
                        current_status,
                        current_target,
                        current_last_update,
                        current_completion,
                        db,
                        req_id=req_id,
                        user_id=user_id,
                    )
                    discoveries.extend(slice_result["discoveries"])
                    expired_nodes.extend(slice_result["expired_nodes"])
                    upgrades.extend(slice_result["upgrades"])
                    current_last_update = current_completion

                    if Engine._player_is_missing(last_message_time, last_command_time, now):
                        current_status = "missing"
                        current_target = None
                        current_completion = None
                        break

                    next_completion = await Engine._start_action_cycle(
                        player_discord_id,
                        village_id,
                        current_status,
                        current_target,
                        db,
                        cycle_start_time=current_last_update,
                        commit=False,
                        req_id=req_id,
                        user_id=user_id,
                    )
                    if next_completion is None:
                        if current_status == "gathering" and current_target:
                            async with db.execute(
                                "SELECT type, remaining_amount FROM resource_nodes WHERE id = ?",
                                (current_target,),
                            ) as cursor:
                                node_row = await cursor.fetchone()
                            if node_row:
                                node_type, remaining_amount = node_row
                                if remaining_amount <= 0:
                                    already_recorded = any(
                                        expired_node["node_id"] == current_target
                                        and expired_node["reason"] == "out_of_stock"
                                        for expired_node in expired_nodes
                                    )
                                    if not already_recorded:
                                        expired_nodes.append(
                                            {
                                                "node_id": current_target,
                                                "node_type": node_type,
                                                "reason": "out_of_stock",
                                            }
                                        )
                        current_status = "idle"
                        current_target = None
                        current_completion = None
                        send_idle_notification = True
                        break

                    current_completion = next_completion

            partial_end = None
            if current_status == "missing":
                partial_end = None
            elif current_status == "idle":
                partial_end = now if current_completion is None else min(now, current_completion)
                current_completion = None
            elif interrupted:
                partial_end = now if current_completion is None else min(now, current_completion)
            elif is_ui_refresh:
                partial_end = now if current_completion is None else min(now, current_completion)

            if partial_end is not None:
                slice_result = await Engine._settle_time_slice(
                    player_discord_id,
                    village_id,
                    current_status,
                    current_target,
                    current_last_update,
                    partial_end,
                    db,
                    req_id=req_id,
                    user_id=user_id,
                )
                discoveries.extend(slice_result["discoveries"])
                expired_nodes.extend(slice_result["expired_nodes"])
                upgrades.extend(slice_result["upgrades"])
                current_last_update = partial_end

            new_status = current_status
            new_target = current_target
            new_completion = current_completion.isoformat() if current_completion is not None else None

            if interrupted and new_status != "missing":
                new_status = "idle"
                new_target = None
                new_completion = None

            if new_status == "missing":
                new_completion = None
            elif new_status == "idle" and current_completion is None:
                new_completion = None

            if interrupted or new_status in ("idle", "missing") or (current_completion is None and status == "idle") or is_ui_refresh:
                await db.execute(
                    """
                    UPDATE players
                    SET status = ?, target_id = ?, last_update_time = ?, completion_time = ?
                    WHERE discord_id = ?
                      AND village_id = ?
                    """,
                    (new_status, new_target, current_last_update.isoformat(), new_completion, player_discord_id, village_id),
                )

            await db.commit()

            if new_status != status or new_target != target_id:
                log_event(
                    req_id,
                    user_id,
                    "STATUS",
                    f"Player {player_discord_id} status changed from {status} to {new_status}",
                )

            for expired_node in expired_nodes:
                await Engine.send_node_expiry_announcement(
                    village_id,
                    expired_node["node_id"],
                    expired_node["node_type"],
                    expired_node["reason"],
                    bot=Engine.bot,
                    req_id=req_id,
                    user_id=user_id,
                )

            for upgrade in upgrades:
                await Engine.send_upgrade_announcement(
                    village_id,
                    upgrade["building_name"],
                    upgrade["level"],
                    bot=Engine.bot,
                    req_id=req_id,
                    user_id=user_id,
                )

            if send_idle_notification and not interrupted and status not in ("idle", "missing"):
                await Engine.send_idle_announcement(
                    village_id,
                    player_discord_id,
                    bot=Engine.bot,
                    req_id=req_id,
                    user_id=user_id,
                )

            await Engine.sync_announcement(village_id, db=db, bot=Engine.bot, req_id=req_id, user_id=user_id)
            return {"discoveries": discoveries, "status": new_status}

        finally:
            if close_db:
                await db.close()

    @staticmethod
    async def _start_action_cycle(
        player_discord_id: int,
        village_id: int,
        action: str,
        target_id: int = None,
        db=None,
        cycle_start_time: datetime = None,
        commit: bool = True,
        req_id: str = None,
        user_id=None,
    ):
        """Starts one action cycle at an explicit cycle boundary."""
        close_db = False
        if db is None:
            db = await get_connection()
            close_db = True

        try:
            async with db.execute(
                """
                SELECT 1
                FROM players
                WHERE discord_id = ?
                  AND village_id = ?
                """,
                (player_discord_id, village_id),
            ) as cursor:
                player_row = await cursor.fetchone()

            if not player_row:
                return None
            async with db.execute(
                """
                SELECT food, wood, stone, food_efficiency_xp
                FROM villages
                WHERE id = ?
                """,
                (village_id,),
            ) as cursor:
                village = await cursor.fetchone()

            if not village:
                return None

            v_food, v_wood, v_stone, v_food_xp = village
            food_cost = 0
            wood_cost = 0
            stone_cost = 0

            if action in ("gathering", "exploring", "building"):
                food_cost = Engine._food_cost(v_food_xp)
            if action == "building":
                wood_cost = 10
                stone_cost = 5

            if action == "gathering":
                if not target_id:
                    return None
                async with db.execute(
                    "SELECT remaining_amount FROM resource_nodes WHERE id = ?",
                    (target_id,),
                ) as cursor:
                    node = await cursor.fetchone()
                if not node:
                    return None
                remaining_amount = node[0]
                if remaining_amount <= 0:
                    return None

            if action == "building" and not target_id:
                return None

            if v_food < food_cost or v_wood < wood_cost or v_stone < stone_cost:
                log_event(
                    req_id,
                    user_id,
                    "ERROR",
                    (
                        f"Player {player_discord_id} could not start {action}: "
                        f"food={v_food}/{food_cost}, wood={v_wood}/{wood_cost}, stone={v_stone}/{stone_cost}"
                    ),
                )
                return None

            if food_cost > 0 or wood_cost > 0 or stone_cost > 0:
                await db.execute(
                    """
                    UPDATE villages
                    SET food = food - ?, wood = wood - ?, stone = stone - ?
                    WHERE id = ?
                    """,
                    (food_cost, wood_cost, stone_cost, village_id),
                )
                log_event(
                    req_id,
                    user_id,
                    "COST",
                    (
                        f"Player {player_discord_id} started {action}: "
                        f"food={food_cost}, wood={wood_cost}, stone={stone_cost}"
                    ),
                )

            cycle_start_time = cycle_start_time or datetime.utcnow()
            completion_time = cycle_start_time + timedelta(minutes=Engine._action_cycle_minutes())
            await db.execute(
                """
                UPDATE players
                SET status = ?, target_id = ?, last_update_time = ?, completion_time = ?
                WHERE discord_id = ?
                  AND village_id = ?
                """,
                (action, target_id, cycle_start_time.isoformat(), completion_time.isoformat(), player_discord_id, village_id),
            )
            if commit:
                await db.commit()
            log_event(
                req_id,
                user_id,
                "STATUS",
                f"Player {player_discord_id} entered {action} until {completion_time.isoformat()}",
            )
            return completion_time

        finally:
            if close_db:
                await db.close()

    @staticmethod
    async def start_action(
        player_discord_id: int,
        village_id: int,
        action: str,
        target_id: int = None,
        db=None,
        req_id: str = None,
        user_id=None,
    ) -> bool:
        """Attempts to start an action cycle and pre-deduct village resources."""
        completion_time = await Engine._start_action_cycle(
            player_discord_id,
            village_id,
            action,
            target_id,
            db=db,
            cycle_start_time=datetime.utcnow(),
            commit=True,
            req_id=req_id,
            user_id=user_id,
        )
        return completion_time is not None

    @staticmethod
    async def _resolve_channel(bot, channel_id):
        if not bot or not channel_id:
            return None

        channel = None
        try:
            channel = bot.get_channel(int(channel_id))
        except Exception:
            channel = None
        return channel

    @staticmethod
    async def _resolve_player_name(bot, guild_id: str, discord_id: str):
        if not bot or not guild_id:
            return f"Player {discord_id}"

        try:
            guild = bot.get_guild(int(guild_id))
        except Exception:
            guild = None

        if not guild:
            return f"Player {discord_id}"

        member = guild.get_member(int(discord_id))
        if member:
            return member.display_name

        fetch_member = getattr(guild, "fetch_member", None)
        if callable(fetch_member):
            try:
                fetched = await fetch_member(int(discord_id))
                if fetched:
                    return fetched.display_name
            except Exception:
                pass

        return f"Player {discord_id}"

    @staticmethod
    async def _resolve_village_name(bot, guild_id: str):
        if not bot or not guild_id:
            return f"Village {guild_id}"

        try:
            guild = bot.get_guild(int(guild_id))
        except Exception:
            guild = None

        if guild and getattr(guild, "name", None):
            return guild.name
        return f"Village {guild_id}"

    @staticmethod
    async def render_announcement(village_id: int, db=None, bot=None, rendered_at: datetime = None):
        close_db = False
        if db is None:
            db = await get_connection()
            close_db = True

        try:
            async with db.execute(
                """
                SELECT food, wood, stone, food_efficiency_xp, storage_capacity_xp, resource_yield_xp, last_announcement_updated
                FROM villages
                WHERE id = ?
                """,
                (village_id,),
            ) as cursor:
                village = await cursor.fetchone()

            if not village:
                return None

            food, wood, stone, food_xp, storage_xp, yield_xp, last_updated_str = village
            storage_capacity = Engine._storage_capacity(storage_xp)
            last_updated = rendered_at or Engine._parse_timestamp(last_updated_str) or datetime.utcnow()
            rich_text_lines = [
                f"(Last Update: <t:{Engine._to_discord_unix(last_updated)}:R>)",
                "",
                f"Village Resources (Cap: {storage_capacity:,})",
                f"🍎 {food:,} | 🪵 {wood:,} | 🪨 {stone:,}",
                "",
                "Village Buildings",
            ]
            building_lines = [
                Engine._building_progress_line(1, food_xp),
                Engine._building_progress_line(2, storage_xp),
                Engine._building_progress_line(3, yield_xp),
            ]

            async with db.execute(
                """
                SELECT
                    p.status,
                    p.target_id,
                    COUNT(*)
                FROM players p
                WHERE p.village_id = ?
                  AND p.status != 'missing'
                GROUP BY p.status, p.target_id
                """,
                (village_id,),
            ) as cursor:
                players = await cursor.fetchall()

            villager_lines = []

            for status, target_id, count in players:
                action_name = await Engine._get_target_description(db, status, target_id)
                villager_lines.append((action_name, int(count)))

            villager_lines.sort(key=lambda item: (-item[1], item[0]))
            villager_text = [f"{action_name}: {count:,}" for action_name, count in villager_lines] or ["(none)"]

            return (
                "\n".join(rich_text_lines)
                + "\n```text\n"
                + "\n".join(building_lines)
                + "\n```"
                + "\n\nActive Villagers"
                + "\n```text\n"
                + "\n".join(villager_text)
                + "\n```"
            )

        finally:
            if close_db:
                await db.close()

    @staticmethod
    async def sync_announcement(village_id: int, db=None, bot=None, force: bool = False, req_id: str = None, user_id=None):
        close_db = False
        if db is None:
            db = await get_connection()
            close_db = True

        try:
            async with db.execute(
                """
                SELECT announcement_channel_id, announcement_message_id, last_announcement_updated
                FROM villages
                WHERE id = ?
                """,
                (village_id,),
            ) as cursor:
                village = await cursor.fetchone()

            if not village:
                return None

            channel_id, message_id, last_updated_str = village
            if not channel_id:
                return None

            now = datetime.utcnow()
            last_updated = Engine._parse_timestamp(last_updated_str) if last_updated_str else None
            if not force and last_updated and (now - last_updated).total_seconds() < 60:
                return None

            channel = await Engine._resolve_channel(bot or Engine.bot, channel_id)
            if channel is None:
                return None

            announcement_text = await Engine.render_announcement(
                village_id,
                db=db,
                bot=bot or Engine.bot,
                rendered_at=now,
            )
            if not announcement_text:
                return None

            message = None
            if message_id:
                try:
                    message = await channel.fetch_message(int(message_id))
                    await message.edit(content=announcement_text)
                except disnake.NotFound:
                    await db.execute(
                        """
                        UPDATE villages
                        SET announcement_message_id = NULL
                        WHERE id = ?
                        """,
                        (village_id,),
                    )
                    message = None
                except Exception as exc:
                    if getattr(exc, "status", None) == 404:
                        await db.execute(
                            """
                            UPDATE villages
                            SET announcement_message_id = NULL
                            WHERE id = ?
                            """,
                            (village_id,),
                        )
                        message = None
                    else:
                        log_event(req_id, user_id, "ERROR", f"Announcement update failed for village {village_id}: {exc}")
                        return None

            if message is None:
                message = await channel.send(announcement_text)
                await db.execute(
                    """
                    UPDATE villages
                    SET announcement_message_id = ?
                    WHERE id = ?
                    """,
                    (str(message.id), village_id),
                )

            await db.execute(
                """
                UPDATE villages
                SET last_announcement_updated = ?
                WHERE id = ?
                """,
                (now.isoformat(), village_id),
            )
            await db.commit()
            log_event(req_id, user_id, "RESP", f"Announcement synced for village {village_id}")
            return message

        finally:
            if close_db:
                await db.close()

    @staticmethod
    async def process_watcher(req_id: str = None):
        watcher_req_id = req_id or new_request_id()
        log_event(watcher_req_id, "SYSTEM", "STATUS", "Watcher sweep started")

        async with get_connection() as db:
            now = datetime.utcnow()
            now_iso = now.isoformat()
            await Engine._mark_missing_players(db, now, req_id=watcher_req_id, user_id="SYSTEM")

            async with db.execute(
                """
                SELECT discord_id, village_id
                FROM players
                WHERE completion_time <= ?
                """,
                (now_iso,),
            ) as cursor:
                players = await cursor.fetchall()

            for player in players:
                await Engine.settle_player(player[0], player[1], db, req_id=watcher_req_id, user_id="SYSTEM")

            async with db.execute("SELECT id FROM villages") as cursor:
                villages = await cursor.fetchall()

            for village in villages:
                await Engine.settle_village(village[0], db, req_id=watcher_req_id, user_id="SYSTEM")

            await db.commit()

        log_event(watcher_req_id, "SYSTEM", "STATUS", "Watcher sweep completed")

    @staticmethod
    @tasks.loop(seconds=300)
    async def start_watcher_loop():
        await Engine.process_watcher()

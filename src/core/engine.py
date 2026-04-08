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
    async def _record_action_logs(db, player_id: int, status: str, target_id: int, start: datetime, end: datetime):
        if start >= end or status == "missing":
            return

        action_type = status
        if status == "gathering":
            action_type = await Engine._resolve_gathering_log_type(db, target_id)

        segments = Engine._chunk_time_range(start, end)
        for seg_start, seg_end in segments:
            await db.execute(
                """
                INSERT INTO player_actions_log (player_id, action_type, start_time, end_time)
                VALUES (?, ?, ?, ?)
                """,
                (player_id, action_type, seg_start.isoformat(), seg_end.isoformat()),
            )

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
            try:
                last_tick = Engine._parse_timestamp(last_tick_time_str)
            except (ValueError, TypeError):
                last_tick = now

            delta = (now - last_tick).total_seconds()
            hours = delta / 3600.0
            active_threshold = (now - timedelta(days=7)).isoformat()

            async with db.execute(
                """
                SELECT count(*)
                FROM players
                WHERE village_id = ?
                  AND (last_message_time >= ? OR status != 'missing')
                """,
                (village_id, active_threshold),
            ) as cursor:
                active_count_row = await cursor.fetchone()

            active_count = active_count_row[0] if active_count_row else 0
            decay = int(hours * (10 + active_count))

            if decay > 0:
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
                        max(0, food_xp - decay),
                        max(0, storage_xp - decay),
                        max(0, yield_xp - decay),
                        now.isoformat(),
                        village_id,
                    ),
                )
                await db.commit()
                log_event(req_id, user_id, "SETTLE", f"Village {village_id} decay applied: {decay} XP")

        finally:
            if close_db:
                await db.close()

    @staticmethod
    async def recalculate_player_stats(player_id: int, db):
        """Recalculates player stats based on the last 150 action log entries."""
        now = datetime.utcnow()
        async with db.execute(
            """
            SELECT action_type, start_time, end_time
            FROM player_actions_log
            WHERE player_id = ?
            ORDER BY end_time DESC, id DESC
            LIMIT 150
            """,
            (player_id,),
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
            INSERT INTO player_stats (player_id, strength, agility, perception, knowledge, endurance, last_calc_time)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(player_id) DO UPDATE SET
                strength = excluded.strength,
                agility = excluded.agility,
                perception = excluded.perception,
                knowledge = excluded.knowledge,
                endurance = excluded.endurance,
                last_calc_time = excluded.last_calc_time
            """,
            (player_id, *final_stats, now.isoformat()),
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
    async def settle_player(player_id: int, db=None, interrupted=False, is_ui_refresh=False, req_id: str = None, user_id=None):
        """Executes settlement for the player's current action."""
        close_db = False
        if db is None:
            db = await get_connection()
            close_db = True

        try:
            async with db.execute(
                """
                SELECT last_update_time, completion_time, status, target_id, village_id
                FROM players
                WHERE id = ?
                """,
                (player_id,),
            ) as cursor:
                player = await cursor.fetchone()

            if not player:
                return None

            last_update_time_str, completion_time_str, status, target_id, village_id = player
            now = datetime.utcnow()

            try:
                last_update = Engine._parse_timestamp(last_update_time_str) or now
            except (ValueError, TypeError):
                last_update = now

            completion_time = None
            target_time = now
            if completion_time_str:
                try:
                    completion_time = Engine._parse_timestamp(completion_time_str)
                    if completion_time is not None:
                        target_time = min(now, completion_time)
                except (ValueError, TypeError):
                    completion_time = None

            p_str, p_agi, p_per, p_kno, p_end = await Engine.recalculate_player_stats(player_id, db)
            delta_seconds = max(0.0, (target_time - last_update).total_seconds())
            time_ratio = Engine._time_ratio(delta_seconds)

            if delta_seconds > 0 and status != "missing":
                await Engine._record_action_logs(db, player_id, status, target_id, last_update, target_time)

            async with db.execute(
                """
                SELECT food, wood, stone, food_efficiency_xp, storage_capacity_xp, resource_yield_xp
                FROM villages
                WHERE id = ?
                """,
                (village_id,),
            ) as cursor:
                village_row = await cursor.fetchone()

            discoveries = []
            if village_row:
                v_food, v_wood, v_stone, _food_eff_xp, v_storage_xp, v_yield_xp = village_row
                storage_capacity = Engine._storage_capacity(v_storage_xp)
                yield_mult = Engine._yield_multiplier(v_yield_xp)

                food_gained, wood_gained, stone_gained = 0, 0, 0

                if status == "idle":
                    efficiency = (p_per + p_kno) / 2.0 / 100.0
                    food_gained = int(20 * efficiency * 0.5 * yield_mult * time_ratio)

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

                        gathered = int(20 * efficiency * (max(10, quality) / 100.0) * yield_mult * time_ratio)
                        actual_gathered = min(gathered, remaining_amount)

                        if actual_gathered > 0:
                            await db.execute(
                                "UPDATE resource_nodes SET remaining_amount = remaining_amount - ? WHERE id = ?",
                                (actual_gathered, target_id),
                            )
                            if node_type == "food":
                                food_gained = actual_gathered
                            elif node_type == "wood":
                                wood_gained = actual_gathered
                            elif node_type == "stone":
                                stone_gained = actual_gathered

                elif status == "building" and target_id:
                    efficiency = (p_kno + p_end) / 2.0 / 100.0
                    xp_gained = int(20 * efficiency * time_ratio)
                    if xp_gained > 0:
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

                elif status == "exploring" and time_ratio > 0:
                    async with db.execute(
                        """
                        SELECT count(*)
                        FROM resource_nodes
                        WHERE village_id = ?
                          AND remaining_amount > 0
                          AND expiry_time > ?
                        """,
                        (village_id, now.isoformat()),
                    ) as cursor:
                        active_nodes_row = await cursor.fetchone()

                    active_nodes = active_nodes_row[0] if active_nodes_row else 0
                    discovery_chance = min(1.0, time_ratio) * (1.0 / (1.0 + (active_nodes ** 2)))
                    if random.random() < discovery_chance:
                        perception_knowledge = p_per + p_kno
                        node_type = random.choice(["food", "wood", "stone"])
                        quality = max(10, int(random.gauss((p_per + p_kno) / 2.0, 50)))
                        stock = random.randint(perception_knowledge * 10, perception_knowledge * 20)
                        expiry = now + timedelta(hours=48)

                        await db.execute(
                            """
                            INSERT INTO resource_nodes (
                                village_id, type, quality, remaining_amount, expiry_time
                            )
                            VALUES (?, ?, ?, ?, ?)
                            """,
                            (village_id, node_type, quality, stock, expiry.isoformat()),
                        )
                        discoveries.append(
                            {
                                "type": node_type,
                                "quality": quality,
                                "remaining_amount": stock,
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
                            f"Player {player_id} settled {status}: "
                            f"food={food_gained}, wood={wood_gained}, stone={stone_gained}, "
                            f"time_ratio={time_ratio:.2f}"
                        ),
                    )

            new_status = status
            new_target = target_id
            new_completion = None

            async with db.execute("SELECT last_message_time FROM players WHERE id = ?", (player_id,)) as cursor:
                last_message_row = await cursor.fetchone()

            if last_message_row:
                last_message_time = Engine._parse_timestamp(last_message_row[0])
                if last_message_time and (now - last_message_time).days >= 7 and (now - target_time).days >= 7:
                    new_status = "missing"
                    new_target = None

            if interrupted and new_status != "missing":
                new_status = "idle"
                new_target = None

            if new_status == "missing":
                new_completion = None
            elif (
                not interrupted
                and status not in ("missing", "idle")
                and completion_time is not None
                and target_time >= completion_time
            ):
                restarted = await Engine.start_action(
                    player_id,
                    status,
                    target_id,
                    db,
                    req_id=req_id,
                    user_id=user_id,
                )
                if restarted:
                    await db.commit()
                    for discovery in discoveries:
                        await Engine.send_discovery_announcement(
                            village_id,
                            player_id,
                            discovery,
                            bot=Engine.bot,
                            req_id=req_id,
                        )
                    await Engine.sync_announcement(village_id, db=db, bot=Engine.bot, req_id=req_id, user_id=user_id)
                    return {"discoveries": discoveries, "status": status}
                new_status = "idle"
                new_target = None
            elif (
                not interrupted
                and status not in ("missing", "idle")
                and completion_time is not None
                and target_time < completion_time
            ):
                new_completion = completion_time_str

            if interrupted or new_status in ("idle", "missing") or (completion_time is None and status == "idle") or is_ui_refresh:
                await db.execute(
                    """
                    UPDATE players
                    SET status = ?, target_id = ?, last_update_time = ?, completion_time = ?
                    WHERE id = ?
                    """,
                    (new_status, new_target, now.isoformat(), new_completion, player_id),
                )

            await db.commit()

            if new_status != status or new_target != target_id:
                log_event(
                    req_id,
                    user_id,
                    "STATUS",
                    f"Player {player_id} status changed from {status} to {new_status}",
                )

            for discovery in discoveries:
                await Engine.send_discovery_announcement(
                    village_id,
                    player_id,
                    discovery,
                    bot=Engine.bot,
                    req_id=req_id,
                )

            await Engine.sync_announcement(village_id, db=db, bot=Engine.bot, req_id=req_id, user_id=user_id)
            return {"discoveries": discoveries, "status": new_status}

        finally:
            if close_db:
                await db.close()

    @staticmethod
    async def start_action(player_id: int, action: str, target_id: int = None, db=None, req_id: str = None, user_id=None) -> bool:
        """Attempts to start an action cycle and pre-deduct village resources."""
        close_db = False
        if db is None:
            db = await get_connection()
            close_db = True

        try:
            async with db.execute("SELECT village_id FROM players WHERE id = ?", (player_id,)) as cursor:
                player_row = await cursor.fetchone()

            if not player_row:
                return False

            village_id = player_row[0]
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
                return False

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
                    return False
                async with db.execute(
                    "SELECT remaining_amount, expiry_time FROM resource_nodes WHERE id = ?",
                    (target_id,),
                ) as cursor:
                    node = await cursor.fetchone()
                if not node:
                    return False
                remaining_amount, expiry_time_str = node
                if remaining_amount <= 0:
                    return False
                expiry_time = Engine._parse_timestamp(expiry_time_str)
                if expiry_time and datetime.utcnow() >= expiry_time:
                    return False

            if action == "building" and not target_id:
                return False

            if v_food < food_cost or v_wood < wood_cost or v_stone < stone_cost:
                log_event(
                    req_id,
                    user_id,
                    "ERROR",
                    (
                        f"Player {player_id} could not start {action}: "
                        f"food={v_food}/{food_cost}, wood={v_wood}/{wood_cost}, stone={v_stone}/{stone_cost}"
                    ),
                )
                return False

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
                        f"Player {player_id} started {action}: "
                        f"food={food_cost}, wood={wood_cost}, stone={stone_cost}"
                    ),
                )

            now = datetime.utcnow()
            completion_time = now + timedelta(minutes=Engine._action_cycle_minutes())
            await db.execute(
                """
                UPDATE players
                SET status = ?, target_id = ?, last_update_time = ?, completion_time = ?
                WHERE id = ?
                """,
                (action, target_id, now.isoformat(), completion_time.isoformat(), player_id),
            )
            await db.commit()
            log_event(
                req_id,
                user_id,
                "STATUS",
                f"Player {player_id} entered {action} until {completion_time.isoformat()}",
            )
            return True

        finally:
            if close_db:
                await db.close()

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
    async def render_announcement(village_id: int, db=None, bot=None):
        close_db = False
        if db is None:
            db = await get_connection()
            close_db = True

        try:
            async with db.execute(
                """
                SELECT guild_id, food, wood, stone, food_efficiency_xp, storage_capacity_xp, resource_yield_xp
                FROM villages
                WHERE id = ?
                """,
                (village_id,),
            ) as cursor:
                village = await cursor.fetchone()

            if not village:
                return None

            guild_id, food, wood, stone, food_xp, storage_xp, yield_xp = village
            village_name = await Engine._resolve_village_name(bot or Engine.bot, guild_id)
            storage_capacity = Engine._storage_capacity(storage_xp)
            building_line = " | ".join(
                [
                    f"{Engine.BUILDING_NAMES[idx]} Lv{Engine._building_level_from_xp(xp)}"
                    for idx, xp in ((1, food_xp), (2, storage_xp), (3, yield_xp))
                ]
            )

            async with db.execute(
                """
                SELECT
                    p.id,
                    p.discord_id,
                    p.status,
                    p.target_id,
                    p.last_update_time,
                    p.completion_time,
                    COALESCE(ps.strength, 50),
                    COALESCE(ps.agility, 50),
                    COALESCE(ps.perception, 50),
                    COALESCE(ps.knowledge, 50),
                    COALESCE(ps.endurance, 50)
                FROM players p
                LEFT JOIN player_stats ps ON ps.player_id = p.id
                WHERE p.village_id = ?
                  AND p.status != 'missing'
                ORDER BY p.last_update_time DESC
                LIMIT 20
                """,
                (village_id,),
            ) as cursor:
                players = await cursor.fetchall()

            lines = [
                f"=== [ {village_name} ] STATUS REPORT ===",
                f"Resources: 食物 {food:,} | 木頭 {wood:,} | 石頭 {stone:,} (Cap: {storage_capacity:,})",
                f"Buildings: {building_line}",
                "",
                "--- ACTIVE VILLAGERS (Sorted by latest action) ---",
            ]

            for row in players:
                (
                    player_id,
                    discord_id,
                    status,
                    target_id,
                    _last_update,
                    _completion_time,
                    strength,
                    agility,
                    perception,
                    knowledge,
                    endurance,
                ) = row
                name = await Engine._resolve_player_name(bot or Engine.bot, guild_id, discord_id)
                display_name = name[:12]
                status_text = await Engine._get_target_description(db, status, target_id)
                lines.append(
                    (
                        f"{display_name:<12} | "
                        f"STR {strength:<3} AGI {agility:<3} PER {perception:<3} KNO {knowledge:<3} END {endurance:<3} | "
                        f"{status_text}"
                    )
                )

            lines.append(f"(Last Update: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC)")

            while players and len("```text\n" + "\n".join(lines) + "\n```") > 2000:
                players = players[:-1]
                lines = lines[:5]
                for row in players:
                    (
                        _player_id,
                        discord_id,
                        status,
                        target_id,
                        _last_update,
                        _completion_time,
                        strength,
                        agility,
                        perception,
                        knowledge,
                        endurance,
                    ) = row
                    name = await Engine._resolve_player_name(bot or Engine.bot, guild_id, discord_id)
                    display_name = name[:12]
                    status_text = await Engine._get_target_description(db, status, target_id)
                    lines.append(
                        (
                            f"{display_name:<12} | "
                            f"STR {strength:<3} AGI {agility:<3} PER {perception:<3} KNO {knowledge:<3} END {endurance:<3} | "
                            f"{status_text}"
                        )
                    )
                lines.append(f"(Last Update: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC)")

            return "```text\n" + "\n".join(lines) + "\n```"

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

            announcement_text = await Engine.render_announcement(village_id, db=db, bot=bot or Engine.bot)
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
    async def send_discovery_announcement(village_id: int, player_id: int, discovery: dict, bot=None, req_id: str = None):
        if not discovery:
            return None

        async with get_connection() as db:
            async with db.execute(
                """
                SELECT guild_id, announcement_channel_id
                FROM villages
                WHERE id = ?
                """,
                (village_id,),
            ) as cursor:
                village = await cursor.fetchone()

            if not village:
                return None

            guild_id, channel_id = village
            if not channel_id:
                return None

            async with db.execute("SELECT discord_id FROM players WHERE id = ?", (player_id,)) as cursor:
                player = await cursor.fetchone()

        channel = await Engine._resolve_channel(bot or Engine.bot, channel_id)
        if channel is None:
            return None

        player_name = "A villager"
        if player:
            player_name = await Engine._resolve_player_name(bot or Engine.bot, guild_id, player[0])

        message = (
            f"New discovery by {player_name}: "
            f"{discovery['type'].title()} node "
            f"(Quality {discovery['quality']}%, Stock {discovery['remaining_amount']})"
        )
        try:
            sent_message = await channel.send(message)
            log_event(req_id, "SYSTEM", "RESP", f"Discovery announcement sent for village {village_id}")
            return sent_message
        except Exception as exc:
            log_event(req_id, "SYSTEM", "ERROR", f"Discovery announcement failed for village {village_id}: {exc}")
            return None

    @staticmethod
    async def process_watcher(req_id: str = None):
        watcher_req_id = req_id or new_request_id()
        log_event(watcher_req_id, "SYSTEM", "STATUS", "Watcher sweep started")

        async with get_connection() as db:
            now = datetime.utcnow().isoformat()
            await db.execute("DELETE FROM resource_nodes WHERE expiry_time <= ? OR remaining_amount <= 0", (now,))

            async with db.execute("SELECT id FROM players WHERE completion_time <= ?", (now,)) as cursor:
                players = await cursor.fetchall()

            for player in players:
                await Engine.settle_player(player[0], db, req_id=watcher_req_id, user_id="SYSTEM")

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

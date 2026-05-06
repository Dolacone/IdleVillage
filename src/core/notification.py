"""
notification.py — Public event notification and dashboard update helpers.

Sends settlement and gear events to the village announcement channel, and
edits the dashboard message after each watcher settlement pass.

Usage:
    from core import notification
    await notification.dispatch_events(bot, events)
    await notification.update_dashboard(bot)
"""

import logging
from datetime import datetime, timezone

import disnake
from core.config import get_env_float, get_env_int
from cogs.ui_renderer import BUILDING_LABELS, GEAR_LABELS, STAGE_TYPE_LABELS

logger = logging.getLogger(__name__)


async def _fetch_village_dashboard_data(db) -> tuple[dict, dict, dict, list]:
    async with db.execute("SELECT * FROM stage_state WHERE id=1") as cur:
        row = await cur.fetchone()
        cols = [d[0] for d in cur.description]
        stage_data = dict(zip(cols, row)) if row else {}

    resources: dict = {}
    async with db.execute("SELECT resource_type, amount FROM village_resources") as cur:
        async for r in cur:
            resources[r[0]] = r[1]

    buildings: dict = {}
    async with db.execute(
        "SELECT building_type, level, xp_progress FROM buildings"
    ) as cur:
        async for r in cur:
            buildings[r[0]] = {"level": r[1], "xp_progress": r[2]}

    action_counts: list = []
    async with db.execute(
        "SELECT action, action_target, COUNT(*) FROM players"
        " WHERE action IS NOT NULL GROUP BY action, action_target"
    ) as cur:
        async for r in cur:
            action_counts.append((r[0], r[1], r[2]))

    return stage_data, resources, buildings, action_counts


async def _clear_dashboard_reference(channel_id: str, message_id: str) -> None:
    from database.schema import get_connection

    async with get_connection() as db:
        await db.execute(
            """
            UPDATE village_state
            SET dashboard_channel_id=NULL, dashboard_message_id=NULL, updated_at=?
            WHERE id=1 AND dashboard_channel_id=? AND dashboard_message_id=?
            """,
            (datetime.now(timezone.utc).isoformat(), channel_id, message_id),
        )
        await db.commit()


# ---------------------------------------------------------------------------
# Internal formatting
# ---------------------------------------------------------------------------

def _pct(progress: int, target: int) -> int:
    if target <= 0:
        return 0
    return round(progress / target * 100)


def _format_event(event: dict) -> str | None:
    """Return a formatted notification string for the given event dict, or None to skip."""
    kind = event.get("type")

    if kind == "stage_clear":
        cleared = event["stages_cleared"]
        next_type = event.get("next_stage_type", "")
        next_target = event.get("next_target", 0)
        next_name = STAGE_TYPE_LABELS.get(next_type, next_type)
        return (
            f"通過第 {cleared} 關\n"
            f"下一目標：{next_name}\n"
            f"目標需求：{next_target}"
        )

    if kind == "upgrade_stage_clear":
        round_n = event["round"]
        old_cap = event["old_cap"]
        new_cap = event["new_cap"]
        next_type = event.get("next_stage_type", "")
        next_target = event.get("next_target", 0)
        next_name = STAGE_TYPE_LABELS.get(next_type, next_type)
        return (
            f"升級關通關，第 {round_n} 輪完成\n"
            f"建築等級上限從 Lv{old_cap} 變成 Lv{new_cap}\n"
            f"下一目標：{next_name}\n"
            f"目標需求：{next_target}"
        )

    if kind == "building_upgrade":
        btype = event["building_type"]
        old_lv = event["old_level"]
        new_lv = event["new_level"]
        next_req = event.get("next_xp_req", "?")
        bname = BUILDING_LABELS.get(btype, btype)
        return (
            f"{bname} 從 Lv{old_lv} 變成 Lv{new_lv}\n"
            f"下一等級需求：{next_req}"
        )

    if kind == "overtime":
        stages_cleared = event["stages_cleared"]
        progress = event["progress"]
        target = event["target"]
        overtime_secs = get_env_int("STAGE_OVERTIME_SECONDS")
        multiplier = get_env_float("STAGE_OVERTIME_PROGRESS_MULTIPLIER")
        pct = _pct(progress, target)
        stage_n = stages_cleared + 1
        return (
            f"第 {stage_n} 關已超過 {overtime_secs} 秒\n"
            f"後續貢獻計入關卡進度時將乘上 {multiplier}\n"
            f"目前進度：{progress} / {target}（{pct}%）"
        )

    if kind == "gear_success":
        user_name = event.get("user_display_name", "")
        gear_type = event.get("gear_type", "")
        current_level = event.get("current_level", 0)
        target_level = event.get("target_level", current_level + 1)
        failure_count = event.get("failure_count", 0)
        gear_name = GEAR_LABELS.get(gear_type, gear_type)
        return (
            f"{user_name} 的 {gear_name} 升級成功 :tada: "
            f"Lv{current_level} -> Lv{target_level}（總失敗次數：{failure_count}）"
        )

    if kind == "gear_fail":
        user_name = event.get("user_display_name", "")
        gear_type = event.get("gear_type", "")
        current_level = event.get("current_level", 0)
        target_level = event.get("target_level", current_level + 1)
        failure_count = event.get("failure_count", 0)
        gear_name = GEAR_LABELS.get(gear_type, gear_type)
        return (
            f"{user_name} 的 {gear_name} 升級失敗 :boom: "
            f"Lv{current_level} -> Lv{target_level}（總失敗次數：{failure_count}）"
        )

    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def dispatch_events(bot, events: list[dict]) -> None:
    """
    Send formatted notification messages to the announcement channel.
    Silently skips if channel is not configured or not accessible.
    """
    if not events:
        return

    from database.schema import get_connection

    async with get_connection() as db:
        async with db.execute("SELECT announcement_channel_id FROM village_state") as cur:
            row = await cur.fetchone()

    if row is None or not row[0]:
        return

    channel_id = int(row[0])
    channel = bot.get_channel(channel_id)
    if channel is None:
        logger.warning("Announcement channel %d not found or not cached", channel_id)
        return

    for event in events:
        text = _format_event(event)
        if text:
            try:
                await channel.send(text)
            except Exception as exc:
                logger.error("Failed to send notification for event %s: %s", event.get("type"), exc)


async def update_dashboard(bot) -> None:
    """
    Edit the pinned dashboard message with the current village embed.
    Silently skips if dashboard is not configured or message is inaccessible.
    """
    from database.schema import get_connection
    from cogs.ui_renderer import build_village_embed

    async with get_connection() as db:
        async with db.execute(
            "SELECT dashboard_channel_id, dashboard_message_id FROM village_state"
        ) as cur:
            row = await cur.fetchone()
        stage_data, resources, buildings, action_counts = (
            await _fetch_village_dashboard_data(db)
        )

    if row is None or not row[0] or not row[1]:
        return

    dashboard_channel_id = row[0]
    dashboard_message_id = row[1]
    channel_id = int(dashboard_channel_id)
    message_id = int(dashboard_message_id)
    channel = bot.get_channel(channel_id)
    if channel is None:
        logger.warning("Dashboard channel %d not found or not cached", channel_id)
        return

    try:
        message = await channel.fetch_message(message_id)
        embed = build_village_embed(stage_data, resources, buildings, action_counts)
        await message.edit(embed=embed)
    except disnake.NotFound:
        await _clear_dashboard_reference(dashboard_channel_id, dashboard_message_id)
    except Exception as exc:
        logger.error("Failed to update dashboard: %s", exc)

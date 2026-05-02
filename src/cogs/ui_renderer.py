"""
ui_renderer.py — pure rendering functions for Discord embeds and components.
No database access. All data passed as plain dicts/lists.
"""

import math
from datetime import datetime, timezone

import disnake

from core.config import get_env_float, get_env_int

ACTION_LABELS = {
    "gathering": "採集",
    "building": "建設",
    "combat": "戰鬥",
    "research": "研究",
}
ACTION_DESCRIPTIONS = {
    "gathering": "產出 🌾食物 + 🪵木頭",
    "building": "消耗 🪵木頭 | 產出 建築XP",
    "combat": "消耗 🪵木頭 | 產出 🧠知識",
    "research": "消耗 🧠知識 | 產出 研究所XP",
}
ACTION_EMOJIS = {
    "gathering": "🌾",
    "building": "🔨",
    "combat": "⚔️",
    "research": "🔬",
}
BUILDING_LABELS = {
    "gathering_field": "採集場",
    "workshop": "加工廠",
    "hunting_ground": "狩獵場",
    "research_lab": "研究所",
}
GEAR_LABELS = {
    "gathering": "採集裝備",
    "building": "建設工具",
    "combat": "戰鬥裝備",
    "research": "研究裝備",
}
STAGE_TYPE_LABELS = {
    "gathering": "採集",
    "building": "建設",
    "combat": "戰鬥",
    "research": "研究",
    "upgrade": "升級",
}
RESOURCE_LABELS = {"food": "食物", "wood": "木頭", "knowledge": "知識"}
RESOURCE_EMOJIS = {"food": "🌾", "wood": "🪵", "knowledge": "🧠"}

# Valid building targets for the action dropdown (research_lab is facility for research, not a build target)
UI_BUILDING_TARGETS = ("gathering_field", "workshop", "hunting_ground")


def _progress_bar(progress: int, target: int, width: int = 10) -> str:
    if target <= 0:
        return "░" * width
    filled = min(width, math.floor(progress / max(target, 1) * width))
    return "█" * filled + "░" * (width - filled)


def _unix_from_iso(iso_str: str) -> int:
    if not iso_str:
        return 0
    try:
        dt = datetime.fromisoformat(iso_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    except (ValueError, TypeError):
        return 0


def _action_display_name(action: str, action_target: str | None = None) -> str:
    if action == "building" and action_target:
        target_name = BUILDING_LABELS.get(action_target, action_target)
        return f"建設（{target_name}）"
    return ACTION_LABELS.get(action, action)


def _build_village_section(
    stage_data: dict, resources: dict, buildings: dict, action_counts: list
) -> str:
    """
    Return the village status block as a text string.
    action_counts: list of (action, action_target, count) tuples.
    """
    unix_ts = _unix_from_iso(stage_data.get("updated_at", ""))

    stages_cleared = stage_data.get("stages_cleared", 0)
    stage_type = stage_data.get("current_stage_type", "gathering")
    stage_name = STAGE_TYPE_LABELS.get(stage_type, stage_type)
    progress = stage_data.get("current_stage_progress", 0)
    target = stage_data.get("current_stage_target", 1)
    pct = math.floor(progress / max(target, 1) * 100)
    bar = _progress_bar(progress, target)

    stage_started_unix = _unix_from_iso(stage_data.get("stage_started_at", ""))
    overtime_secs = get_env_int("STAGE_OVERTIME_SECONDS")
    deadline_unix = stage_started_unix + overtime_secs

    now_ts = int(datetime.now(timezone.utc).timestamp())
    is_overtime = stage_started_unix > 0 and (now_ts - stage_started_unix) > overtime_secs
    overtime_line = "   ⚠️ 逾時！通關效率已降低（產出計分 ×0.5）\n" if is_overtime else ""

    food = resources.get("food", 0)
    wood = resources.get("wood", 0)
    knowledge = resources.get("knowledge", 0)

    level_cap = stages_cleared // 5 + 1
    xp_per_level = get_env_int("BUILDING_XP_PER_LEVEL")
    building_lines = []
    for btype, blabel in [
        ("gathering_field", "🌾 採集場"),
        ("workshop", "🔨 加工廠"),
        ("hunting_ground", "⚔️ 狩獵場"),
        ("research_lab", "🔬 研究所"),
    ]:
        b = buildings.get(btype, {"level": 0, "xp_progress": 0})
        blevel = b.get("level", 0)
        bxp = b.get("xp_progress", 0)
        next_req = (blevel + 1) * xp_per_level
        bpct = math.floor(bxp / max(next_req, 1) * 100)
        building_lines.append(f"{blabel} Lv{blevel} ({bpct}%)")

    sorted_counts = sorted(action_counts, key=lambda x: (-x[2], x[0]))
    action_lines = [_action_display_name(a, t) + f": {c}" for a, t, c in sorted_counts]
    action_block = "\n".join(action_lines) if action_lines else "（無）"

    building_block = "\n".join(building_lines)
    return (
        f"(Last Update: <t:{unix_ts}:R>)\n\n"
        f"**Idle Village**\n\n"
        f"📋 關卡 {stages_cleared}: {stage_name}\n"
        f"   {bar}  {progress} / {target} ({pct}%)\n"
        f"   ⏰ 期限: <t:{deadline_unix}:R>\n"
        f"{overtime_line}"
        f"\n公用資源\n"
        f"🌾 {food} | 🪵 {wood} | 🧠 {knowledge}\n"
        f"\n公用設施 (等級上限：Lv{level_cap})\n"
        f"{building_block}\n"
        f"\n村民行動\n"
        f"```\n{action_block}\n```"
    )


def build_village_embed(
    stage_data: dict, resources: dict, buildings: dict, action_counts: list
) -> disnake.Embed:
    text = _build_village_section(stage_data, resources, buildings, action_counts)
    return disnake.Embed(description=text, color=disnake.Color.blue())


def build_main_embed(
    stage_data: dict,
    resources: dict,
    buildings: dict,
    action_counts: list,
    player_row: dict,
) -> disnake.Embed:
    village_text = _build_village_section(stage_data, resources, buildings, action_counts)

    gear_parts = [
        f"{ACTION_EMOJIS[a]} {player_row.get(f'gear_{a}', 0)}"
        for a in ("gathering", "building", "combat", "research")
    ]
    mat_parts = [
        f"{ACTION_EMOJIS[a]} {player_row.get(f'materials_{a}', 0)}"
        for a in ("gathering", "building", "combat", "research")
    ]

    action = player_row.get("action")
    action_target = player_row.get("action_target")
    completion_time_str = player_row.get("completion_time")
    if action:
        emoji = ACTION_EMOJIS.get(action, "")
        display = _action_display_name(action, action_target)
        ct_unix = _unix_from_iso(completion_time_str or "")
        if ct_unix:
            action_line = f"🏃 行動：{emoji}{display}（下次結算：<t:{ct_unix}:R>）"
        else:
            action_line = f"🏃 行動：{emoji}{display}"
    else:
        action_line = "🏃 行動：（未設定）"

    ap = player_row.get("_ap", 0)
    ap_cap = get_env_int("AP_CAP")

    player_section = (
        f"\n**個人資訊**\n"
        f"🏅 裝備：{' | '.join(gear_parts)}\n"
        f"🎒 素材：{' | '.join(mat_parts)}\n"
        f"{action_line}\n"
        f"⚡ AP：{ap} / {ap_cap}"
    )

    return disnake.Embed(description=village_text + player_section, color=disnake.Color.blue())


def build_main_components(
    player_row: dict,
    buildings: dict,
    *,
    pending_action: str | None = None,
    pending_target: str | None = None,
) -> list:
    ap = player_row.get("_ap", 0)
    gear_cap = buildings.get("research_lab", {}).get("level", 0)
    all_gear_at_cap = all(
        player_row.get(f"gear_{gear_type}", 0) >= gear_cap
        for gear_type in ("gathering", "building", "combat", "research")
    )

    action_options = [
        disnake.SelectOption(
            label=f"{ACTION_EMOJIS[a]} {ACTION_LABELS[a]}",
            value=a,
            description=ACTION_DESCRIPTIONS[a],
            default=(pending_action == a),
        )
        for a in ("gathering", "building", "combat", "research")
    ]
    rows = [
        disnake.ui.ActionRow(
            disnake.ui.Button(
                label="⚡ 消耗AP立刻完成三次行動",
                style=disnake.ButtonStyle.primary,
                custom_id="burst_execute",
                disabled=(ap < 1 or player_row.get("action") is None),
            ),
            disnake.ui.Button(
                label="🔨 強化裝備",
                style=disnake.ButtonStyle.primary,
                custom_id="open_gear_upgrade",
                disabled=(ap < 1 or all_gear_at_cap),
            ),
        ),
        disnake.ui.ActionRow(
            disnake.ui.StringSelect(
                custom_id="action_select",
                placeholder="選擇行動...",
                options=action_options,
            )
        ),
    ]

    if pending_action == "building":
        xp_per_level = get_env_int("BUILDING_XP_PER_LEVEL")
        target_options = []
        for btype in UI_BUILDING_TARGETS:
            b = buildings.get(btype, {"level": 0, "xp_progress": 0})
            blevel = b.get("level", 0)
            bxp = b.get("xp_progress", 0)
            next_req = (blevel + 1) * xp_per_level
            target_options.append(
                disnake.SelectOption(
                    label=f"{BUILDING_LABELS[btype]} Lv{blevel}",
                    value=btype,
                    description=f"XP: {bxp}/{next_req}",
                    default=(pending_target == btype),
                )
            )
        rows.append(
            disnake.ui.ActionRow(
                disnake.ui.StringSelect(
                    custom_id="building_target_select",
                    placeholder="選擇建設目標...",
                    options=target_options,
                )
            )
        )

    confirm_enabled = pending_action is not None and (
        pending_action != "building" or pending_target is not None
    )
    if pending_action == "building" and pending_target:
        confirm_id = f"confirm_action:building:{pending_target}"
    elif pending_action and pending_action != "building":
        confirm_id = f"confirm_action:{pending_action}"
    else:
        confirm_id = "confirm_action:none"

    rows.append(
        disnake.ui.ActionRow(
            disnake.ui.Button(
                label="✅ 確認行動",
                style=disnake.ButtonStyle.success,
                custom_id=confirm_id,
                disabled=not confirm_enabled,
            )
        )
    )

    return rows


def build_gear_embed(
    upgrade_info: dict, gear_type: str, result: dict | None = None
) -> disnake.Embed:
    label = GEAR_LABELS.get(gear_type, gear_type)
    emoji = ACTION_EMOJIS.get(gear_type, "")
    mat_label = f"{emoji} {ACTION_LABELS.get(gear_type, gear_type)} 素材"

    gear_level = upgrade_info.get("gear_level", 0)
    target_level = upgrade_info.get("target_level", gear_level + 1)
    rate = upgrade_info.get("rate", 0.0)
    pity = upgrade_info.get("pity", 0)
    material_cost = upgrade_info.get("material_cost", target_level)
    gear_cap = upgrade_info.get("gear_cap", 0)
    ap = upgrade_info.get("ap", 0)
    materials = upgrade_info.get("materials", 0)
    ap_cap = get_env_int("AP_CAP")

    pity_bonus_per = get_env_float("GEAR_PITY_BONUS")
    base_rate = max(
        get_env_float("GEAR_MIN_SUCCESS_RATE"),
        1.0 - gear_level * get_env_float("GEAR_RATE_LOSS_PER_LEVEL"),
    )
    final_rate = min(1.0, base_rate + pity * pity_bonus_per)
    base_rate_pct = math.floor(base_rate * 100)
    final_rate_pct = math.floor(final_rate * 100)
    pity_display = math.floor(pity_bonus_per * 100)

    lines = [
        "🔨 裝備強化",
        "─────────────────────────────",
        f"{label}：Lv{gear_level} → Lv{target_level}",
        f"成功率：{base_rate_pct}%（+{pity}×{pity_display}% 保底）= {final_rate_pct}%",
        f"消耗：⚡ 1 AP + {material_cost} 個 {mat_label}",
        f"持有素材：{materials} 個",
        f"⚡ AP：{ap} / {ap_cap}",
        f"裝備等級上限：Lv{gear_cap}（研究所 Lv{gear_cap}）",
    ]

    if result is not None:
        if result.get("success"):
            lines.append(f"\n✅ 強化成功！{label} 升至 Lv{result.get('new_level', target_level)}")
        else:
            lines.append("\n❌ 強化失敗。保底計數 +1")

    color = disnake.Color.green() if (result and result.get("success")) else disnake.Color.blue()
    return disnake.Embed(description="\n".join(lines), color=color)


def build_gear_components(
    gear_type: str,
    can_attempt: bool,
    player_gear: dict,
    gear_cap: int,
) -> list:
    bonus_pct = math.floor(get_env_float("GEAR_BONUS_PER_LEVEL") * 100)

    def gear_description(g: str) -> str:
        current = player_gear.get(g, 0)
        if current >= gear_cap:
            return f"已達等級上限 Lv{gear_cap}"
        current_total = current * bonus_pct
        next_total = (current + 1) * bonus_pct
        return (
            f"Lv{current} → Lv{current + 1}: "
            f"{ACTION_LABELS[g]}產出 +{current_total}% → +{next_total}%"
        )

    gear_options = [
        disnake.SelectOption(
            label=f"{ACTION_EMOJIS[g]} {GEAR_LABELS[g]}",
            value=g,
            description=gear_description(g),
            default=(gear_type == g),
        )
        for g in ("gathering", "building", "combat", "research")
    ]
    return [
        disnake.ui.ActionRow(
            disnake.ui.StringSelect(
                custom_id="gear_type_select",
                placeholder="選擇裝備類型...",
                options=gear_options,
            )
        ),
        disnake.ui.ActionRow(
            disnake.ui.Button(
                label="🎲 強化",
                style=disnake.ButtonStyle.success,
                custom_id=f"attempt_upgrade:{gear_type}",
                disabled=not can_attempt,
            ),
            disnake.ui.Button(
                label="← 返回",
                style=disnake.ButtonStyle.secondary,
                custom_id="back_to_main",
            ),
        ),
    ]


def build_admin_embed(resource_type: str, amount: int) -> disnake.Embed:
    label = RESOURCE_LABELS.get(resource_type, resource_type)
    emoji = RESOURCE_EMOJIS.get(resource_type, "")
    text = f"⚙️ 資源管理\n\n當前 {emoji} {label}：{amount}"
    return disnake.Embed(description=text, color=disnake.Color(0xFFA500))


def build_admin_components(resource_type: str) -> list:
    small = get_env_int("ADMIN_RESOURCE_DELTA_SMALL")
    large = get_env_int("ADMIN_RESOURCE_DELTA_LARGE")
    resource_options = [
        disnake.SelectOption(
            label=f"{RESOURCE_EMOJIS[r]} {RESOURCE_LABELS[r]}",
            value=r,
            default=(resource_type == r),
        )
        for r in ("food", "wood", "knowledge")
    ]
    return [
        disnake.ui.ActionRow(
            disnake.ui.StringSelect(
                custom_id="resource_select",
                placeholder="選擇資源類型...",
                options=resource_options,
            )
        ),
        disnake.ui.ActionRow(
            disnake.ui.Button(
                label=f"+{small}",
                style=disnake.ButtonStyle.success,
                custom_id=f"resource_add_small:{resource_type}",
            ),
            disnake.ui.Button(
                label=f"+{large}",
                style=disnake.ButtonStyle.success,
                custom_id=f"resource_add_large:{resource_type}",
            ),
            disnake.ui.Button(
                label=f"-{small}",
                style=disnake.ButtonStyle.danger,
                custom_id=f"resource_sub_small:{resource_type}",
            ),
            disnake.ui.Button(
                label=f"-{large}",
                style=disnake.ButtonStyle.danger,
                custom_id=f"resource_sub_large:{resource_type}",
            ),
            disnake.ui.Button(
                label="Set Custom",
                style=disnake.ButtonStyle.secondary,
                custom_id=f"resource_set_custom:{resource_type}",
            ),
        ),
    ]

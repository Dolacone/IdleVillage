"""
ui_renderer.py — pure rendering functions for Discord embeds and components.
No database access. All data passed as plain dicts/lists.
"""

import math
from datetime import datetime, timezone

import disnake

from core.config import get_env_float, get_env_int
from core.formula import ACTION_FACILITY_BUILDING

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
    "gathering": "採集工具",
    "building": "建設工具",
    "combat": "狩獵工具",
    "research": "研究工具",
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
REDUCE_AFFIX_TYPES = {"upgrade_cost_reduce"}

AFFIX_TYPE_LABELS = {
    "efficiency": "效率",
    "material_drop": "素材掉落",
    "upgrade_success": "強化成功率",
    "upgrade_cost_reduce": "強化素材減免",
    "upgrade_ap_refund": "強化AP退還",
    "upgrade_material_refund": "強化素材退還",
    "cycle_time_reduce": "週期縮短",
}

# Valid building targets for the action dropdown (research_lab is facility for research, not a build target)
UI_BUILDING_TARGETS = ("gathering_field", "workshop", "hunting_ground")


def _progress_bar(progress: int, target: int, width: int = 10) -> str:
    if target <= 0:
        return "░" * width
    filled = min(width, math.floor(progress / max(target, 1) * width))
    return "█" * filled + "░" * (width - filled)


def _rate_percent(rate: float) -> int:
    return math.floor(round(rate * 100, 10))


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


def _build_trial_line(trial_data: dict, resources: dict, now_ts: int) -> str:
    """
    Return the "🏆 試煉" status line (with a leading newline). Always shown:
    progress while active, otherwise one of openable/insufficient-resources/cooldown.
    trial_data: current trial_state row, or {} if there is no active trial.
        When inactive, it may still carry "ended_at" from the most recent
        trial, used for the cooldown check below.
    """
    if trial_data.get("is_active"):
        trial_progress = trial_data.get("progress", 0)
        trial_target = trial_data.get("target", 1)
        trial_pct = math.floor(trial_progress / max(trial_target, 1) * 100)
        trial_bar = _progress_bar(trial_progress, trial_target)
        trial_deadline_unix = _unix_from_iso(trial_data.get("started_at", "")) + get_env_int("TRIAL_DURATION_SECONDS")
        return (
            f"\n🏆 試煉 {trial_progress} / {trial_target} ({trial_pct}%)\n"
            f"   {trial_bar}\n"
            f"   ⏰ 期限: <t:{trial_deadline_unix}:R>\n"
        )

    trial_reopen_unix = None
    ended_at_str = trial_data.get("ended_at")
    if ended_at_str:
        cooldown = get_env_int("TRIAL_COOLDOWN_SECONDS")
        ended_unix = _unix_from_iso(ended_at_str)
        if (now_ts - ended_unix) < cooldown:
            trial_reopen_unix = ended_unix + cooldown

    if trial_reopen_unix is not None:
        return f"\n🏆 試煉 ⏳ 可於 <t:{trial_reopen_unix}:t> 後開啟\n"

    trial_target_amount = get_env_int("TRIAL_TARGET_AMOUNT")
    if any(resources.get(r, 0) >= trial_target_amount for r in ("food", "wood", "knowledge")):
        return "\n🏆 試煉 ✅ 可開啟試煉\n"
    return "\n🏆 試煉 ⚠️ 資源不足，尚無法開啟\n"


def _build_village_section(
    stage_data: dict, resources: dict, buildings: dict, action_counts: list,
    trial_data: dict | None = None,
) -> str:
    """
    Return the village status block as a text string.
    action_counts: list of (action, action_target, count) tuples.
    trial_data: current trial_state row, or None/{} if there is no active trial.
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

    trial_line = _build_trial_line(trial_data or {}, resources, now_ts)

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
        f"{trial_line}"
        f"\n公用資源\n"
        f"🌾 {food} | 🪵 {wood} | 🧠 {knowledge}\n"
        f"\n公用設施 (等級上限：Lv{level_cap})\n"
        f"{building_block}\n"
        f"\n村民行動\n"
        f"```\n{action_block}\n```"
    )


def build_village_embed(
    stage_data: dict, resources: dict, buildings: dict, action_counts: list,
    trial_data: dict | None = None,
) -> disnake.Embed:
    text = _build_village_section(stage_data, resources, buildings, action_counts, trial_data)
    return disnake.Embed(description=text, color=disnake.Color.blue())


def build_main_embed(
    stage_data: dict,
    resources: dict,
    buildings: dict,
    action_counts: list,
    player_row: dict,
    trial_data: dict | None = None,
    trial_contribution: int = 0,
    trial_message: str | None = None,
) -> disnake.Embed:
    village_text = _build_village_section(stage_data, resources, buildings, action_counts, trial_data)

    gear_parts = [
        f"{ACTION_EMOJIS[a]} {player_row.get(f'gear_{a}', 0)}"
        for a in ("gathering", "building", "combat", "research")
    ]
    mat_parts = [
        f"{ACTION_EMOJIS[a]} {player_row.get(f'materials_{a}', 0)}"
        for a in ("gathering", "building", "combat", "research")
    ]
    mat_parts.append(f"🌟 {player_row.get('materials_universal', 0)}")
    base_output = get_env_int("BASE_OUTPUT")
    stage_bonus_per = get_env_float("STAGE_BONUS_PER_CLEAR")
    gear_bonus_per = get_env_float("GEAR_BONUS_PER_LEVEL")
    facility_bonus_per = get_env_float("FACILITY_BONUS_PER_LEVEL")
    stages_cleared = stage_data.get("stages_cleared", 0)
    upgrade_clears = stages_cleared // 5
    efficiency_parts = []
    for action_type in ("gathering", "building", "combat", "research"):
        gear_level = player_row.get(f"gear_{action_type}", 0)
        facility = ACTION_FACILITY_BUILDING[action_type]
        facility_level = buildings.get(facility, {}).get("level", 0)
        bonus = (
            upgrade_clears * stage_bonus_per
            + gear_level * gear_bonus_per
            + facility_level * facility_bonus_per
        )
        output = math.floor(base_output * (1 + bonus))
        pct = math.floor(bonus * 100)
        efficiency_parts.append(f"{ACTION_EMOJIS[action_type]} {output}(+{pct}%)")

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
    recovery_mins = get_env_int("AP_RECOVERY_MINUTES")
    ap_full_time_unix = _unix_from_iso(player_row.get("ap_full_time") or "")
    if ap < ap_cap and ap_full_time_unix:
        next_ap_unix = ap_full_time_unix - (ap_cap - ap - 1) * recovery_mins * 60
        ap_line = f"⚡ AP：{ap} / {ap_cap}（下次：<t:{next_ap_unix}:R>）"
    else:
        ap_line = f"⚡ AP：{ap} / {ap_cap}"

    trial_contrib_line = f"\n🏆 試煉貢獻：{trial_contribution}" if (trial_data or {}).get("is_active") else ""
    trial_message_line = f"\n{trial_message}" if trial_message else ""

    player_section = (
        f"\n**個人資訊**\n"
        f"📊 效率：{' | '.join(efficiency_parts)}\n"
        f"🏅 工具：{' | '.join(gear_parts)}\n"
        f"🎒 素材：{' | '.join(mat_parts)}\n"
        f"{action_line}\n"
        f"{ap_line}"
        f"{trial_contrib_line}"
        f"{trial_message_line}"
    )

    return disnake.Embed(description=village_text + player_section, color=disnake.Color.blue())


def build_main_components(
    player_row: dict,
    buildings: dict,
    *,
    pending_action: str | None = None,
    pending_target: str | None = None,
    trial_data: dict | None = None,
    resources: dict | None = None,
    active_auto_tools: set | list | None = None,
) -> list:
    ap = player_row.get("_ap", 0)
    gear_cap = buildings.get("research_lab", {}).get("level", 0)
    all_gear_at_cap = all(
        player_row.get(f"gear_{gear_type}", 0) >= gear_cap
        for gear_type in ("gathering", "building", "combat", "research")
    )

    trial_data = trial_data or {}
    can_start_trial = not trial_data.get("is_active")
    if can_start_trial:
        ended_at_str = trial_data.get("ended_at")
        if ended_at_str:
            cooldown = get_env_int("TRIAL_COOLDOWN_SECONDS")
            ended_unix = _unix_from_iso(ended_at_str)
            now_unix = int(datetime.now(timezone.utc).timestamp())
            can_start_trial = (now_unix - ended_unix) >= cooldown
    if can_start_trial:
        resources = resources or {}
        trial_amount = get_env_int("TRIAL_TARGET_AMOUNT")
        can_start_trial = any(resources.get(r, 0) >= trial_amount for r in ("food", "wood", "knowledge"))

    # A tool running as an auto-tool cannot also be selected as the manual action.
    active_auto = set(active_auto_tools or [])
    selectable_actions = [a for a in ("gathering", "building", "combat", "research") if a not in active_auto]
    if selectable_actions:
        action_options = [
            disnake.SelectOption(
                label=f"{ACTION_EMOJIS[a]} {ACTION_LABELS[a]}",
                value=a,
                description=ACTION_DESCRIPTIONS[a],
                default=(pending_action == a),
            )
            for a in selectable_actions
        ]
        action_select_disabled = False
    else:
        action_options = [disnake.SelectOption(label="（所有工具皆為自動工具）", value="none")]
        action_select_disabled = True

    rows = [
        disnake.ui.ActionRow(
            disnake.ui.Button(
                label="⚡ 消耗AP立刻完成三次行動",
                style=disnake.ButtonStyle.primary,
                custom_id="burst_execute",
                disabled=(ap < 1 or player_row.get("action") is None),
            ),
            disnake.ui.Button(
                label="🔨 強化工具",
                style=disnake.ButtonStyle.primary,
                custom_id="open_gear_upgrade",
                disabled=all_gear_at_cap,
            ),
            disnake.ui.Button(
                label="🏆 開啟試煉",
                style=disnake.ButtonStyle.primary,
                custom_id="open_trial_start",
                disabled=not can_start_trial,
            ),
            disnake.ui.Button(
                label="⚙️ 自動工具",
                style=disnake.ButtonStyle.primary,
                custom_id="open_auto_tool",
            ),
        ),
        disnake.ui.ActionRow(
            disnake.ui.StringSelect(
                custom_id="action_select",
                placeholder="選擇行動...",
                options=action_options,
                disabled=action_select_disabled,
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


def _build_affix_section(affixes: list, max_slots: int) -> str:
    """Return affix slot text block, or empty string when no slots unlocked."""
    if max_slots == 0:
        return ""
    affix_by_slot = {a["slot_index"]: a for a in affixes}
    lines = ["─────────────────────────────", f"詞條槽（{len(affixes)}/{max_slots}）"]
    for i in range(max_slots):
        if i in affix_by_slot:
            a = affix_by_slot[i]
            label = AFFIX_TYPE_LABELS.get(a["affix_type"], a["affix_type"])
            sign = "-" if a["affix_type"] in REDUCE_AFFIX_TYPES else "+"
            lines.append(f"槽 {i}: ✨ {label} {sign}{a['value']}%")
        else:
            lines.append(f"槽 {i}: ─ 空槽")
    return "\n" + "\n".join(lines)


def build_gear_embed(
    upgrade_info: dict,
    gear_type: str | None,
    result: dict | None = None,
    *,
    affixes: list | None = None,
    max_slots: int = 0,
) -> disnake.Embed:
    if gear_type is None:
        return disnake.Embed(description="🔨 工具強化\n請選擇工具類型與強化模式", color=disnake.Color.blue())
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
    universal_materials = upgrade_info.get("universal_materials", 0)
    ap_cap = get_env_int("AP_CAP")

    pity_bonus_per = get_env_float("GEAR_PITY_BONUS")
    base_rate = max(
        get_env_float("GEAR_MIN_SUCCESS_RATE"),
        1.0 - gear_level * get_env_float("GEAR_RATE_LOSS_PER_LEVEL"),
    )
    final_rate = min(1.0, base_rate + pity * pity_bonus_per)
    base_rate_pct = _rate_percent(base_rate)
    final_rate_pct = _rate_percent(final_rate)
    pity_display = _rate_percent(pity_bonus_per)

    mode = upgrade_info.get("mode", "normal")
    mode_labels = {"normal": "標準", "buffer": "墊檔", "risky": "鐵齒"}
    mode_label = mode_labels.get(mode, mode)

    risky_failed_levels = upgrade_info.get("risky_failed_levels", 0)
    risky_bonus_pct = upgrade_info.get("risky_bonus_pct", 0.0)

    # For normal/risky mode, use the actual rate from upgrade_info which includes the risky bonus
    if mode in ("normal", "risky") and rate > final_rate:
        final_rate_pct = _rate_percent(min(1.0, rate))

    pity_total_pct = pity * pity_display
    risky_bonus_display = f"{risky_bonus_pct:g}"

    if mode == "buffer":
        rate_line = "成功率：0%（墊檔不進行強化）"
    else:
        rate_line = f"成功率：{base_rate_pct}%（+保底{pity_total_pct}% +鐵齒{risky_bonus_display}%）= {final_rate_pct}%"

    lines = [
        "🔨 工具強化",
        "─────────────────────────────",
        f"{label}：Lv{gear_level} → Lv{target_level}",
        f"模式：{mode_label}",
        rate_line,
    ]

    if mode in ("normal", "risky"):
        lines.extend([
            f"保底率：{pity} x {pity_display}% = {pity_total_pct}%",
            f"鐵齒率：{risky_failed_levels} x 0.01% = {risky_bonus_display}%",
        ])

    lines.extend([
        f"消耗：⚡ 1 AP + {material_cost} 個 {mat_label}",
        f"持有素材：{materials} 個 ｜ 🌟 萬能素材：{universal_materials} 個",
        f"⚡ AP：{ap} / {ap_cap}",
        f"工具等級上限：Lv{gear_cap}（研究所 Lv{gear_cap}）",
    ])

    affix_section = _build_affix_section(affixes or [], max_slots)
    if affix_section:
        lines.append(affix_section)

    if result is not None:
        if result.get("type") == "sacrifice":
            n = result.get("sacrificed", 0)
            lines.append(f"\n🩸 獻祭完成！消耗 {n} 個 {mat_label}，鐵齒加成 +{round(n * 0.01, 2):g}%")
        elif result.get("error"):
            lines.append(f"\n⚠️ 操作失敗：{result['error']}")
        else:
            result_mode = result.get("mode", "normal")
            if result.get("success"):
                lines.append(f"\n✅ 強化成功！{label} 升至 Lv{result.get('new_level', target_level)}")
            elif result_mode == "buffer":
                lines.append(f"\n🛡️ 墊檔完成。保底計數 +1（現為 {result.get('pity_after', pity + 1)}）")
            elif result_mode == "risky":
                lines.append(f"\n💀 鐵齒失敗！等級與保底計數歸零")
            else:
                lines.append(f"\n❌ 強化失敗。保底計數 +1")

    color = disnake.Color.green() if (result and result.get("success")) else disnake.Color.blue()
    return disnake.Embed(description="\n".join(lines), color=color)


_UPGRADE_MODE_DEFS = (
    ("標準", "normal", "正常強化：消耗全額素材，成功升級，失敗保底+1"),
    ("墊檔", "buffer", "消耗一半素材，直接獲得一個保底計數，不進行強化"),
    ("鐵齒", "risky", "僅消耗 1 個素材，成功 +1~+3（50/35/15%），失敗則工具等級與 pity 均歸零"),
)


def build_gear_components(
    gear_type: str | None,
    mode: str | None,
    can_attempt: bool,
    player_gear: dict,
    gear_cap: int,
    *,
    affixes: list | None = None,
    max_slots: int = 0,
    materials: int = 0,
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

    mode_options = [
        disnake.SelectOption(label=label, value=value, description=desc, default=(value == mode))
        for label, value, desc in _UPGRADE_MODE_DEFS
    ]

    _gt = gear_type or "none"
    _m = mode or "normal"

    rows = [
        disnake.ui.ActionRow(
            disnake.ui.StringSelect(
                custom_id="gear_type_select",
                placeholder="選擇工具類型...",
                options=gear_options,
            )
        ),
        disnake.ui.ActionRow(
            disnake.ui.StringSelect(
                custom_id=f"upgrade_mode_select:{_gt}",
                placeholder="選擇強化模式...",
                options=mode_options,
            )
        ),
        disnake.ui.ActionRow(
            disnake.ui.Button(
                label="🎲 強化工具",
                style=disnake.ButtonStyle.success,
                custom_id=f"attempt_upgrade:{_gt}:{_m}",
                disabled=not can_attempt or mode is None,
            ),
            disnake.ui.Button(
                label="🩸 獻祭素材",
                style=disnake.ButtonStyle.danger,
                custom_id=f"sacrifice_material:{_gt}",
                disabled=(materials == 0),
            ),
            disnake.ui.Button(
                label="🔮 詞條管理",
                style=disnake.ButtonStyle.primary,
                custom_id=f"open_affix_mgmt:{_gt}",
                disabled=(max_slots == 0),
            ),
            disnake.ui.Button(
                label="← 返回",
                style=disnake.ButtonStyle.secondary,
                custom_id="back_to_main",
            ),
        ),
    ]

    return rows


def build_affix_embed(
    gear_type: str | None,
    player_gear: dict,
    affixes: list,
    max_slots: int,
    selected_slot: int | None = None,
) -> disnake.Embed:
    if gear_type is None:
        return disnake.Embed(description="🔮 詞條管理\n請選擇工具類型", color=disnake.Color.purple())
    label = GEAR_LABELS.get(gear_type, gear_type)
    lines = [f"🔮 詞條管理 — {ACTION_EMOJIS.get(gear_type, '')} {label}"]
    affix_section = _build_affix_section(affixes, max_slots)
    if affix_section:
        lines.append(affix_section)
    if selected_slot is not None:
        affix_by_slot = {a["slot_index"]: a for a in affixes}
        a = affix_by_slot.get(selected_slot)
        if a:
            sign = "-" if a["affix_type"] in REDUCE_AFFIX_TYPES else "+"
            type_label = AFFIX_TYPE_LABELS.get(a["affix_type"], a["affix_type"])
            lines.append(f"\n即將清除：槽 {selected_slot} — {type_label} {sign}{a['value']}%")
    embed = disnake.Embed(description="\n".join(lines), color=disnake.Color.purple())
    return embed


def build_affix_components(
    gear_type: str | None,
    player_gear: dict,
    gear_cap: int,
    affixes: list,
    max_slots: int,
    selected_slot: int | None = None,
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

    is_full = len(affixes) >= max_slots
    _gt = gear_type or "none"

    rows = [
        disnake.ui.ActionRow(
            disnake.ui.StringSelect(
                custom_id="affix_gear_select",
                placeholder="選擇工具類型...",
                options=gear_options,
            )
        ),
    ]

    if affixes:
        affix_options = [
            disnake.SelectOption(
                label=f"槽 {a['slot_index']}: {AFFIX_TYPE_LABELS.get(a['affix_type'], a['affix_type'])}",
                value=str(a["slot_index"]),
                description=f"{'-' if a['affix_type'] in REDUCE_AFFIX_TYPES else '+'}{a['value']}%",
                default=(a["slot_index"] == selected_slot),
            )
            for a in affixes
        ]
        rows.append(
            disnake.ui.ActionRow(
                disnake.ui.StringSelect(
                    custom_id=f"affix_slot_select:{_gt}",
                    placeholder="選擇要清除的詞條...",
                    options=affix_options,
                )
            )
        )

    rows.append(
        disnake.ui.ActionRow(
            disnake.ui.Button(
                label="🗑️ 清除詞條",
                style=disnake.ButtonStyle.danger,
                custom_id=f"affix_clear:{_gt}:{selected_slot}",
                disabled=(selected_slot is None),
            ),
            disnake.ui.Button(
                label="✨ 抽取詞條",
                style=disnake.ButtonStyle.primary,
                custom_id=f"affix_extract:{_gt}",
                disabled=is_full,
            ),
            disnake.ui.Button(
                label="← 返回",
                style=disnake.ButtonStyle.secondary,
                custom_id=f"back_to_gear:{_gt}",
            ),
        )
    )

    return rows


_AUTO_TOOL_ORDER = ("gathering", "building", "combat", "research")


def build_auto_tool_embed(active_rows: list, max_materials: int) -> disnake.Embed:
    """Auto-tool sub-interface embed: currently running tools + their expiry, plus the rule."""
    lines = ["⚙️ 自動工具", "─────────────────────────────"]
    if active_rows:
        lines.append("運行中：")
        for row in active_rows:
            tt = row["tool_type"]
            label = f"{ACTION_EMOJIS.get(tt, '')} {GEAR_LABELS.get(tt, tt)}"
            deadline = _unix_from_iso(row["expires_at"])
            line = f"{label} — 到期 <t:{deadline}:R>"
            if tt == "building" and row.get("action_target"):
                line += f"（{BUILDING_LABELS.get(row['action_target'], row['action_target'])}）"
            lines.append(line)
    else:
        lines.append("目前沒有運行中的自動工具。")
    lines.append("─────────────────────────────")
    lines.append(f"每 1 個該工具素材可運行 1 小時；上限 {max_materials} 小時。運行中可補充（不超過上限）。")
    return disnake.Embed(description="\n".join(lines), color=disnake.Color.teal())


def build_auto_tool_components(
    idle_tools: list,
    active_rows: list,
    *,
    selected_tool: str | None = None,
    selected_target: str | None = None,
    selected_count: int | None = None,
    max_add: int = 0,
) -> list:
    """
    Auto-tool sub-interface components.

    idle_tools: tool types that can be started (not manual action, not running).
    active_rows: running auto-tool rows (selectable for refuel).
    selected_tool/target/count + max_add drive the confirm button's enabled state.
    """
    active_types = [r["tool_type"] for r in active_rows]
    selectable = [t for t in _AUTO_TOOL_ORDER if t in idle_tools or t in active_types]

    if selectable:
        tool_options = [
            disnake.SelectOption(
                label=f"{ACTION_EMOJIS.get(t, '')} {GEAR_LABELS.get(t, t)}",
                value=t,
                description=("運行中（補充）" if t in active_types else "啟動"),
                default=(selected_tool == t),
            )
            for t in selectable
        ]
        tool_disabled = False
    else:
        tool_options = [disnake.SelectOption(label="（沒有可用的工具）", value="none")]
        tool_disabled = True

    rows = [
        disnake.ui.ActionRow(
            disnake.ui.StringSelect(
                custom_id="auto_tool_type_select",
                placeholder="選擇工具...",
                options=tool_options,
                disabled=tool_disabled,
            )
        )
    ]

    if selected_tool == "building":
        target_options = [
            disnake.SelectOption(
                label=BUILDING_LABELS[b], value=b, default=(selected_target == b)
            )
            for b in UI_BUILDING_TARGETS
        ]
        rows.append(
            disnake.ui.ActionRow(
                disnake.ui.StringSelect(
                    custom_id="auto_tool_target_select",
                    placeholder="選擇建設目標...",
                    options=target_options,
                )
            )
        )

    if selected_tool is not None:
        if max_add >= 1:
            count_options = [
                disnake.SelectOption(label=f"{n} 個（{n} 小時）", value=str(n), default=(selected_count == n))
                for n in range(1, max_add + 1)
            ]
            count_disabled = False
        else:
            count_options = [disnake.SelectOption(label="（已達上限，無法補充）", value="none")]
            count_disabled = True
        rows.append(
            disnake.ui.ActionRow(
                disnake.ui.StringSelect(
                    custom_id="auto_tool_count_select",
                    placeholder="選擇消耗素材數量...",
                    options=count_options,
                    disabled=count_disabled,
                )
            )
        )

    ready = (
        selected_tool is not None
        and max_add >= 1
        and selected_count is not None
        and 1 <= selected_count <= max_add
        and (selected_tool != "building" or selected_target is not None)
    )
    confirm_id = (
        f"auto_tool_confirm:{selected_tool}:{selected_count}:{selected_target or 'none'}"
        if ready
        else "auto_tool_confirm:none"
    )
    rows.append(
        disnake.ui.ActionRow(
            disnake.ui.Button(
                label="✅ 確認",
                style=disnake.ButtonStyle.success,
                custom_id=confirm_id,
                disabled=not ready,
            ),
            disnake.ui.Button(
                label="← 返回",
                style=disnake.ButtonStyle.secondary,
                custom_id="back_to_main",
            ),
        )
    )
    return rows


def build_manager_embed(target_user_display_name: str, player_data: dict) -> disnake.Embed:
    embed = disnake.Embed(
        title=f"玩家管理：{target_user_display_name}",
        color=disnake.Color.orange(),
    )

    for prefix, field_name in (
        ("gear", "工具等級"),
        ("materials", "素材數量"),
        ("pity", "保底計數"),
    ):
        value = " ｜ ".join(
            f"{ACTION_LABELS[a]} {player_data.get(f'{prefix}_{a}', 0)}"
            for a in ("gathering", "building", "combat", "research")
        )
        if prefix == "materials":
            value += f" ｜ 萬能 {player_data.get('materials_universal', 0)}"
        embed.add_field(name=field_name, value=value, inline=False)

    embed.add_field(
        name="鐵齒失敗累積",
        value=str(player_data.get("risky_failed_levels", 0)),
        inline=False,
    )

    return embed


def build_manager_components(target_user_id: str) -> list:
    return [
        disnake.ui.ActionRow(
            disnake.ui.Button(
                label="編輯工具等級",
                style=disnake.ButtonStyle.secondary,
                custom_id=f"mgr_edit_gear:{target_user_id}",
            ),
            disnake.ui.Button(
                label="編輯素材",
                style=disnake.ButtonStyle.secondary,
                custom_id=f"mgr_edit_material:{target_user_id}",
            ),
            disnake.ui.Button(
                label="編輯保底",
                style=disnake.ButtonStyle.secondary,
                custom_id=f"mgr_edit_pity:{target_user_id}",
            ),
            disnake.ui.Button(
                label="編輯鐵齒",
                style=disnake.ButtonStyle.secondary,
                custom_id=f"mgr_edit_risky:{target_user_id}",
            ),
        )
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


_RANKING_GEAR_ORDER = ("gathering", "building", "combat", "research")


def build_ranking_text(sliced_rankings: dict, name_map: dict) -> str:
    """Format per-tool-type rankings as a plain text string.

    sliced_rankings: {gear_type: [(user_id, level), ...]} already sliced to top levels.
    name_map: {user_id: display_name}
    Returns a multi-line string ready to send as Discord message content.
    """
    sections = []
    for gear_type in _RANKING_GEAR_ORDER:
        emoji = ACTION_EMOJIS[gear_type]
        label = GEAR_LABELS[gear_type]
        entries = sliced_rankings.get(gear_type, [])
        header = f"{emoji}{label}:"
        if not entries:
            sections.append(f"{header}\n- （尚無玩家）")
        else:
            lines = [header]
            for user_id, level in entries:
                name = name_map.get(user_id, user_id)
                lines.append(f"- Lv{level}: {name}")
            sections.append("\n".join(lines))
    return "\n".join(sections)

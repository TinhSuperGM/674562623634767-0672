from __future__ import annotations

from typing import Any, Dict, Union

import discord

from api_client import get_couple, get_data, get_inventory, get_user_data, get_waifu

# ===== UTILS =====
def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _get_waifu_amount(raw_value: Any) -> int:
    if isinstance(raw_value, dict):
        return _safe_int(raw_value.get("love", 0))
    return _safe_int(raw_value, 0)


def _count_total_waifu(waifus: Dict[str, Any]) -> int:
    return sum(_get_waifu_amount(v) for v in waifus.values())


def _sanitize(text: str) -> str:
    return discord.utils.escape_mentions(discord.utils.escape_markdown(text))


def _truncate(text: str, limit: int = 300) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _pick_user_bucket(root: Any, user_id: str) -> Dict[str, Any]:
    """
    Hỗ trợ cả 2 kiểu dữ liệu:
    - root[user_id] = {...}
    - root = {...} (trả trực tiếp bucket của user)
    """
    if not isinstance(root, dict):
        return {}

    uid = str(user_id)

    if uid in root and isinstance(root[uid], dict):
        return root[uid]

    # Nếu API trả trực tiếp bucket của user
    if "gold" in root or "waifus" in root or "bag" in root or "default_waifu" in root:
        return root

    return {}


def _pick_level_bucket(root: Any, user_id: str) -> Dict[str, Any]:
    """
    Hỗ trợ:
    - root[user_id] = {waifu_id: level}
    - root = {waifu_id: level}
    """
    if not isinstance(root, dict):
        return {}

    uid = str(user_id)

    if uid in root and isinstance(root[uid], dict):
        return root[uid]

    # Nếu API trả trực tiếp bảng level của user
    if root and all(isinstance(v, (int, dict)) for v in root.values()):
        return root

    return {}


def _pick_couple_bucket(root: Any, user_id: str) -> Dict[str, Any]:
    """
    Hỗ trợ:
    - root[user_id] = {partner, points, ...}
    - root = {partner, points, ...}
    """
    if not isinstance(root, dict):
        return {}

    uid = str(user_id)

    if uid in root and isinstance(root[uid], dict):
        return root[uid]

    if "partner" in root or "points" in root:
        return root

    return {}


# ===== MAIN =====
async def get_profile_embed(bot, user: Union[discord.Member, discord.User]):
    uid = str(user.id)

    # ===== LOAD API =====
    inv_raw = await get_inventory(uid)
    level_raw = await get_data("level")
    couple_raw = await get_couple()
    waifu_raw = await get_waifu()
    user_raw = await get_user_data(uid)

    inv_data = _pick_user_bucket(inv_raw, uid)
    level_data = _pick_level_bucket(level_raw, uid)
    couple_data = _pick_couple_bucket(couple_raw, uid)
    waifu_data = waifu_raw if isinstance(waifu_raw, dict) else {}

    # ===== GOLD =====
    gold = _safe_int(user_raw.get("gold") if isinstance(user_raw, dict) else 0)

    # ===== WAIFU =====
    waifus = inv_data.get("waifus") or {}
    if not isinstance(waifus, dict):
        waifus = {}

    count = len(waifus)
    total = _count_total_waifu(waifus)

    default = inv_data.get("default_waifu")
    if default and default in waifus:
        wid = str(default)
        info = waifu_data.get(wid, {}) if isinstance(waifu_data.get(wid, {}), dict) else {}
        love = _get_waifu_amount(waifus.get(wid))
        level = _safe_int(level_data.get(wid, 0))
    else:
        wid, info, love, level = None, {}, 0, 0

    name = info.get("name", "None")
    bio = _truncate(_sanitize(info.get("Bio", "No bio")))
    image = info.get("image")

    # ===== COUPLE =====
    partner_id = couple_data.get("partner")
    points = _safe_int(couple_data.get("points"))

    if partner_id:
        try:
            partner = bot.get_user(int(partner_id))
        except Exception:
            partner = None

        partner_name = partner.display_name if partner else f"<@{partner_id}>"
    else:
        partner_name = "Single"

    # ===== EMBED =====
    embed = discord.Embed(
        color=discord.Color.pink() if partner_id else discord.Color.blurple()
    )

    embed.set_author(
        name=f"{user.display_name} ✨",
        icon_url=user.display_avatar.url,
    )
    embed.set_thumbnail(url=user.display_avatar.url)

    embed.add_field(
        name="Economy",
        value=f"Gold: **{gold:,}**\nWaifu: **{count}** | ❤️ {total}",
        inline=True,
    )

    embed.add_field(
        name="Main Waifu",
        value=f"**{name}**\n❤️ {love} | Lv {level}",
        inline=True,
    )

    embed.add_field(
        name="Relationship",
        value=f"{partner_name}\nPoint: **{points}**",
        inline=True,
    )

    embed.add_field(
        name="Description",
        value=bio,
        inline=False,
    )

    if image:
        embed.set_image(url=image)

    embed.set_footer(text=f"User ID: {uid}")
    return embed


print("Loaded profile (API) has success")

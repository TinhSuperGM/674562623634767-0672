import discord
from typing import Any, Dict, Union

# ✅ API thay vì JSON
from api_client import get
from Data import data_user  # vẫn giữ nếu bạn đã convert sang API bên trong

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


def _truncate(text: str, limit=300):
    return text if len(text) <= limit else text[:limit - 3] + "..."


# ===== MAIN =====
async def get_profile_embed(bot, user: Union[discord.Member, discord.User]):
    uid = str(user.id)

    # ===== LOAD API =====
    inv = await get(f"/inventory/{uid}")
    level_data = await get(f"/level/{uid}")
    couple_data = await get(f"/couple/{uid}")
    waifu_data = await get("/waifu")

    # ✅ GOLD (nếu data_user đã dùng API thì giữ, không thì đổi sang API luôn)
    user_data = await get(f"/users/{uid}")
    gold = _safe_int(user_data.get("gold"))

    # ===== DATA =====
    inv_data = inv or {}
    level_data = level_data or {}
    couple_data = couple_data or {}

    # ===== WAIFU =====
    waifus = inv_data.get("waifus") or {}

    if not isinstance(waifus, dict):
        waifus = {}

    count = len(waifus)
    total = _count_total_waifu(waifus)

    default = inv_data.get("default_waifu")

    if default and default in waifus and default in waifu_data:
        wid = default
        info = waifu_data.get(wid, {})
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
        partner = bot.get_user(int(partner_id))
        partner_name = partner.display_name if partner else f"<@{partner_id}>"
    else:
        partner_name = "Single"

    # ===== EMBED =====
    embed = discord.Embed(
        color=discord.Color.pink() if partner_id else discord.Color.blurple()
    )

    embed.set_author(
        name=f"{user.display_name} ✨",
        icon_url=user.display_avatar.url
    )

    embed.set_thumbnail(url=user.display_avatar.url)

    embed.add_field(
        name="💰 Economy",
        value=f"Gold: **{gold:,}**\nWaifu: **{count}** | ❤️ {total}",
        inline=True
    )

    embed.add_field(
        name="💖 Main Waifu",
        value=f"**{name}**\n❤️ {love} | Lv {level}",
        inline=True
    )

    embed.add_field(
        name="💍 Relationship",
        value=f"{partner_name}\nPoint: **{points}**",
        inline=True
    )

    embed.add_field(
        name="📖 Description",
        value=bio,
        inline=False
    )

    if image:
        embed.set_image(url=image)

    embed.set_footer(text=f"User ID: {uid}")

    return embed


print("Loaded profile (API) has success")
import asyncio
import time
from typing import Any, Dict, Optional, Union

import discord
from discord.ext import commands

from api_client import get  # 👈 dùng API

# ===== CACHE =====
_INV_CACHE: Dict[str, Any] = {}
_WAIFU_CACHE: Dict[str, Any] = {}
_INV_TS = 0.0
_WAIFU_TS = 0.0
_INV_TTL = 10.0
_WAIFU_TTL = 30.0

_LOCKS: Dict[str, asyncio.Lock] = {}


def get_lock(key: str) -> asyncio.Lock:
    if key not in _LOCKS:
        _LOCKS[key] = asyncio.Lock()
    return _LOCKS[key]


def safe_int(value: Any) -> int:
    try:
        return int(value)
    except Exception:
        return 0


# ===== LOAD FROM API =====

async def load_inventory(force: bool = False) -> Dict[str, Any]:
    global _INV_CACHE, _INV_TS
    now = time.time()

    if force or not _INV_CACHE or (now - _INV_TS) > _INV_TTL:
        data = await get("/inventory")
        _INV_CACHE = data if isinstance(data, dict) else {}
        _INV_TS = now

    return _INV_CACHE


async def load_waifu_data(force: bool = False) -> Dict[str, Any]:
    global _WAIFU_CACHE, _WAIFU_TS
    now = time.time()

    if force or not _WAIFU_CACHE or (now - _WAIFU_TS) > _WAIFU_TTL:
        data = await get("/waifu")
        _WAIFU_CACHE = data if isinstance(data, dict) else {}
        _WAIFU_TS = now

    return _WAIFU_CACHE


# ❌ KHÔNG CẦN SAVE FILE NỮA
async def save_inventory(data: Dict[str, Any]) -> None:
    pass


# ===== LOGIC GIỮ NGUYÊN =====

def get_waifu_name(waifu_id: str, waifu_data: Dict[str, Any]) -> str:
    meta = waifu_data.get(waifu_id, {})
    if isinstance(meta, dict):
        for key in ("name", "display_name", "title", "char_name"):
            if meta.get(key):
                return str(meta[key])
    return str(waifu_id)


def build_entries(user_data: Dict[str, Any], waifu_data: Dict[str, Any]):
    entries = []

    bag = user_data.get("bag", {})
    if isinstance(bag, dict):
        for wid, count in bag.items():
            count = safe_int(count)
            if count > 0:
                entries.append(("waifu", str(wid), count, get_waifu_name(str(wid), waifu_data)))

    bag_item = user_data.get("bag_item", {})
    if isinstance(bag_item, dict):
        for item_name, count in bag_item.items():
            count = safe_int(count)
            if count > 0:
                entries.append(("item", str(item_name), count, str(item_name)))

    entries.sort(key=lambda x: (0 if x[0] == "waifu" else 1, x[3].lower()))
    return entries


def build_embed(
    target_user: Union[discord.User, discord.Member],
    requester: Union[discord.User, discord.Member],
    entries,
) -> discord.Embed:
    waifu_lines = []
    item_lines = []

    for t, raw_id, count, display_name in entries:
        if t == "waifu":
            waifu_lines.append(f"• `{display_name}` x{count}")
        else:
            item_lines.append(f"• `{display_name}` x{count}")

    waifu_text = "\n".join(waifu_lines) if waifu_lines else "Trống"
    item_text = "\n".join(item_lines) if item_lines else "Trống"

    embed = discord.Embed(
        title=f"🎒 Túi đồ của {target_user.display_name}",
        color=0x1E1F22,
    )
    embed.set_thumbnail(url=target_user.display_avatar.url)
    embed.add_field(name="💖 Waifus", value=waifu_text, inline=False)
    embed.add_field(name="📦 Vật phẩm", value=item_text, inline=False)
    embed.set_footer(
        text=f"Yêu cầu bởi: {requester.display_name} • Waifu: {len(waifu_lines)} • Item: {len(item_lines)}"
    )
    return embed


# ===== CTX HELPERS =====

def get_user(ctx):
    return ctx.user if isinstance(ctx, discord.Interaction) else ctx.author


async def resolve_target_user(
    ctx: Union[commands.Context, discord.Interaction],
    target_user: Optional[Union[discord.User, discord.Member]] = None,
):
    if target_user is not None:
        return target_user

    if isinstance(ctx, commands.Context):
        if ctx.message and ctx.message.reference and ctx.message.reference.resolved:
            ref = ctx.message.reference.resolved
            if isinstance(ref, discord.Message) and ref.author:
                return ref.author
        return ctx.author

    if isinstance(ctx, discord.Interaction):
        return ctx.user

    return None


async def send_message(
    ctx: Union[commands.Context, discord.Interaction],
    *,
    content: Optional[str] = None,
    embed: Optional[discord.Embed] = None,
    ephemeral: bool = False,
):
    if isinstance(ctx, discord.Interaction):
        try:
            if not ctx.response.is_done():
                return await ctx.response.send_message(
                    content=content,
                    embed=embed,
                    ephemeral=ephemeral
                )
            else:
                return await ctx.followup.send(
                    content=content,
                    embed=embed,
                    ephemeral=ephemeral
                )
        except discord.InteractionResponded:
            return await ctx.followup.send(
                content=content,
                embed=embed,
                ephemeral=ephemeral
            )

    return await ctx.send(content=content, embed=embed)


# ===== MAIN =====

async def bag_logic(
    ctx: Union[commands.Context, discord.Interaction],
    target_user: Optional[Union[discord.User, discord.Member]] = None,
):
    requester = get_user(ctx)
    target_user = await resolve_target_user(ctx, target_user)

    # 🔥 API load
    inv = await load_inventory(force=True)
    waifu_data = await load_waifu_data(force=True)

    user_data = inv.get(str(target_user.id), {})
    if not isinstance(user_data, dict):
        user_data = {}

    entries = build_entries(user_data, waifu_data)
    embed = build_embed(target_user, requester, entries)

    content = None
    if target_user.id != requester.id:
        content = target_user.mention

    await send_message(ctx, content=content, embed=embed)


print("Loaded bag (API mode) has success")
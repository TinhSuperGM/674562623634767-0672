import asyncio
from typing import Optional

import discord

from Commands.fight import INV_LOCK
import api_client

TEAM_LOCK = :contentReference[oaicite:0]{index=0}= HELPERS =====
def resolve_waifu_id(input_id: str, waifu_data: dict, user_waifus: dict):
    input_id = str(input_id).lower()

    if input_id in user_waifus:
        return input_id

    for wid, meta in waifu_data.items():
        if not isinstance(meta, dict):
            continue

        name = str(meta.get("name", "")).lower()
        display = str(meta.get("display_name", "")).lower()

        if input_id in (name, display):
            if wid in user_waifus:
                return wid

    return None


def get_user_obj(ctx):
    return getattr(ctx, "user", None) or getattr(ctx, "author", None)


async def resolve_target_user(ctx, target):
    if target:
        return target

    if hasattr(ctx, "message") and ctx.message:
        ref = getattr(ctx.message, "reference", None)
        if ref and ref.resolved and getattr(ref.resolved, "author", None):
            return ref.resolved.author

        mentions = getattr(ctx.message, "mentions", [])
        if mentions:
            return mentions[0]

    return get_user_obj(ctx)


async def send_like(ctx, content=None, embed=None, ephemeral=False):
    if hasattr(ctx, "response"):
        if not ctx.response.is_done():
            return await ctx.response.send_message(content=content, embed=embed, ephemeral=ephemeral)
        return await ctx.followup.send(content=content, embed=embed, ephemeral=ephemeral)

    return await ctx.send(content=content, embed=embed)


def normalize_team_ids(inv, uid, team_data):
    uid = str(uid)

    user = inv.get(uid, {})
    if not isinstance(user, dict):
        user = {}

    waifus = user.get("waifus", {})
    if not isinstance(waifus, dict):
        waifus = {}

    source = team_data.get(uid, {}).get("team", [])
    if not source:
        default_id = user.get("default_waifu")
        if default_id is not None:
            source = [str(default_id)]
        elif isinstance(waifus, dict):
            source = list(waifus.keys())

    out = []
    seen = set()

    for wid in source:
        wid = str(wid)
        if wid in seen:
            continue
        if wid in waifus:
            out.append(wid)
            seen.add(wid)
        if len(out) >= 3:
            break

    return out


def _waifu_name(waifu_data: dict, wid: str):
    meta = waifu_data.get(wid, {})
    if not isinstance(meta, dict):
        return wid
    return meta.get("name") or meta.get("display_name") or wid


def _can_set(uid):
    now = asyncio.get_event_loop().time()

    if len(_LAST_SET) > 5000:
        _LAST_SET.clear()

    last = _LAST_SET.get(uid, 0)
    if now - last < 2:
        return False

    _LAST_SET[uid] = now
    return True


# ===== LOGIC =====
async def show_team_logic(ctx, target: Optional[discord.Member] = None):
    user = await resolve_target_user(ctx, target)
    if not user:
        return await send_like(ctx, content="❌ Không xác định user", ephemeral=True)

    uid = str(user.id)

    inv = await api_client.get_inventory(uid)
    team_data = await api_client.get("/team")
    waifu_data = await api_client.get("/waifu")

    if not isinstance(inv, dict):
        inv = {}
    if not isinstance(team_data, dict):
        team_data = {}
    if not isinstance(waifu_data, dict):
        waifu_data = {}

    team = normalize_team_ids({uid: inv}, uid, team_data)

    if not team:
        return await send_like(ctx, content="Không có waifu.", ephemeral=True)

    lines = []
    for wid in team:
        meta = waifu_data.get(wid, {})
        rank = meta.get("rank", "unknown") if isinstance(meta, dict) else "unknown"
        lines.append(f"• **{_waifu_name(waifu_data, wid)}** (`{wid}`) | rank: `{rank}`")

    embed = discord.Embed(
        title=f"Team của {getattr(user, 'display_name', user.name)}",
        description="\n".join(lines),
        color=discord.Color.blurple(),
    )
    return await send_like(ctx, embed=embed)


async def set_team_logic(ctx, waifu_ids: str):
    user = get_user_obj(ctx)
    if not user:
        return await send_like(ctx, content="❌ Không xác định user", ephemeral=True)

    uid = str(user.id)

    if not _can_set(uid):
        return await send_like(ctx, content="⏳ Thao tác quá nhanh", ephemeral=True)

    async with INV_LOCK:
        async with TEAM_LOCK:
            inv = await api_client.get_inventory(uid)
            team_data = await api_client.get("/team")
            waifu_data = await api_client.get("/waifu")

            if not isinstance(inv, dict):
                inv = {}
            if not isinstance(team_data, dict):
                team_data = {}
            if not isinstance(waifu_data, dict):
                waifu_data = {}

            waifus = inv.get("waifus", {})
            if not isinstance(waifus, dict):
                waifus = {}

            raw_ids = [x.strip() for x in waifu_ids.replace(",", " ").split() if x.strip()]
            chosen = []
            invalid = []

            for raw in raw_ids:
                wid = resolve_waifu_id(raw, waifu_data, waifus)
                if not wid:
                    invalid.append(raw)
                    continue
                if wid not in chosen:
                    chosen.append(wid)
                if len(chosen) >= 3:
                    break

            if not chosen:
                return await send_like(ctx, content="❌ Không có waifu hợp lệ", ephemeral=True)

            team_data[uid] = {"team": chosen}
            await api_client.post("/team/update", team_data)

            return await send_like(ctx, content=f"✅ Team: {', '.join(chosen)}", ephemeral=True)


async def add_team_logic(ctx, waifu_id: str):
    user = get_user_obj(ctx)
    uid = str(user.id)

    async with INV_LOCK:
        async with TEAM_LOCK:
            inv = await api_client.get_inventory(uid)
            team_data = await api_client.get("/team")

            if not isinstance(inv, dict):
                inv = {}
            if not isinstance(team_data, dict):
                team_data = {}

            waifus = inv.get("waifus", {})
            if not isinstance(waifus, dict):
                waifus = {}

            if waifu_id not in waifus:
                return await send_like(ctx, content="❌ Không sở hữu", ephemeral=True)

            current = team_data.get(uid, {}).get("team", [])
            if not isinstance(current, list):
                current = []

            if len(current) >= 3:
                return await send_like(ctx, content="❌ Full team", ephemeral=True)

            if waifu_id not in current:
                current.append(waifu_id)

            team_data[uid] = {"team": current}
            await api_client.post("/team/update", team_data)

            return await send_like(ctx, content="✅ Đã thêm", ephemeral=True)


async def remove_team_logic(ctx, waifu_id: str):
    user = get_user_obj(ctx)
    uid = str(user.id)

    async with INV_LOCK:
        async with TEAM_LOCK:
            team_data = await api_client.get("/team")
            if not isinstance(team_data, dict):
                team_data = {}

            current = team_data.get(uid, {}).get("team", [])
            if not isinstance(current, list):
                current = []

            if waifu_id not in current:
                return await send_like(ctx, content="❌ Không có trong team", ephemeral=True)

            current.remove(waifu_id)

            if current:
                team_data[uid] = {"team": current}
            else:
                team_data.pop(uid, None)

            await api_client.post("/team/update", team_data)
            return await send_like(ctx, content="✅ Đã xoá", ephemeral=True)


async def clear_team_logic(ctx):
    user = get_user_obj(ctx)
    uid = str(user.id)

    async with INV_LOCK:
        async with TEAM_LOCK:
            team_data = await api_client.get("/team")
            if not isinstance(team_data, dict):
                team_data = {}

            team_data.pop(uid, None)
            await api_client.post("/team/update", team_data)

            return await send_like(ctx, content="✅ Đã xoá team", ephemeral=True)


async def team_logic(ctx, action: str = None, args: str = None, target: Optional[discord.Member] = None):
    if not action or action == "show":
        return await show_team_logic(ctx, target)

    if action == "set":
        return await set_team_logic(ctx, args or "")

    if action == "add":
        return await add_team_logic(ctx, args)

    if action in ("remove", "rm"):
        return await remove_team_logic(ctx, args)

    if action == "clear":
        return await clear_team_logic(ctx)

    return await send_like(ctx, content="❌ Lệnh không hợp lệ")

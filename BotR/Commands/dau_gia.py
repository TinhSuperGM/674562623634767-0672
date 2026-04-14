from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any, Dict, Optional, Union

import discord
from discord.ext import commands

from BotR import api_client
from Data import data_user

ALLOWED_AUCTION_RANKS = {"truyen_thuyet", "toi_thuong", "limited"}

# =========================================================
# LOCK / COOLDOWN
# =========================================================
GLOBAL_LOCK = asyncio.Lock()
auction_locks: Dict[str, asyncio.Lock] = {}
last_bid_time: Dict[str, float] = {}


def get_auction_lock(aid: str) -> asyncio.Lock:
    aid = str(aid)
    if aid not in auction_locks:
        auction_locks[aid] = asyncio.Lock()
    return auction_locks[aid]


def check_cooldown(uid: str, aid: str) -> bool:
    key = f"{uid}:{aid}"
    now = time.time()
    if key in last_bid_time and now - last_bid_time[key] < 2:
        return False
    last_bid_time[key] = now
    return True


# =========================================================
# CACHE
# =========================================================
WAIFU_CACHE: Dict[str, Any] = {}
WAIFU_LAST = 0.0
CHANNEL_CACHE: Dict[str, Any] = {}
CHANNEL_LAST = 0.0


def _get_user(ctx):
    return ctx.user if isinstance(ctx, discord.Interaction) else ctx.author


def _get_client(ctx):
    return ctx.client if isinstance(ctx, discord.Interaction) else ctx.bot


def _normalize_inventory(inv: Any) -> Dict[str, Any]:
    if not isinstance(inv, dict):
        inv = {}
    inv.setdefault("waifus", {})
    inv.setdefault("bag", {})
    inv.setdefault("bag_item", {})
    inv.setdefault("default_waifu", None)
    return inv


def _normalize_auction(a: Any) -> Dict[str, Any]:
    return a if isinstance(a, dict) else {}


# =========================================================
# API LOADERS
# =========================================================
async def get_waifu_data() -> Dict[str, Any]:
    global WAIFU_CACHE, WAIFU_LAST
    if time.time() - WAIFU_LAST < 10 and WAIFU_CACHE:
        return WAIFU_CACHE

    data = await api_client.get_waifu()
    WAIFU_CACHE = data if isinstance(data, dict) else {}
    WAIFU_LAST = time.time()
    return WAIFU_CACHE


async def get_channels() -> Dict[str, Any]:
    global CHANNEL_CACHE, CHANNEL_LAST
    if time.time() - CHANNEL_LAST < 10 and CHANNEL_CACHE:
        return CHANNEL_CACHE

    data = await api_client.get_auction_channels()
    CHANNEL_CACHE = data if isinstance(data, dict) else {}
    CHANNEL_LAST = time.time()
    return CHANNEL_CACHE


async def load_auctions() -> Dict[str, Any]:
    data = await api_client.get_auction()
    return data if isinstance(data, dict) else {}


async def save_auctions(data: Dict[str, Any]) -> bool:
    res = await api_client.set_auction(data)
    return bool(res and res.get("success", True))


async def get_inventory(user_id: str) -> Dict[str, Any]:
    data = await api_client.get_inventory(user_id)
    return _normalize_inventory(data)


async def save_inventory(user_id: str, inv: Dict[str, Any]) -> bool:
    res = await api_client.post(f"/inventory/{user_id}/update", inv)
    return bool(res and res.get("success"))


# =========================================================
# SEND HELPERS
# =========================================================
async def _send(
    ctx: Union[commands.Context, discord.Interaction],
    content: Optional[str] = None,
    embed: Optional[discord.Embed] = None,
    view: Optional[discord.ui.View] = None,
    ephemeral: bool = False,
):
    try:
        if isinstance(ctx, discord.Interaction):
            try:
                if not ctx.response.is_done():
                    await ctx.response.send_message(
                        content=content,
                        embed=embed,
                        view=view,
                        ephemeral=ephemeral,
                    )
                    try:
                        return await ctx.original_response()
                    except Exception:
                        return None
                return await ctx.followup.send(
                    content=content,
                    embed=embed,
                    view=view,
                    ephemeral=ephemeral,
                )
            except discord.InteractionResponded:
                return await ctx.followup.send(
                    content=content,
                    embed=embed,
                    view=view,
                    ephemeral=ephemeral,
                )

        return await ctx.send(content=content, embed=embed, view=view)
    except Exception as e:
        print("[AUCTION SEND ERROR]", e)
        return None


async def _defer(ctx: Union[commands.Context, discord.Interaction], ephemeral: bool = False):
    if isinstance(ctx, discord.Interaction) and not ctx.response.is_done():
        try:
            await ctx.response.defer(ephemeral=ephemeral)
        except Exception:
            pass


# =========================================================
# EMBEDS
# =========================================================
def get_color(rank: str):
    return {
        "truyen_thuyet": 0x00FFFF,
        "toi_thuong": 0xFF0000,
        "limited": 0xFF00FF,
    }.get(rank, 0xFFD700)


async def get_info(a):
    waifu_data = await get_waifu_data()
    return waifu_data.get(a["waifu_id"], {})


async def build_active_embed(a):
    info = await get_info(a)
    name = (
        info.get("name")
        or info.get("bio")
        or info.get("description")
        or a["waifu_id"]
    )
    bio = info.get("Bio") or info.get("bio") or info.get("description") or "Không có mô tả"
    rank = str(info.get("rank", "unknown")).strip().lower()
    highest = a.get("highest_bidder")

    e = discord.Embed(
        title="⚖️ BUỔI ĐẤU GIÁ ⚖️",
        description=(
            f"**{name}**\n"
            f"{bio}\n\n"
            f"Rank: **{rank}**\n"
            f"Seller: <@{a['seller']}>\n"
            f"Giá hiện tại: **{a.get('current_bid', 0)}**\n"
            f"{f'Người đang dẫn: <@{highest}>' if highest else 'Chưa có người bid'}\n\n"
            f"⏳ Còn hiệu lực"
        ),
        color=get_color(rank),
    )
    e.set_footer(text=f"Auction ID: {a.get('id')}")
    if info.get("image"):
        e.set_image(url=info["image"])
    return e


async def build_end_embed(a):
    info = await get_info(a)
    name = (
        info.get("name")
        or info.get("bio")
        or info.get("description")
        or a["waifu_id"]
    )
    bio = info.get("Bio") or info.get("bio") or info.get("description") or "Không có mô tả"
    winner = a.get("highest_bidder")
    seller = a["seller"]
    bid = a.get("current_bid", 0)

    e = discord.Embed(color=discord.Color.green())
    if winner and winner != seller:
        e.description = f"<@{winner}> thắng **{name}** với **{bid}** gold"
    else:
        e.description = f"Không ai mua **{name}**, trả về <@{seller}>"

    e.add_field(name="Thông tin", value=bio, inline=False)
    e.set_footer(text=f"Auction ID: {a.get('id')}")
    if info.get("image"):
        e.set_image(url=info["image"])
    return e


# =========================================================
# VIEW / MODAL
# =========================================================
class BidModal(discord.ui.Modal, title="Đặt giá"):
    amount = discord.ui.TextInput(label="Gold", required=True)

    def __init__(self, aid: str):
        super().__init__()
        self.aid = str(aid)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        uid = str(interaction.user.id)
        if not check_cooldown(uid, self.aid):
            return await interaction.followup.send("⏳ Spam ít thôi!", ephemeral=True)

        try:
            bid = int(str(self.amount.value).strip())
        except Exception:
            return await interaction.followup.send("❌ Sai số", ephemeral=True)

        if bid <= 0:
            return await interaction.followup.send("❌ Gold phải lớn hơn 0", ephemeral=True)

        async with get_auction_lock(self.aid):
            auctions = await load_auctions()
            a = _normalize_auction(auctions.get(self.aid))
            if not a:
                return await interaction.followup.send("❌ Không tồn tại", ephemeral=True)

            if time.time() >= float(a.get("end_time", 0)):
                return await interaction.followup.send("❌ Đã kết thúc", ephemeral=True)

            if uid == str(a.get("seller")):
                return await interaction.followup.send("❌ Không thể tự bid", ephemeral=True)

            cur = int(a.get("current_bid", 0))
            min_price = int(a.get("min_price", 0))
            step = int(a.get("step", 1))

            if cur == 0:
                if bid < min_price:
                    return await interaction.followup.send("❌ Chưa đạt giá tối thiểu", ephemeral=True)
            else:
                if bid < cur + step:
                    return await interaction.followup.send("❌ Không đủ bước giá", ephemeral=True)

            # Trừ gold bidder
            if not await data_user.remove_gold(uid, bid):
                return await interaction.followup.send("❌ Không đủ gold", ephemeral=True)

            prev = a.get("highest_bidder")
            prev_bid = int(a.get("current_bid", 0))

            # Hoàn gold người bị outbid
            if prev and prev != uid and prev_bid > 0:
                try:
                    ok_refund = await data_user.add_gold(str(prev), prev_bid)
                    if not ok_refund:
                        await data_user.add_gold(uid, bid)
                        return await interaction.followup.send("❌ Lỗi hoàn gold cho người bid trước", ephemeral=True)
                except Exception:
                    try:
                        await data_user.add_gold(uid, bid)
                    except Exception:
                        pass
                    return await interaction.followup.send("❌ Lỗi hoàn gold cho người bid trước", ephemeral=True)

            a["highest_bidder"] = uid
            a["current_bid"] = bid

            # Gia hạn nếu gần hết giờ
            if float(a.get("end_time", 0)) - time.time() < 10:
                a["end_time"] = float(a["end_time"]) + 15

            auctions[self.aid] = a
            await save_auctions(auctions)
            await update_all_embeds(interaction.client, self.aid, a, False)

        await interaction.followup.send("✅ Đã bid", ephemeral=True)


class BidButton(discord.ui.Button):
    def __init__(self, aid: str):
        super().__init__(
            label="Đấu giá",
            style=discord.ButtonStyle.green,
            custom_id=f"bid:{aid}",
        )

    async def callback(self, interaction: discord.Interaction):
        aid = self.custom_id.split(":", 1)[1]
        await interaction.response.send_modal(BidModal(aid))


class BidView(discord.ui.View):
    def __init__(self, aid: str):
        super().__init__(timeout=None)
        self.add_item(BidButton(aid))


# =========================================================
# UPDATE / BOOTSTRAP
# =========================================================
async def _safe_get_channel(bot, channel_id: str):
    try:
        ch = bot.get_channel(int(channel_id))
        if ch is not None:
            return ch
        return await bot.fetch_channel(int(channel_id))
    except Exception:
        return None


async def _ensure_panel_for_guild(bot, aid: str, a: Dict[str, Any], gid: str, ch_id: str):
    try:
        ch = await _safe_get_channel(bot, ch_id)
        if ch is None:
            return

        embed = await build_active_embed(a)
        view = BidView(aid)
        msg_key = f"message_id_{gid}"
        msg_id = a.get(msg_key)

        if msg_id:
            try:
                msg = await ch.fetch_message(int(msg_id))
                await msg.edit(embed=embed, view=view)
                return
            except Exception:
                pass

        msg = await ch.send(embed=embed, view=view)
        a[msg_key] = msg.id
    except Exception:
        return


async def update_all_embeds(bot, aid, a, ended=False):
    channels = await get_channels()
    for gid, ch_data in channels.items():
        ch_id = ch_data.get("auction_channel_id") if isinstance(ch_data, dict) else ch_data
        msg_id = a.get(f"message_id_{gid}")

        if not ch_id or not msg_id:
            continue

        try:
            ch = await _safe_get_channel(bot, ch_id)
            if ch is None:
                continue

            msg = await ch.fetch_message(int(msg_id))
            embed = await build_end_embed(a) if ended else await build_active_embed(a)
            view = None if ended else BidView(aid)
            await msg.edit(embed=embed, view=view)
        except Exception:
            continue


async def _bootstrap_auctions(bot):
    await bot.wait_until_ready()
    while not bot.is_closed():
        try:
            auctions = await load_auctions()
            channels = await get_channels()
            changed = False

            for aid, a in list(auctions.items()):
                if not isinstance(a, dict):
                    continue

                bot.add_view(BidView(aid))

                for gid, ch_data in channels.items():
                    ch_id = ch_data.get("auction_channel_id") if isinstance(ch_data, dict) else ch_data
                    if not ch_id:
                        continue

                    msg_key = f"message_id_{gid}"
                    if a.get(msg_key):
                        continue

                    await _ensure_panel_for_guild(bot, aid, a, str(gid), str(ch_id))
                    changed = True

            if changed:
                await save_auctions(auctions)
        except Exception as e:
            print("[AUCTION BOOTSTRAP ERROR]", e)

        await asyncio.sleep(20)


# =========================================================
# CREATE AUCTION
# =========================================================
async def dau_gia_logic(ctx, waifu_id, min_price, step):
    await _defer(ctx, ephemeral=True)

    uid = str(_get_user(ctx).id)
    client = _get_client(ctx)

    waifu_id = str(waifu_id)
    min_price = int(min_price)
    step = int(step)

    if min_price <= 0:
        return await _send(ctx, "❌ Giá mở màn phải lớn hơn 0", ephemeral=True)
    if step <= 0:
        return await _send(ctx, "❌ Bước giá phải lớn hơn 0", ephemeral=True)

    waifu_data = await get_waifu_data()
    waifu_info = waifu_data.get(waifu_id, {})
    rank = str(waifu_info.get("rank", "")).strip().lower()

    if rank not in ALLOWED_AUCTION_RANKS:
        return await _send(
            ctx,
            "❌ Chỉ rank truyen_thuyet / toi_thuong / limited mới được tạo đấu giá",
            ephemeral=True,
        )

    async with GLOBAL_LOCK:
        inv = await get_inventory(uid)
        waifus = inv.setdefault("waifus", {})

        if waifu_id not in waifus:
            return await _send(ctx, "❌ Bạn không sở hữu waifu này", ephemeral=True)

        raw_val = waifus.pop(waifu_id)
        if isinstance(raw_val, dict):
            love = int(raw_val.get("love", 0))
        elif isinstance(raw_val, int):
            love = int(raw_val)
        else:
            love = 0

        if not await save_inventory(uid, inv):
            return await _send(ctx, "❌ Không lưu được inventory", ephemeral=True)

        aid = str(uuid.uuid4())
        a = {
            "id": aid,
            "waifu_id": waifu_id,
            "seller": uid,
            "min_price": min_price,
            "step": step,
            "current_bid": 0,
            "highest_bidder": None,
            "end_time": time.time() + 86400,
            "love": love,
        }

        channels = await get_channels()
        for gid, ch_data in channels.items():
            ch_id = ch_data.get("auction_channel_id") if isinstance(ch_data, dict) else ch_data
            if not ch_id:
                continue

            try:
                ch = await _safe_get_channel(client, ch_id)
                if ch is None:
                    continue

                msg = await ch.send(embed=await build_active_embed(a), view=BidView(aid))
                a[f"message_id_{gid}"] = msg.id
            except Exception:
                continue

        auctions = await load_auctions()
        auctions[aid] = a
        await save_auctions(auctions)

    await _send(ctx, "✅ Tạo đấu giá thành công!", ephemeral=isinstance(ctx, discord.Interaction))


# =========================================================
# AUCTION LOOP
# =========================================================
async def auction_realtime_loop(bot):
    await bot.wait_until_ready()

    while not bot.is_closed():
        try:
            auctions = await load_auctions()
            if not isinstance(auctions, dict):
                auctions = {}

            ended = []
            dirty_inventories: Dict[str, Dict[str, Any]] = {}

            async def get_cached_inventory(user_id: str):
                if user_id not in dirty_inventories:
                    dirty_inventories[user_id] = await get_inventory(user_id)
                return dirty_inventories[user_id]

            now = time.time()

            for aid, a in list(auctions.items()):
                if not isinstance(a, dict):
                    continue

                if now < float(a.get("end_time", 0)):
                    continue

                async with get_auction_lock(aid):
                    a = _normalize_auction(auctions.get(aid))
                    if not a:
                        continue

                    waifu = str(a.get("waifu_id", ""))
                    seller = str(a.get("seller", ""))
                    winner = a.get("highest_bidder")
                    bid = int(a.get("current_bid", 0))
                    love = int(a.get("love", 0))

                    if not waifu or not seller:
                        ended.append(aid)
                        continue

                    if winner and str(winner) != seller:
                        winner = str(winner)
                        winner_inv = await get_cached_inventory(winner)
                        winner_inv.setdefault("waifus", {})
                        winner_inv.setdefault("bag", {})

                        if waifu not in winner_inv["waifus"]:
                            winner_inv["waifus"][waifu] = love
                        else:
                            winner_inv["bag"][waifu] = int(winner_inv["bag"].get(waifu, 0)) + 1

                        try:
                            await data_user.add_gold(seller, bid)
                        except Exception as e:
                            print("[AUCTION ADD GOLD ERROR]", e)
                    else:
                        seller_inv = await get_cached_inventory(seller)
                        seller_inv.setdefault("waifus", {})
                        seller_inv.setdefault("bag", {})

                        if waifu not in seller_inv["waifus"]:
                            seller_inv["waifus"][waifu] = love
                        else:
                            seller_inv["bag"][waifu] = int(seller_inv["bag"].get(waifu, 0)) + 1

                    ended.append(aid)
                    await update_all_embeds(bot, aid, a, True)

            for user_id, inv in dirty_inventories.items():
                await save_inventory(user_id, inv)

            if ended:
                for aid in ended:
                    auctions.pop(aid, None)
                await save_auctions(auctions)

        except Exception as e:
            print("[AUCTION LOOP ERROR]", e)

        await asyncio.sleep(5)


# Alias để tương thích với file cũ / main.py cũ
auction_loop = auction_realtime_loop


# =========================================================
# SETUP
# =========================================================
async def setup(bot):
    auctions = await load_auctions()
    for aid in auctions:
        bot.add_view(BidView(aid))

    if not getattr(bot, "_auction_tasks_started", False):
        bot._auction_tasks_started = True
        bot.loop.create_task(auction_realtime_loop(bot))
        bot.loop.create_task(_bootstrap_auctions(bot))

    print("Loaded auction has success")

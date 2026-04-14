from __future__ import annotations

import asyncio
from typing import Any, Dict

import discord

import api_client
from Commands import dau_gia
from Data import data_admin


# =========================================================
# huy_dau_gia.py (API mode)
# - Uses BotR/backend/app.py through api_client
# - Keeps auction lock logic from Commands/dau_gia.py
# - Restores waifu to seller, refunds highest bidder gold,
#   deletes auction messages, and removes auction from API
# =========================================================

GLOBAL_LOCK = dau_gia.GLOBAL_LOCK
get_auction_lock = dau_gia.get_auction_lock


def _normalize_inventory(inv: Any) -> Dict[str, Any]:
    if not isinstance(inv, dict):
        inv = {}

    inv.setdefault("waifus", {})
    inv.setdefault("bag", {})
    inv.setdefault("bag_item", {})
    inv.setdefault("default_waifu", None)

    if not isinstance(inv["waifus"], dict):
        inv["waifus"] = {}
    if not isinstance(inv["bag"], dict):
        inv["bag"] = {}
    if not isinstance(inv["bag_item"], dict):
        inv["bag_item"] = {}

    return inv


async def get_auctions() -> Dict[str, Any]:
    data = await api_client.get_auction()
    return data if isinstance(data, dict) else {}


async def update_auctions(auctions: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(auctions, dict):
        auctions = {}
    return await api_client.set_auction(auctions)


async def get_inventory(user_id: str) -> Dict[str, Any]:
    data = await api_client.get_inventory(str(user_id))
    return _normalize_inventory(data)


async def update_inventory(user_id: str, inv: Dict[str, Any]) -> Dict[str, Any]:
    inv = _normalize_inventory(inv)
    return await api_client.post(f"/inventory/{user_id}/update", inv)


async def add_gold(user_id: str, amount: int) -> bool:
    return await api_client.add_gold(str(user_id), int(amount))


async def get_auction_channels() -> Dict[str, Any]:
    data = await api_client.get_auction_channels()
    return data if isinstance(data, dict) else {}


async def huy_dau_gia_logic(interaction, auction_id: str):
    await interaction.response.defer(ephemeral=True)

    auctions = await get_auctions()
    auction = auctions.get(auction_id)

    if not auction:
        return await interaction.followup.send("❌ Auction không tồn tại!")

    uid = str(interaction.user.id)
    seller = str(auction.get("seller", ""))

    is_admin = uid in list(map(str, getattr(data_admin, "ADMINS", [])))
    if not is_admin and uid != seller:
        return await interaction.followup.send("❌ Không có quyền hủy!")

    async with get_auction_lock(auction_id):
        # Reload tránh stale data
        auctions = await get_auctions()
        auction = auctions.get(auction_id)

        if not auction:
            return await interaction.followup.send("❌ Auction đã bị xử lý trước đó!")

        waifu_id = str(auction.get("waifu_id", ""))
        love = auction.get("love", 1)

        if not waifu_id:
            return await interaction.followup.send("❌ Dữ liệu auction không hợp lệ!")

        # ===== TRẢ WAIFU =====
        async with GLOBAL_LOCK:
            inv = await get_inventory(seller)
            inv["waifus"][waifu_id] = love
            await update_inventory(seller, inv)

        # ===== HOÀN GOLD =====
        highest = auction.get("highest_bidder")
        current = int(auction.get("current_bid", 0))

        if highest and current > 0:
            try:
                await add_gold(str(highest), current)
            except Exception as e:
                print("[REFUND ERROR]", e)

        # ===== XÓA MESSAGE =====
        channels = await get_auction_channels()
        for gid, ch_data in channels.items():
            ch_id = ch_data.get("auction_channel_id") if isinstance(ch_data, dict) else ch_data
            msg_id = auction.get(f"message_id_{gid}")

            if not ch_id or not msg_id:
                continue

            try:
                ch = interaction.client.get_channel(int(ch_id)) or await interaction.client.fetch_channel(int(ch_id))
                if ch is None:
                    continue

                msg = ch.get_partial_message(int(msg_id))
                await msg.delete()
            except Exception as e:
                print("[DELETE MSG ERROR]", e)

        # ===== XÓA DATA =====
        auctions.pop(auction_id, None)
        dau_gia.auction_locks.pop(auction_id, None)
        await update_auctions(auctions)

    await interaction.followup.send("✅ Đã hủy đấu giá thành công!")

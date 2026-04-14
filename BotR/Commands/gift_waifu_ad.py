from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

import discord

from Data.data_admin import ADMINS
from Data import data_user
from BotR import api_client

FILE_LOCK = asyncio.Lock()


async def safe_send(interaction, content, ephemeral=False):
    try:
        if not interaction.response.is_done():
            await interaction.response.send_message(content, ephemeral=ephemeral)
        else:
            await interaction.followup.send(content, ephemeral=ephemeral)
    except Exception as e:
        print(f"[gift_waifu_ad] send error: {e}")


async def load_waifu_data() -> Dict[str, Any]:
    data = await api_client.get_waifu()
    return data if isinstance(data, dict) else {}


async def load_inventory() -> Dict[str, Any]:
    data = await api_client.get_inventory()
    return data if isinstance(data, dict) else {}


async def save_target_inventory(user_id: str, user_data: Dict[str, Any]) -> bool:
    res = await api_client.post(f"/inventory/{user_id}/update", user_data)
    return bool(res.get("success"))


async def save_waifu_data(waifu_data: Dict[str, Any]) -> bool:
    res = await api_client.set_waifu(waifu_data)
    return bool(res.get("success")) or isinstance(res, dict)


async def gift_waifu_ad_logic(interaction, waifu_id: str, user: discord.User = None):
    uid = str(interaction.user.id)

    # ===== ADMIN CHECK =====
    if uid not in list(map(str, ADMINS)):
        return await safe_send(
            interaction,
            "❌ Bạn không phải admin! Không được dùng lệnh này!",
            ephemeral=True,
        )

    waifu_id = str(waifu_id).strip()
    target = user or interaction.user
    target_id = str(target.id)

    async with FILE_LOCK:
        # ===== LOAD DATA FROM API =====
        waifu_data = await load_waifu_data()
        inventory = await load_inventory()

        if waifu_id not in waifu_data:
            return await safe_send(interaction, "❌ Waifu không tồn tại!", True)

        waifu = waifu_data[waifu_id]
        quantity = int(waifu.get("quantity", -1))
        claimed = int(waifu.get("claimed", 0))

        # ===== INIT TARGET USER =====
        target_data = inventory.get(target_id)
        if not isinstance(target_data, dict):
            target_data = {"waifus": {}, "bag": {}}
            inventory[target_id] = target_data

        waifus = target_data.get("waifus")
        if not isinstance(waifus, dict):
            waifus = {}
            target_data["waifus"] = waifus

        bag = target_data.get("bag")
        if not isinstance(bag, dict):
            bag = {}
            target_data["bag"] = bag

        # ===== LIMITED CHECK =====
        if quantity != -1 and claimed >= quantity:
            return await safe_send(
                interaction,
                "❌ Waifu này thuộc rank **Limited**, đã đạt giới hạn!",
                True,
            )

        # ===== DUPLICATE CHECK =====
        if waifu_id in waifus:
            return await safe_send(
                interaction,
                "❌ Người nhận đã sở hữu waifu này rồi!",
                True,
            )

        # ===== ADD WAIFU =====
        waifus[waifu_id] = 1
        if quantity != -1:
            waifu["claimed"] = claimed + 1

        # ===== SAVE BACK TO API =====
        ok_inventory = await save_target_inventory(target_id, target_data)
        ok_waifu = await save_waifu_data(waifu_data)

        if not ok_inventory or not ok_waifu:
            return await safe_send(
                interaction,
                "❌ Lưu dữ liệu thất bại, thử lại sau!",
                True,
            )

        # ===== RESPONSE =====
        await safe_send(
            interaction,
            f"✅ **{waifu_id}** đã được gửi cho {target.mention}. || ADMIN ||",
        )


# ===== SETUP =====
async def setup(bot):
    pass


print("Loaded gift waifu admin has success")

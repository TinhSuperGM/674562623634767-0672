from __future__ import annotations

import asyncio
import copy
import re
from typing import Any, Dict, Optional, Tuple

import discord

import api_client

# =========================
# PRICE
# =========================
PRICE = {
    "thuong": 180,
    "anh_hung": 360,
    "huyen_thoai": 680,
    "truyen_thuyet": 1080,
    "toi_thuong": 1750,
    "limited": 10000,
}

# =========================
# LOCKS
# =========================
USER_LOCKS: Dict[str, asyncio.Lock] = {}


def get_lock(user_id: str) -> asyncio.Lock:
    user_id = str(user_id)
    if user_id not in USER_LOCKS:
        USER_LOCKS[user_id] = asyncio.Lock()
    return USER_LOCKS[user_id]


# =========================
# HELPERS
# =========================
def normalize(text: str) -> str:
    if text is None:
        return ""
    text = str(text).strip().lower()
    text = text.replace(" ", "_")
    text = re.sub(r"_+", "_", text)
    return text


def ensure_user_struct(inv: dict):
    if not isinstance(inv.get("waifus"), dict):
        inv["waifus"] = {}
    if not isinstance(inv.get("bag"), dict):
        inv["bag"] = {}
    if "bag_item" not in inv or not isinstance(inv.get("bag_item"), dict):
        inv["bag_item"] = {}
    inv.setdefault("default_waifu", None)


def find_waifu_id(query: str, inv_waifus: dict, wdata: dict):
    q = normalize(query)

    if q in wdata:
        return q

    if q in inv_waifus:
        return q

    for wid, info in wdata.items():
        if isinstance(info, dict):
            name = info.get("name")
            if isinstance(name, str) and normalize(name) == q:
                return wid

    for wid in wdata.keys():
        if q in normalize(wid):
            return wid

    return None


async def _respond(interaction: discord.Interaction, content=None, **kwargs):
    try:
        if interaction.response.is_done():
            return await interaction.followup.send(content, **kwargs)
        return await interaction.response.send_message(content, **kwargs)
    except discord.InteractionResponded:
        return await interaction.followup.send(content, **kwargs)


async def load_waifu_data() -> Dict[str, Any]:
    data = await api_client.get_waifu()
    return data if isinstance(data, dict) else {}


async def get_inventory(user_id: str) -> Dict[str, Any]:
    data = await api_client.get_inventory(user_id)
    return data if isinstance(data, dict) else {}


async def update_inventory(user_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(data, dict):
        data = {}
    return await api_client.post(f"/inventory/{user_id}/update", data)


async def get_user_data(user_id: str) -> Dict[str, Any]:
    data = await api_client.get_user_data(user_id)
    return data if isinstance(data, dict) else {}


async def update_user_data(user_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(data, dict):
        data = {"gold": 0, "last_free": 0}
    return await api_client.post(f"/users/{user_id}/update", data)


# =========================
# CONFIRM VIEW (GIỮ NGUYÊN)
# =========================
class ConfirmView(discord.ui.View):
    def __init__(self, owner_id, waifu_id, gold, callback):
        super().__init__(timeout=30)
        self.owner_id = owner_id
        self.waifu_id = waifu_id
        self.gold = gold
        self.callback = callback
        self.done = False

    @discord.ui.button(label="Chắc chắn", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.owner_id:
            return await interaction.response.send_message("❌ Không phải của bạn!", ephemeral=True)

        if self.done:
            return await interaction.response.send_message("❌ Giao dịch đã xử lý.", ephemeral=True)

        self.done = True
        await interaction.response.defer(ephemeral=True)

        try:
            sold, total = await self.callback()
        except Exception as e:
            self.done = False
            return await interaction.followup.send(f"❌ Giao dịch thất bại: {e}", ephemeral=True)

        for item in self.children:
            item.disabled = True

        try:
            await interaction.edit_original_response(
                content=f"✅ Đã bán **{self.waifu_id}**! +{total} gold",
                view=self,
            )
        except Exception:
            await interaction.followup.send(
                f"✅ Đã bán **{self.waifu_id}**! +{total} gold",
                ephemeral=True,
            )

    @discord.ui.button(label="Hủy", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.owner_id:
            return await interaction.response.send_message("❌ Không phải của bạn!", ephemeral=True)

        for item in self.children:
            item.disabled = True

        await interaction.response.edit_message(content="❌ Đã hủy.", view=self)


# =========================
# LOGIC (API VERSION)
# =========================
async def sell_logic(interaction, waifu_id: str, source: str = None, amount: int = 1):
    uid = str(interaction.user.id)

    inv = await get_inventory(uid)
    w = await load_waifu_data()

    if not inv:
        return await _respond(interaction, "❌ Không có dữ liệu!", ephemeral=True)

    ensure_user_struct(inv)

    waifu_id = find_waifu_id(waifu_id, inv["waifus"], w)
    if not waifu_id:
        return await _respond(interaction, "❌ Waifu không tồn tại!", ephemeral=True)

    rank = normalize(w.get(waifu_id, {}).get("rank"))
    if not rank:
        return await _respond(interaction, "❌ Không có rank!", ephemeral=True)

    price = PRICE.get(rank, 0)
    if price <= 0:
        return await _respond(interaction, "❌ Không có giá!", ephemeral=True)

    bag_count = int(inv["bag"].get(waifu_id, 0))
    has_collection = waifu_id in inv["waifus"]

    if bag_count <= 0 and not has_collection:
        return await _respond(interaction, "❌ Không có waifu!", ephemeral=True)

    async def do_sell():
        lock = get_lock(uid)
        async with lock:
            inv2 = await get_inventory(uid)
            ensure_user_struct(inv2)

            user_data = await get_user_data(uid)
            if not isinstance(user_data, dict):
                user_data = {"gold": 0, "last_free": 0}

            inv_before = copy.deepcopy(inv2)
            user_before = copy.deepcopy(user_data)

            bag_count2 = int(inv2["bag"].get(waifu_id, 0))
            has_collection2 = waifu_id in inv2["waifus"]

            sold = 0

            if source == "bag":
                take = min(amount, bag_count2)
                if take <= 0:
                    raise Exception("Hết waifu trong bag")

                inv2["bag"][waifu_id] -= take
                if inv2["bag"][waifu_id] <= 0:
                    del inv2["bag"][waifu_id]
                sold = take

            elif source == "collection":
                if not has_collection2:
                    raise Exception("Không còn trong collection")

                del inv2["waifus"][waifu_id]
                sold = 1

            else:
                if bag_count2 > 0:
                    take = min(amount, bag_count2)
                    inv2["bag"][waifu_id] -= take
                    if inv2["bag"][waifu_id] <= 0:
                        del inv2["bag"][waifu_id]
                    sold += take

                if sold == 0 and has_collection2:
                    del inv2["waifus"][waifu_id]
                    sold = 1

            if sold <= 0:
                raise Exception("Không còn waifu")

            total = sold * price

            current_gold = int(user_data.get("gold", 0) or 0)
            user_data["gold"] = current_gold + total

            try:
                await update_inventory(uid, inv2)
                await update_user_data(uid, user_data)
            except Exception:
                await update_inventory(uid, inv_before)
                await update_user_data(uid, user_before)
                raise

            return sold, total

    if rank in ["truyen_thuyet", "toi_thuong", "limited"]:
        view = ConfirmView(interaction.user.id, waifu_id, price, do_sell)
        return await interaction.response.send_message(
            f"⚠️ Bán {waifu_id} để nhận {price} gold?",
            view=view,
            ephemeral=True,
        )

    await interaction.response.defer(thinking=True)
    sold, total = await do_sell()

    try:
        if interaction.response.is_done():
            await interaction.followup.send(f"✅ Đã bán {waifu_id}, nhận {total} gold!")
        else:
            await interaction.response.send_message(f"✅ Đã bán {waifu_id}, nhận {total} gold!")
    except Exception:
        await interaction.followup.send(f"✅ Đã bán {waifu_id}, nhận {total} gold!")


# =========================
# SETUP
# =========================
async def setup(bot):
    print("Loaded sell (API) success")

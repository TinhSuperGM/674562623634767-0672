from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

import discord
from discord.ui import View, Button

from Data import data_user
import api_client

# =========================================================
# give.py (API mode)
# - Gold transfer uses Data.data_user wrapper -> API
# - Waifu transfer uses BotR/api_client.py inventory + waifu API
# - Keeps old gift_logic signature for existing callers
# =========================================================

GIVE_LOCK = asyncio.Lock()


# ===== RESPOND HELPERS =====
async def _defer_if_needed(interaction: discord.Interaction, *, ephemeral: bool = True):
    try:
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=ephemeral)
    except Exception:
        pass


async def _send(interaction: discord.Interaction, content=None, **kwargs):
    try:
        if interaction.response.is_done():
            return await interaction.followup.send(content, **kwargs)
        return await interaction.response.send_message(content, **kwargs)
    except discord.InteractionResponded:
        return await interaction.followup.send(content, **kwargs)


# ===== API HELPERS =====
async def load_waifu_data() -> Dict[str, Any]:
    data = await api_client.get_waifu()
    return data if isinstance(data, dict) else {}


async def get_inventory(user_id: str) -> Dict[str, Any]:
    data = await api_client.get_inventory(str(user_id))
    return data if isinstance(data, dict) else {}


async def update_inventory(user_id: str, inventory_data: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(inventory_data, dict):
        inventory_data = {"waifus": {}, "bag": {}, "bag_item": {}}
    return await api_client.post(f"/inventory/{user_id}/update", inventory_data)


# ===== INTERNAL CONFIRM VIEW =====
class ConfirmView(View):
    def __init__(self):
        super().__init__(timeout=60)
        self.result: Optional[bool] = None

    @discord.ui.button(label="Chắc chắn", style=discord.ButtonStyle.green)
    async def confirm(self, interaction2: discord.Interaction, button: Button):
        await interaction2.response.defer()
        self.result = True
        self.stop()

    @discord.ui.button(label="Hủy", style=discord.ButtonStyle.red)
    async def cancel(self, interaction2: discord.Interaction, button: Button):
        await interaction2.response.defer()
        self.result = False
        self.stop()


# ===== LOGIC =====
async def gift_logic(
    interaction,
    type: str,
    user: discord.User,
    amount: int = None,
    waifu_id: str = None,
):
    """
    type == "gold"  -> chuyển gold
    type == "waifu" -> tặng waifu
    """
    sender = interaction.user

    async with GIVE_LOCK:
        await _defer_if_needed(interaction, ephemeral=True)

        # Load API data
        sender_inv = await get_inventory(str(sender.id))
        recipient_inv = await get_inventory(str(user.id))
        waifu_data = await load_waifu_data()

        # Ensure schema keys exist
        sender_inv.setdefault("waifus", {})
        sender_inv.setdefault("bag", {})
        sender_inv.setdefault("bag_item", {})

        recipient_inv.setdefault("waifus", {})
        recipient_inv.setdefault("bag", {})
        recipient_inv.setdefault("bag_item", {})

        # =========================================================
        # ===================== GIFT GOLD ==========================
        # =========================================================
        if type == "gold":
            if amount is None or amount <= 0:
                return await _send(interaction, "❌ Số gold không hợp lệ!", ephemeral=True)

            if sender.id == user.id:
                return await _send(interaction, "❌ Không thể tự chuyển gold!", ephemeral=True)

            fee = int(amount * 0.05)
            received = amount - fee

            # Remove from sender first
            success = await data_user.remove_gold(sender.id, amount)
            if not success:
                return await _send(interaction, "❌ Không đủ gold!", ephemeral=True)

            # Add to recipient, rollback sender if failed
            try:
                ok = await data_user.add_gold(user.id, received)
                if not ok:
                    await data_user.add_gold(sender.id, amount)
                    return await _send(interaction, "❌ Lỗi khi chuyển gold!", ephemeral=True)
            except Exception as e:
                print("[GIFT GOLD ERROR]", e)
                try:
                    await data_user.add_gold(sender.id, amount)
                except Exception:
                    pass
                return await _send(interaction, "❌ Lỗi khi chuyển gold!", ephemeral=True)

            return await _send(
                interaction,
                f"{sender.mention} chuyển {amount} <a:gold:1492792339436142703> cho {user.mention}\n"
                f"Phí: {fee} <a:gold:1492792339436142703> | Nhận: {received} <a:gold:1492792339436142703>",
                ephemeral=False,
            )

        # =========================================================
        # ===================== GIFT WAIFU =========================
        # =========================================================
        elif type == "waifu":
            if waifu_id is None:
                return await _send(interaction, "❌ Chưa chọn waifu!", ephemeral=True)

            if sender.id == user.id:
                return await _send(interaction, "❌ Không thể tự tặng!", ephemeral=True)

            bag = sender_inv["bag"]
            owned = sender_inv["waifus"]

            # Check ownership
            if waifu_id in bag and int(bag.get(waifu_id, 0)) > 0:
                source = "bag"
            elif waifu_id in owned:
                source = "waifus"
            else:
                return await _send(interaction, "❌ Bạn không có waifu này!", ephemeral=True)

            rank = waifu_data.get(waifu_id, {}).get("rank", "thường")
            name = waifu_data.get(waifu_id, {}).get("name", waifu_id)

            # Confirm for rare ranks
            if rank in ["truyen_thuyet", "toi_thuong", "limited"]:
                view = ConfirmView()
                await _send(
                    interaction,
                    f"⚠️ Gửi **{name}** (rank {rank})?\nBạn chắc chưa?",
                    view=view,
                )

                await view.wait()
                if view.result is None:
                    return await interaction.followup.send("⌛ Hết giờ, auto hủy!", ephemeral=True)
                if not view.result:
                    return await interaction.followup.send("❌ Đã hủy!", ephemeral=True)

            try:
                # Remove from sender
                if source == "bag":
                    bag[waifu_id] -= 1
                    if bag[waifu_id] <= 0:
                        del bag[waifu_id]
                else:
                    owned.pop(waifu_id, None)

                # Add to recipient bag
                recipient_inv["bag"][waifu_id] = int(recipient_inv["bag"].get(waifu_id, 0)) + 1

                # Save both inventories
                await update_inventory(str(sender.id), sender_inv)
                await update_inventory(str(user.id), recipient_inv)

            except Exception as e:
                print("[GIFT ERROR]", e)
                return await _send(interaction, "❌ Lỗi khi chuyển waifu!", ephemeral=True)

            return await _send(
                interaction,
                f"✈️ {sender.mention} đã tặng **{name}** cho {user.mention}",
                ephemeral=False,
            )

        # =========================================================
        # ===================== INVALID TYPE =======================
        # =========================================================
        else:
            return await _send(interaction, "❌ Loại quà không hợp lệ!", ephemeral=True)


# ===== SETUP =====
async def setup(bot):
    pass


print("Loaded gift has success")

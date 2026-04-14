import discord
from discord.ui import View, Button

from Data import data_user
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


# ===== LOGIC =====
async def gift_logic(interaction, type: str, user: discord.User, amount: int = None, waifu_id: str = None):
    from Data.api_client import get_inventory, add_item, remove_item
    sender = interaction.user

    if type == "gold":
        await _defer_if_needed(interaction, ephemeral=True)

    # ===== LOAD DATA (API) =====
    sender_inv = await get_inventory(str(sender.id))
    recipient_inv = await get_inventory(str(user.id))
    waifu_data = await load_waifu_data()

    # đảm bảo key tồn tại (KHÔNG phá schema)
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

        success = await data_user.remove_gold(sender.id, amount)
        if not success:
            return await _send(interaction, "❌ Không đủ gold!", ephemeral=True)

        try:
            await data_user.add_gold(user.id, received)
        except Exception as e:
            print("[GIFT GOLD ERROR]", e)
            try:
                await data_user.add_gold(sender.id, amount)
            except Exception:
                pass
            return await _send(interaction, "❌ Lỗi khi chuyển gold!", ephemeral=True)

        return await _send(
            interaction,
            f"💸 {sender.mention} chuyển {amount} <a:gold:1492792339436142703> cho {user.mention}\n"
            f"📉 Phí: {fee} <a:gold:1492792339436142703> | Nhận: {received} <a:gold:1492792339436142703>",
            ephemeral=False
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

        # ===== CHECK OWN =====
        if waifu_id in bag and bag[waifu_id] > 0:
            source = "bag"
        elif waifu_id in owned:
            source = "waifus"
        else:
            return await _send(interaction, "❌ Bạn không có waifu này!", ephemeral=True)

        rank = waifu_data.get(waifu_id, {}).get("rank", "thường")
        name = waifu_data.get(waifu_id, {}).get("name", waifu_id)

        # ===== CONFIRM =====
        if rank in ["truyen_thuyet", "toi_thuong", "limited"]:
            class ConfirmView(View):
                def __init__(self):
                    super().__init__(timeout=60)
                    self.result = None

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

            view = ConfirmView()

            await _send(
                interaction,
                f"⚠️ Gửi **{name}** (rank {rank})?\nBạn chắc chưa?",
                view=view
            )

            await view.wait()

            if view.result is None:
                return await interaction.followup.send("⌛ Hết giờ, auto hủy!", ephemeral=True)

            if not view.result:
                return await interaction.followup.send("❌ Đã hủy!", ephemeral=True)

        # ===== TRANSACTION =====
        try:
            # REMOVE
            if source == "bag":
                bag[waifu_id] -= 1
                if bag[waifu_id] <= 0:
                    del bag[waifu_id]
            else:
                owned.pop(waifu_id, None)

            # ADD
            recipient_inv["bag"][waifu_id] = recipient_inv["bag"].get(waifu_id, 0) + 1

            # ===== SAVE API =====
            await update_inventory(str(sender.id), sender_inv)
            await update_inventory(str(user.id), recipient_inv)

        except Exception as e:
            print("[GIFT ERROR]", e)
            return await _send(interaction, "❌ Lỗi khi chuyển waifu!", ephemeral=True)

        return await interaction.followup.send(
            f"✈️ {sender.mention} đã tặng **{name}** cho {user.mention} 🥰"
        )


# ===== SETUP =====
async def setup(bot):
    pass


print("Loaded gift has success")
from __future__ import annotations

import asyncio
import copy
import inspect
import random
import time
from typing import Any, Dict, Optional

import discord
from discord.ui import Button, Modal, TextInput, View

from Commands.prayer import get_luck
from Data.level import sync_all
import api_client

# =========================================================
# setup.py (API mode)
# - No direct JSON file access
# - Uses BotR/api_client.py for all runtime data
# - Keeps old public function names for compatibility
# =========================================================

_USER_LOCKS: Dict[str, asyncio.Lock] = {}


def _get_user_lock(user_id: str) -> asyncio.Lock:
    user_id = str(user_id)
    lock = _USER_LOCKS.get(user_id)
    if lock is None:
        lock = asyncio.Lock()
        _USER_LOCKS[user_id] = lock
    return lock


async def _maybe_await(value):
    if inspect.isawaitable(value):
        return await value
    return value


async def _api_get(endpoint: str) -> Dict[str, Any]:
    data = await api_client.get(endpoint)
    return data if isinstance(data, dict) else {}


async def _api_post(endpoint: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    data = await api_client.post(endpoint, payload or {})
    return data if isinstance(data, dict) else {}


def _ensure_dict(data):
    return data if isinstance(data, dict) else {}


# =========================
# API STORAGE HELPERS
# =========================
async def load_channels():
    return _ensure_dict(await _api_get("/data/auction_channels"))


async def save_channels(data):
    if not isinstance(data, dict):
        data = {}
    return await _api_post("/data/auction_channels/update", data)


async def load_auctions():
    return _ensure_dict(await _api_get("/data/auction"))


async def save_auctions(data):
    if not isinstance(data, dict):
        data = {}
    return await _api_post("/data/auction/update", data)


async def load_inventory():
    return _ensure_dict(await _api_get("/inventory"))


async def save_inventory(data):
    if not isinstance(data, dict):
        data = {}
    return await _api_post("/data/inventory/update", data)


async def load_waifu_data():
    return _ensure_dict(await _api_get("/waifu"))


async def save_waifu_data(data):
    if not isinstance(data, dict):
        data = {}
    return await _api_post("/waifu/update", data)


async def get_user_data(user_id: str) -> Dict[str, Any]:
    data = await _api_get(f"/users/{user_id}")
    if not isinstance(data, dict):
        data = {}
    data.setdefault("gold", 0)
    data.setdefault("last_free", 0)
    return data


async def save_user_data(user_id: str, user_data: Dict[str, Any]):
    if not isinstance(user_data, dict):
        user_data = {"gold": 0, "last_free": 0}
    return await _api_post(f"/users/{user_id}/update", user_data)


# =========================
# SAFE HELPERS
# =========================
async def _defer_if_needed(interaction: discord.Interaction, *, ephemeral: bool = True):
    try:
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=ephemeral)
    except Exception:
        pass


async def _respond(interaction: discord.Interaction, content=None, **kwargs):
    try:
        if interaction.response.is_done():
            return await interaction.followup.send(content, **kwargs)
        return await interaction.response.send_message(content, **kwargs)
    except discord.InteractionResponded:
        return await interaction.followup.send(content, **kwargs)


def _ensure_inventory_schema(inventory: Dict[str, Any], user_id: str) -> Dict[str, Any]:
    user_id = str(user_id)
    user_inv = inventory.get(user_id)
    if not isinstance(user_inv, dict):
        user_inv = {}
        inventory[user_id] = user_inv

    if not isinstance(user_inv.get("waifus"), dict):
        user_inv["waifus"] = {}
    if not isinstance(user_inv.get("bag"), dict):
        user_inv["bag"] = {}
    if not isinstance(user_inv.get("bag_item"), dict):
        user_inv["bag_item"] = {}
    if "default_waifu" not in user_inv:
        user_inv["default_waifu"] = None

    return user_inv


async def _rollback_user_snapshot(user_id: str, snapshot: Dict[str, Any]):
    try:
        await save_user_data(user_id, snapshot)
    except Exception:
        pass


async def _rollback_inventory_snapshot(snapshot: Dict[str, Any]):
    try:
        await save_inventory(snapshot)
    except Exception:
        pass


async def _rollback_waifu_snapshot(snapshot: Dict[str, Any]):
    try:
        await save_waifu_data(snapshot)
    except Exception:
        pass


# =========================
# AUCTION / RANK / SHOP / ROLL CHANNEL SETUP
# =========================
async def setup_channel_logic(interaction, type: str, channel_id: str):
    await _defer_if_needed(interaction, ephemeral=True)

    guild = interaction.guild
    if not guild:
        return await _respond(interaction, "❌ Chỉ dùng trong server!", ephemeral=True)

    if not interaction.user.guild_permissions.administrator:
        return await _respond(interaction, "❌ Cần quyền admin!", ephemeral=True)

    if not type:
        return await _respond(interaction, "❌ Thiếu type!", ephemeral=True)

    if not channel_id:
        return await _respond(interaction, "❌ Thiếu channel ID!", ephemeral=True)

    try:
        ch_id = int(channel_id)
    except Exception:
        return await _respond(interaction, "❌ ID không hợp lệ!", ephemeral=True)

    channel = guild.get_channel(ch_id)
    if not channel:
        try:
            channel = await guild.fetch_channel(ch_id)
        except Exception:
            return await _respond(interaction, "❌ Không tìm thấy channel!", ephemeral=True)

    type = str(type).strip().lower()
    type_alias = {
        "rank": "ranking",
        "leaderboard": "ranking",
        "rollwaifu": "roll",
        "roll_waifu": "roll",
        "roll-waifu": "roll",
    }
    type = type_alias.get(type, type)

    channels = await load_channels()
    guild_key = str(guild.id)

    if guild_key not in channels or not isinstance(channels.get(guild_key), dict):
        channels[guild_key] = {}

    if type == "auction":
        old_channel_id = channels[guild_key].get("auction_channel_id")
        auctions = await load_auctions()

        if old_channel_id and int(old_channel_id) != ch_id:
            try:
                old_channel = guild.get_channel(int(old_channel_id))
                if not old_channel:
                    old_channel = await guild.fetch_channel(int(old_channel_id))
            except Exception:
                old_channel = None

            if old_channel:
                for auction_id, auction in list(auctions.items()):
                    if not isinstance(auction, dict):
                        continue

                    msg_key = f"message_id_{guild_key}"
                    msg_id = auction.get(msg_key)
                    if msg_id:
                        try:
                            msg = await old_channel.fetch_message(int(msg_id))
                            await msg.delete()
                        except Exception:
                            pass
                        auction.pop(msg_key, None)

                await save_auctions(auctions)

        channels[guild_key]["auction_channel_id"] = ch_id
        await save_channels(channels)
        return await _respond(
            interaction,
            f"✅ Set kênh đấu giá: {channel.mention}",
            ephemeral=True,
        )

    if type == "ranking":
        channels[guild_key]["leaderboard_channel_id"] = ch_id
        await save_channels(channels)
        return await _respond(
            interaction,
            f"✅ Set kênh BXH: {channel.mention}",
            ephemeral=True,
        )

    if type == "shop":
        channels[guild_key]["shop_channel_id"] = ch_id
        await save_channels(channels)
        return await _respond(
            interaction,
            f"✅ Set kênh shop: {channel.mention}",
            ephemeral=True,
        )

    if type in ("roll", "roll_waifu"):
        channels[guild_key]["roll_waifu_channel_id"] = ch_id
        await save_channels(channels)
        return await _respond(
            interaction,
            f"✅ Set kênh roll waifu: {channel.mention}",
            ephemeral=True,
        )

    return await _respond(interaction, "❌ Type không hợp lệ!", ephemeral=True)


# =========================
# ROLL LOGIC
# =========================
def roll_rank(level, luck=0):
    shift_percent = luck / 100

    if level in ["free", "200"]:
        ranks = [None, "thuong", "anh_hung", "huyen_thoai", "truyen_thuyet"]
        rates = [0.40, 0.30, 0.20, 0.08, 0.02]
    elif level == "500":
        ranks = [None, "thuong", "anh_hung", "huyen_thoai", "truyen_thuyet"]
        rates = [0.30, 0.20, 0.25, 0.20, 0.05]
    elif level == "1000":
        ranks = [None, "thuong", "anh_hung", "huyen_thoai", "truyen_thuyet", "toi_thuong"]
        rates = [0.15, 0.15, 0.20, 0.30, 0.18, 0.02]
    elif level == "2000":
        ranks = ["thuong", "anh_hung", "huyen_thoai", "truyen_thuyet", "toi_thuong"]
        rates = [0.15, 0.30, 0.40, 0.10, 0.05]
    else:
        return None

    for i in range(len(rates) - 1):
        shift = rates[i] * shift_percent
        rates[i] -= shift
        rates[i + 1] += shift

    r = random.random()
    current = 0
    for rank, rate in zip(ranks, rates):
        current += rate
        if r <= current:
            return rank

    return ranks[-1] if ranks else None


def get_random_waifu(waifu_data, rank):
    pool = []
    for wid, data in waifu_data.items():
        if not isinstance(data, dict):
            continue

        if data.get("rank") == rank and (
            data.get("quantity", -1) == -1 or data.get("claimed", 0) < data.get("quantity", -1)
        ):
            pool.append(wid)

    if not pool:
        return None
    return random.choice(pool)


def build_roll_embed():
    embed = discord.Embed(
        title="Cổng Triệu Hồi Waifu",
        description=(
            "**Mỗi ngày, cổng triệu hồi sẽ ban tặng bạn một lượt roll miễn phí.**\n"
            "Ngoài ra, bạn còn có thể dùng Gold để thực hiện nghi thức triệu hồi.\n\n"
            "**Thẻ Đồng**\n"
            "> - 2% - Truyền Thuyết\n"
            "> - 8% - Huyền Thoại\n"
            "> - 20% - Anh Hùng\n"
            "> - 30% - Thường\n"
            "> - 40% - Hụt\n\n"
            "**Hãy chọn mức Free / 200 để quay Thẻ Đồng**\n\n"
            "**Thẻ Bạc**\n"
            "> - 5% - Truyền Thuyết\n"
            "> - 20% - Huyền Thoại\n"
            "> - 25% - Anh Hùng\n"
            "> - 20% - Thường\n"
            "> - 30% - Hụt\n\n"
            "**Hãy chọn mức 500 để quay Thẻ Bạc**\n\n"
            "**Thẻ Vàng**\n"
            "> - 2% - Tối Thượng\n"
            "> - 18% - Truyền Thuyết\n"
            "> - 30% - Huyền Thoại\n"
            "> - 20% - Anh Hùng\n"
            "> - 15% - Thường\n"
            "> - 15% - Hụt\n\n"
            "**Hãy chọn mức 1000 để quay Thẻ Vàng**\n\n"
            "**Thẻ Kim Cương**\n"
            "> - 5% - Tối Thượng\n"
            "> - 10% - Truyền Thuyết\n"
            "> - 40% - Huyền Thoại\n"
            "> - 30% - Anh Hùng\n"
            "> - 15% - Thường\n"
            "**Hãy chọn mức 2000 để quay Thẻ Kim Cương**"
        ),
        color=discord.Color.purple(),
    )
    embed.set_footer(text="Chọn một mức roll ở bên dưới.")
    return embed


async def roll_waifu_logic(ctx, mode: str):
    if hasattr(ctx, "response"):
        await _defer_if_needed(ctx, ephemeral=True)

    user_obj = getattr(ctx, "user", getattr(ctx, "author", None))
    if user_obj is None:
        return await _respond(ctx, "❌ Không xác định được người dùng!", ephemeral=True)

    user_id = str(user_obj.id)
    lock = _get_user_lock(user_id)

    async with lock:
        waifu_data = await load_waifu_data()
        inventory = await load_inventory()
        user_inv = _ensure_inventory_schema(inventory, user_id)

        cost_map = {"free": 0, "200": 200, "500": 500, "1000": 1000, "2000": 2000}
        if mode not in cost_map:
            return await _respond(ctx, "❌ Mode không hợp lệ!", ephemeral=True)

        user_before = copy.deepcopy(await get_user_data(user_id))

        luck = await _maybe_await(get_luck(user_obj.id)) if callable(get_luck) else 0
        if luck is None:
            luck = 0

        spent = 0
        free_consumed = False

        if mode == "free":
            now = time.time()
            last_free = int(user_before.get("last_free", 0) or 0)
            if now - last_free < 64800:
                return await _respond(ctx, "⏱ Bạn đã roll free hôm nay rồi!", ephemeral=True)
            free_consumed = True
        else:
            cost = cost_map[mode]
            current_gold = int(user_before.get("gold", 0) or 0)
            if current_gold < cost:
                return await _respond(ctx, "❌ Không đủ gold!", ephemeral=True)

            user_before["gold"] = current_gold - cost
            await save_user_data(user_id, user_before)
            spent = cost

        rank = roll_rank(mode, luck)
        if not rank:
            if spent > 0:
                await _rollback_user_snapshot(user_id, user_before)
            return await _respond(ctx, "❌ Roll thất bại.", ephemeral=True)

        waifu_id = get_random_waifu(waifu_data, rank)
        if not waifu_id:
            if spent > 0:
                await _rollback_user_snapshot(user_id, user_before)
            return await _respond(ctx, "❌ Không có waifu phù hợp!", ephemeral=True)

        waifu = waifu_data.get(waifu_id, {})
        inv_before = copy.deepcopy(inventory)
        waifu_before = copy.deepcopy(waifu_data)

        try:
            if waifu_id in user_inv["waifus"]:
                user_inv["bag"][waifu_id] = user_inv["bag"].get(waifu_id, 0) + 1
            else:
                user_inv["waifus"][waifu_id] = 1

            if waifu.get("quantity", -1) != -1:
                waifu["claimed"] = int(waifu.get("claimed", 0) or 0) + 1

            waifu_data[waifu_id] = waifu

            await save_inventory(inventory)
            await save_waifu_data(waifu_data)

            if free_consumed:
                user_now = await get_user_data(user_id)
                user_now["last_free"] = time.time()
                await save_user_data(user_id, user_now)

            try:
                await sync_all()
            except Exception:
                pass

        except Exception:
            if spent > 0:
                await _rollback_user_snapshot(user_id, user_before)
            await _rollback_inventory_snapshot(inv_before)
            await _rollback_waifu_snapshot(waifu_before)
            return await _respond(ctx, "❌ Lỗi, đã hoàn tác!", ephemeral=True)

        waifu_name = waifu.get("name", waifu_id)
        rank_name = rank if rank else "Không rõ"
        image = waifu.get("image")
        bio = waifu.get("Bio") or waifu.get("bio") or ""

        embed = discord.Embed(
            title="🎉 Bạn đã roll thành công!",
            description=(
                f"**Waifu:** {waifu_name}\n"
                f"**ID:** `{waifu_id}`\n"
                f"**Rank:** `{rank_name}`\n"
                f"**Bio:** {bio if bio else 'Không có'}"
            ),
            color=discord.Color.green(),
        )
        if image:
            embed.set_image(url=image)

        if spent > 0:
            embed.set_footer(text=f"Đã trừ {spent} gold.")
        else:
            embed.set_footer(text="Lượt roll miễn phí đã được dùng.")

        return await _respond(ctx, embed=embed, ephemeral=True)


# =========================
# SHOP LOGIC
# =========================
class QuantityModal(Modal):
    def __init__(self, item: str, cost: int):
        super().__init__(title=f"Mua {item}")
        self.item = item
        self.cost = cost
        self.quantity = TextInput(
            label="Số lượng",
            placeholder="Nhập số lượng muốn mua",
            required=True,
            min_length=1,
            max_length=4,
        )
        self.add_item(self.quantity)

    async def on_submit(self, interaction: discord.Interaction):
        await _defer_if_needed(interaction, ephemeral=True)

        try:
            qty = int(str(self.quantity.value).strip())
        except Exception:
            return await _respond(interaction, "❌ Số lượng không hợp lệ!", ephemeral=True)

        if qty <= 0:
            return await _respond(interaction, "❌ Số lượng phải lớn hơn 0!", ephemeral=True)

        user_id = str(interaction.user.id)
        lock = _get_user_lock(user_id)

        async with lock:
            user_data = await get_user_data(user_id)
            inventory = await load_inventory()
            user_inv = _ensure_inventory_schema(inventory, user_id)

            total = self.cost * qty
            current_gold = int(user_data.get("gold", 0) or 0)
            if current_gold < total:
                return await _respond(interaction, "❌ Không đủ gold!", ephemeral=True)

            user_data["gold"] = current_gold - total
            user_inv["bag_item"][self.item] = int(user_inv["bag_item"].get(self.item, 0)) + qty

            try:
                await save_user_data(user_id, user_data)
                await save_inventory(inventory)
            except Exception:
                return await _respond(interaction, "❌ Lỗi, giao dịch đã bị hủy!", ephemeral=True)

            try:
                await sync_all()
            except Exception:
                pass

        await _respond(
            interaction,
            f"✅ Mua {qty} {self.item} (-{total} gold)",
            ephemeral=True,
        )


class ShopView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label=" Soup", style=discord.ButtonStyle.green, custom_id="shop_soup")
    async def soup(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(QuantityModal("soup", 100))

    @discord.ui.button(label=" Pizza", style=discord.ButtonStyle.blurple, custom_id="shop_pizza")
    async def pizza(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(QuantityModal("pizza", 200))

    @discord.ui.button(label=" Drug", style=discord.ButtonStyle.red, custom_id="shop_drug")
    async def drug(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(QuantityModal("drug", 300))


def build_shop_embed():
    embed = discord.Embed(
        title="Cửa Hàng",
        description=(
            "**Soup** - 100 gold\n"
            "**Pizza** - 200 gold\n"
            "**Drug** - 300 gold\n\n"
            "Chọn món bên dưới để mua."
        ),
        color=discord.Color.blurple(),
    )
    embed.set_footer(text="Mua hàng sẽ trừ gold trực tiếp từ API.")
    return embed


# =========================
# SEND EMBEDS TO CHANNEL
# =========================
async def send_roll_embed_logic(interaction, channel_id: str):
    await _defer_if_needed(interaction, ephemeral=True)

    if not interaction.guild:
        return await _respond(interaction, "❌ Lệnh chỉ dùng trong server!", ephemeral=True)

    if not interaction.user.guild_permissions.administrator:
        return await _respond(interaction, "❌ Cần quyền admin!", ephemeral=True)

    if not channel_id:
        return await _respond(interaction, "❌ Thiếu channel ID!", ephemeral=True)

    try:
        ch_id = int(channel_id)
    except Exception:
        return await _respond(interaction, "❌ Channel ID không hợp lệ!", ephemeral=True)

    channel = interaction.guild.get_channel(ch_id)
    if not channel:
        try:
            channel = await interaction.guild.fetch_channel(ch_id)
        except Exception:
            return await _respond(interaction, "❌ Không tìm thấy channel!", ephemeral=True)

    try:
        await channel.send(embed=build_roll_embed(), view=RollView())
    except Exception as e:
        return await _respond(interaction, f"❌ Không gửi được embed: {e}", ephemeral=True)

    return await _respond(interaction, f"✅ Đã gửi roll embed vào {channel.mention}", ephemeral=True)


async def send_shop_embed_logic(interaction, channel_id: str):
    await _defer_if_needed(interaction, ephemeral=True)

    if not interaction.guild:
        return await _respond(interaction, "❌ Lệnh chỉ dùng trong server!", ephemeral=True)

    if not interaction.user.guild_permissions.administrator:
        return await _respond(interaction, "❌ Cần quyền admin!", ephemeral=True)

    if not channel_id:
        return await _respond(interaction, "❌ Thiếu channel ID!", ephemeral=True)

    try:
        ch_id = int(channel_id)
    except Exception:
        return await _respond(interaction, "❌ Channel ID không hợp lệ!", ephemeral=True)

    channel = interaction.guild.get_channel(ch_id)
    if not channel:
        try:
            channel = await interaction.guild.fetch_channel(ch_id)
        except Exception:
            return await _respond(interaction, "❌ Không tìm thấy channel!", ephemeral=True)

    try:
        await channel.send(embed=build_shop_embed(), view=ShopView())
    except Exception as e:
        return await _respond(interaction, f"❌ Không gửi được embed: {e}", ephemeral=True)

    return await _respond(interaction, f"✅ Đã gửi shop embed vào {channel.mention}", ephemeral=True)


# =========================
# UI VIEWS
# =========================
class RollView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Free", style=discord.ButtonStyle.green, custom_id="roll_free")
    async def roll_free(self, interaction: discord.Interaction, button: Button):
        await roll_waifu_logic(interaction, "free")

    @discord.ui.button(label="200", style=discord.ButtonStyle.secondary, custom_id="roll_200")
    async def roll_200(self, interaction: discord.Interaction, button: Button):
        await roll_waifu_logic(interaction, "200")

    @discord.ui.button(label="500", style=discord.ButtonStyle.blurple, custom_id="roll_500")
    async def roll_500(self, interaction: discord.Interaction, button: Button):
        await roll_waifu_logic(interaction, "500")

    @discord.ui.button(label="1000", style=discord.ButtonStyle.primary, custom_id="roll_1000")
    async def roll_1000(self, interaction: discord.Interaction, button: Button):
        await roll_waifu_logic(interaction, "1000")

    @discord.ui.button(label="2000", style=discord.ButtonStyle.danger, custom_id="roll_2000")
    async def roll_2000(self, interaction: discord.Interaction, button: Button):
        await roll_waifu_logic(interaction, "2000")


# =========================
# BOT SETUP
# =========================
async def setup(bot):
    bot.add_view(ShopView())
    bot.add_view(RollView())


__all__ = [
    "setup_channel_logic",
    "send_roll_embed_logic",
    "send_shop_embed_logic",
    "RollView",
    "ShopView",
    "roll_waifu_logic",
    "load_channels",
    "save_channels",
    "load_auctions",
    "save_auctions",
    "load_inventory",
    "save_inventory",
    "load_waifu_data",
    "save_waifu_data",
    "get_user_data",
    "save_user_data",
]

print("Loaded setup has success")

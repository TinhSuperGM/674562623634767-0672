import discord
import asyncio
from typing import Any, Dict

from api_client import get, post  # dùng API thay JSON

_inv_lock = asyncio.Lock()


async def _send_response(interaction: discord.Interaction, content: str, ephemeral: bool = False):
    try:
        if interaction.response.is_done():
            await interaction.followup.send(content, ephemeral=ephemeral)
        else:
            await interaction.response.send_message(content, ephemeral=ephemeral)
    except (discord.HTTPException, discord.NotFound):
        try:
            if interaction.channel:
                await interaction.channel.send(content)
        except Exception:
            pass


# ===== HELPER FIX DEFAULT =====
def _fix_default_waifu(user_data: Dict[str, Any]) -> None:
    default = user_data.get("default_waifu")
    waifus = user_data.get("waifus", {})

    if not default:
        return

    count = waifus.get(default, 0)

    try:
        count = int(count)
    except Exception:
        count = 0

    if count <= 0:
        user_data["default_waifu"] = None


# ===== LOGIC =====
async def select_waifu_logic(interaction, waifu_id: str):
    if not interaction or not interaction.user:
        return

    uid = str(interaction.user.id)

    if not waifu_id or not isinstance(waifu_id, str):
        return await _send_response(
            interaction,
            "❌ Bạn không sở hữu waifu ``!",
            ephemeral=True
        )

    waifu_id = waifu_id.lower().strip()
    error_msg = None

    async with _inv_lock:
        try:
            inv = await get(f"/inventory/{uid}")
        except Exception:
            inv = {}

        if not isinstance(inv, dict):
            inv = {}

        user_data = inv

        if not isinstance(user_data, dict):
            error_msg = f"❌ Bạn không sở hữu waifu `{waifu_id}`!"
        else:
            # đảm bảo structure (GIỮ NGUYÊN logic cũ)
            if "waifus" not in user_data or not isinstance(user_data["waifus"], dict):
                user_data["waifus"] = {}

            if "default_waifu" not in user_data:
                user_data["default_waifu"] = None

            _fix_default_waifu(user_data)

            waifus = user_data["waifus"]

            if waifu_id not in waifus or int(waifus.get(waifu_id, 0)) <= 0:
                error_msg = f"❌ Bạn không sở hữu waifu `{waifu_id}`!"
            else:
                user_data["default_waifu"] = waifu_id

                try:
                    await post(f"/inventory/{uid}/update", {
                        "data": user_data
                    })
                except Exception:
                    error_msg = "❌ Có lỗi khi lưu dữ liệu!"

    if error_msg:
        return await _send_response(interaction, error_msg, ephemeral=True)

    await _send_response(
        interaction,
        f"✅ Đã chọn **{waifu_id}** làm waifu mặc định!"
    )


# ===== AUTO CLEAN =====
async def cleanup_default_waifu(uid: str):
    async with _inv_lock:
        try:
            user_data = await get(f"/inventory/{uid}")
        except Exception:
            return

        if not isinstance(user_data, dict):
            return

        _fix_default_waifu(user_data)

        try:
            await post(f"/inventory/{uid}/update", {
                "data": user_data
            })
        except Exception:
            pass


# ===== SETUP =====
async def setup(bot):
    pass


print("Loaded select waifu has success (API mode)")
from __future__ import annotations

from typing import Optional

import discord

from Data.api_client import get, post


# =========================================================
# gold.py (API mode)
# - Read user gold from API
# - Auto-create only for the command author
# - Compatible with bot command flow
# =========================================================

GOLD_START = 100


async def _send(interaction: discord.Interaction, content: str):
    """
    Safe response helper for interaction-based commands.
    """
    try:
        if interaction.response.is_done():
            return await interaction.followup.send(content)
        return await interaction.response.send_message(content)
    except Exception:
        # Last resort: try followup again
        return await interaction.followup.send(content)


async def gold_logic(interaction: discord.Interaction, user: Optional[discord.User] = None):
    target = user if user else interaction.user
    user_id = str(target.id)

    # ===== GET USER FROM API =====
    user_data = await get(f"/users/{user_id}")
    if not isinstance(user_data, dict):
        user_data = {}

    # ===== USER CHƯA CÓ DATA =====
    if "gold" not in user_data:
        if target.id == interaction.user.id:
            # tạo user mới cho chính người dùng đang gọi lệnh
            await post(f"/users/{user_id}/update", {
                "gold": GOLD_START,
                "last_free": 0
            })
            return await _send(
                interaction,
                "✅ Chào người mới! Bạn nhận 100 để bắt đầu!"
            )

        return await _send(
            interaction,
            "❌ Người này chưa đăng ký tài khoản!"
        )

    gold_amount = int(user_data.get("gold", 0))

    # ===== HIỂN THỊ =====
    if target.id != interaction.user.id:
        return await _send(
            interaction,
            f"💰 Số dư của <@{target.id}>: {gold_amount} <a:gold:1492792339436142703>"
        )

    return await _send(
        interaction,
        f"💰 Số dư của bạn: {gold_amount} <a:gold:1492792339436142703>"
    )


# ===== SETUP =====
async def setup(bot):
    pass


print("Loaded gold has success")

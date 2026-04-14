import discord
from Data.api_client import get, post


# ===== LOGIC =====
async def gold_logic(interaction, user: discord.User = None):
    target = user if user else interaction.user
    user_id = str(target.id)

    # ===== GET USER FROM API =====
    user_data = await get(f"/users/{user_id}")

    # ===== USER CHƯA CÓ DATA =====
    if not user_data or "gold" not in user_data:
        if target.id == interaction.user.id:
            # tạo user mới
            await post(f"/users/{user_id}/update", {
                "data": {
                    "gold": 100,
                    "last_free": 0
                }
            })

            return await interaction.response.send_message(
                "🎉 Chào người mới! Bạn nhận 100 🪙 để bắt đầu!"
            )
        else:
            return await interaction.response.send_message(
                "❌ Người này chưa đăng ký tài khoản!"
            )

    gold_amount = int(user_data.get("gold", 0))

    # ===== HIỂN THỊ =====
    if target.id != interaction.user.id:
        return await interaction.response.send_message(
            f"💰 Số dư của <@{target.id}>: {gold_amount} <a:gold:1492792339436142703>"
        )
    else:
        return await interaction.response.send_message(
            f"💰 Số dư của bạn: {gold_amount} <a:gold:1492792339436142703>"
        )


# ===== SETUP =====
async def setup(bot):
    pass


print("Loaded gold has success")